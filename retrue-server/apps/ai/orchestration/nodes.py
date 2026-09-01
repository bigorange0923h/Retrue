"""编排图节点实现。

节点只通过 ``OrchestrationState`` 交换编排事实，不直接持有 therapist 或
任务对象。需要访问领域数据时，通过 ``assistant_task_id`` 从数据库恢复任务，
再由 ``task.therapist_id`` 派生可信身份；绝不接收客户端提供的 therapist_id。

每个节点返回对 state 的增量更新（dict），图负责合并。
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.ai.orchestration.intent import classify_intent
from apps.ai.orchestration.limits import NodeLimitError, max_steps
from apps.ai.orchestration.state import OrchestrationState


def _bump_step(state: OrchestrationState) -> None:
    """节点入口自增步数并检查上限。"""
    current = int(state.get("step_count") or 0) + 1
    if current > max_steps():
        raise NodeLimitError(
            f"单轮图节点执行次数超过上限 {max_steps()}",
            error_code="orchestration_step_limit_exceeded",
        )
    state["step_count"] = current


def _task_from_state(state: OrchestrationState):
    """从状态恢复任务（可信身份来源）。"""
    from apps.assistant_tasks.models import AssistantTask

    task_id = state.get("assistant_task_id")
    if not task_id:
        raise NodeLimitError("缺少任务上下文", error_code="task_missing")
    task = AssistantTask.objects.filter(pk=task_id).first()
    if task is None:
        raise NodeLimitError("任务不存在", error_code="task_not_found")
    return task


def receive_turn_node(state: OrchestrationState) -> dict:
    """回合入口：首轮进入分类；恢复场景保持原 next_node 以便按意图路由。"""
    _bump_step(state)
    # 恢复场景（state_data 已含 intent 且 next_node 非空）不重新分类，
    # 由 _route_after_receive 按已持久化 intent 路由到对应分支。
    if state.get("intent") and state.get("next_node"):
        return {}
    return {"next_node": "classify_intent"}


def classify_intent_node(state: OrchestrationState) -> dict:
    """意图与风险初筛节点。"""
    _bump_step(state)
    result = classify_intent(
        state.get("user_input", ""),
        customer_bound=state.get("customer_id") is not None,
        customer_name=state.get("customer_name", ""),
    )
    return {
        "intent": result.intent,
        "needs_confirmation": result.needs_confirmation,
        "customer_name": result.customer_name,
        "required_tools": result.required_tools or [],
    }


def answer_general_node(state: OrchestrationState) -> dict:
    """通用知识咨询直接回答（不读客户数据）。"""
    _bump_step(state)
    # 通用问答不读取客户数据；真实回答由 provider.chat 在 API 层生成，这里只
    # 记录编排事实，避免把模型输出写进图状态。
    return {"next_node": "answer_general"}


def customer_lookup_node(state: OrchestrationState) -> dict:
    """按姓名查询当前康复师客户，返回候选数量用于路由。"""
    _bump_step(state)
    task = _task_from_state(state)
    from apps.assistant_tasks import tools

    name = (state.get("customer_name") or "").strip()
    if not name:
        return {"next_node": "wait_customer_name", "missing_fields": ["customer_name"]}
    matches = tools.lookup_current_therapist_customers_by_name(task.therapist, name)
    count = len(matches)
    if count == 0:
        return {"next_node": "wait_customer_name", "missing_fields": ["customer_name"]}
    if count == 1:
        return {"customer_id": matches[0]["id"], "next_node": "bind_customer"}
    return {
        "next_node": "wait_customer_selection",
        "missing_fields": ["customer_id"],
        "customer_candidates": matches,
    }


def bind_customer_node(state: OrchestrationState) -> dict:
    """绑定已唯一确定的客户。"""
    _bump_step(state)
    return {"next_node": "bound"}


def choose_read_tools_node(state: OrchestrationState) -> dict:
    """根据客户问题选择只读 Tool（首期固定为上下文查询）。"""
    _bump_step(state)
    return {"required_tools": ["get_customer_context"], "next_node": "execute_read_tools"}


def execute_read_tools_node(state: OrchestrationState) -> dict:
    """执行选定的只读 Tool，并把结果引用写入状态。"""
    _bump_step(state)
    task = _task_from_state(state)
    from apps.assistant_tasks import tools

    tool_refs: list[str] = []
    for tool_name in state.get("required_tools", []):
        result = tools.execute_tool(task, tool_name, {"customer_id": state.get("customer_id")})
        tool_refs.append(f"tool_execution:{result.tool_execution.id}")
    return {"tool_result_refs": tool_refs, "next_node": "answer_with_context"}


def answer_with_context_node(state: OrchestrationState) -> dict:
    """基于只读事实回答（真实文本在 API 层生成）。"""
    _bump_step(state)
    return {"next_node": "answer_with_context"}


def ensure_customer_node(state: OrchestrationState) -> dict:
    """训练补记前确保客户已绑定。"""
    _bump_step(state)
    if state.get("customer_id") is None:
        return {"next_node": "wait_customer_selection", "missing_fields": ["customer_id"]}
    return {"next_node": "create_training_draft"}


def create_training_draft_node(state: OrchestrationState) -> dict:
    """生成训练补记草稿（pending），等待康复师确认。

    训练补记沿用现有领域服务的草稿闭环；这里为补记创建/复用独立的
    ``task_type=training_record`` 业务任务，并把草稿关联到该任务，
    使补记草稿可通过任务中断恢复，同时不改变领域服务的幂等与审计边界。
    """
    _bump_step(state)
    orchestration_task = _task_from_state(state)
    from apps.ai.services import training_parser
    from apps.assistant_tasks import services as task_services

    input_text = state.get("user_input", "") or _latest_user_message(orchestration_task)
    if not input_text.strip():
        # 恢复场景无原文可用时，无法生成草稿，安全降级为等待补充。
        return {"next_node": "wait_customer_name", "missing_fields": ["training_text"]}

    business_task = task_services.create_task(
        orchestration_task.therapist,
        customer=state.get("customer_id"),
        task_type="training_record",
        skill_code="training_record",
        origin="assistant_turns",
        business_key=f"training_record:{orchestration_task.id}",
    )

    draft = training_parser.parse_training_draft(
        orchestration_task.therapist,
        input_text,
        customer_id=state.get("customer_id"),
        assistant_task_id=business_task.id,
    )
    return {
        "resource_refs": {"draft_id": draft.id, "task_id": business_task.id},
        "next_node": "wait_draft_confirmation",
    }


def _latest_user_message(task: Any) -> str:
    """从任务关联会话读取最后一条用户消息原文（恢复训练补记输入）。"""
    conversation_id = getattr(task, "conversation_id", None)
    if not conversation_id:
        return ""
    from apps.conversations.models import Message

    message = (
        Message.objects.filter(conversation_id=conversation_id, role="user")
        .order_by("-created_at", "-id")
        .first()
    )
    return message.content if message else ""


def wait_draft_confirmation_node(state: OrchestrationState) -> dict:
    """进入等待康复师确认节点。"""
    _bump_step(state)
    return {"next_node": "wait_draft_confirmation"}


def wait_customer_name_node(state: OrchestrationState) -> dict:
    """等待补充客户姓名。"""
    _bump_step(state)
    return {"next_node": "wait_customer_name"}


def wait_customer_selection_node(state: OrchestrationState) -> dict:
    """等待同名客户选择。"""
    _bump_step(state)
    return {"next_node": "wait_customer_selection"}


def risk_review_node(state: OrchestrationState) -> dict:
    """风险核查：提示康复师人工核查，不自动诊断。"""
    _bump_step(state)
    return {"next_node": "risk_review"}
