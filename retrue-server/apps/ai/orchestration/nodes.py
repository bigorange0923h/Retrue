"""编排图节点实现。

节点只通过 ``OrchestrationState`` 交换编排事实，不直接持有 therapist 或
任务对象。需要访问领域数据时，通过 ``assistant_task_id`` 从数据库恢复任务，
再由 ``task.therapist_id`` 派生可信身份；绝不接收客户端提供的 therapist_id。

真实 AI 回复由节点调用 provider 生成并写入 Conversation；回复正文只放在
``state.reply_content``（仅内存）中返回给 API，绝不写入任务状态或 checkpoint。

每个节点返回对 state 的增量更新（dict），图负责合并。
"""

from __future__ import annotations

import hashlib
from typing import Any

from apps.ai.orchestration.intent import classify_intent
from apps.ai.orchestration.limits import NodeLimitError, max_steps, max_tool_calls
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


def _save_assistant_message(conversation_id: int | None, content: str) -> int | None:
    """把生成的回复写入会话（不可变消息），返回消息主键。

    会话是对话记录，不是正式业务数据；写入仅发生在编排生成回复后。
    """
    if not conversation_id or not content:
        return None
    from apps.conversations.models import Message, MessageRole

    message = Message.objects.create(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
    )
    return message.id


def _chat(system: str, prompt: str) -> str:
    """通过 provider 生成回复，失败时抛出，由上层做安全降级。"""
    from apps.ai.providers.factory import get_provider

    return get_provider().chat(prompt, system=system)


def receive_turn_node(state: OrchestrationState) -> dict:
    """回合入口：首轮进入分类；恢复场景保持原 next_node 以便按暂停节点路由。"""
    _bump_step(state)
    # 恢复场景（state_data 已含 intent 且 next_node 非空）不重新分类，
    # 由 service 层按 next_node 定向继续，图不再按 intent 重跑。
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
    """通用知识咨询直接回答，不读客户数据。"""
    _bump_step(state)
    from apps.ai.prompts.loader import load_prompt

    try:
        reply = _chat(load_prompt("general_answer_system"), state.get("user_input", ""))
    except Exception:  # noqa: BLE001 - 模型失败降级为固定提示，不伪造内容
        reply = "抱歉，暂时无法生成回答，请稍后重试。"
    message_id = _save_assistant_message(state.get("conversation_id"), reply)
    return {
        "next_node": "answer_general",
        "reply_content": reply,
        "assistant_message_id": message_id,
    }


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


def _tool_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    """生成工具调用的去重签名，不保存参数原文（仅哈希）。"""
    canonical = hashlib.sha256(repr(sorted(arguments.items())).encode("utf-8")).hexdigest()[:16]
    return f"{tool_name}:{canonical}"


def execute_read_tools_node(state: OrchestrationState) -> dict:
    """执行选定的只读 Tool，落实单轮上限、去重、有限重试与失败降级。"""
    _bump_step(state)
    task = _task_from_state(state)
    from apps.assistant_tasks import tools
    from apps.assistant_tasks.services import TaskBusinessError

    tool_contexts: list[dict[str, Any]] = []
    tool_refs: list[str] = []
    signatures: list[str] = list(state.get("tool_signatures") or [])

    for tool_name in state.get("required_tools", []):
        if len(tool_refs) >= max_tool_calls():
            break
        arguments = {"customer_id": state.get("customer_id")}
        signature = _tool_signature(tool_name, arguments)
        if signature in signatures:
            # 同一 Run 中相同 Tool + 相同参数组合只执行一次。
            continue
        signatures.append(signature)

        result = None
        last_error: Exception | None = None
        # 最多尝试 2 次（首次 + 1 次重试）。
        for _attempt in range(2):
            try:
                result = tools.execute_tool(task, tool_name, arguments)
                break
            except (TaskBusinessError, tools.ToolBusinessError) as exc:
                last_error = exc
            except Exception as exc:  # noqa: BLE001 - 未知错误也安全降级
                last_error = exc
                break

        if result is not None:
            tool_refs.append(f"tool_execution:{result.tool_execution.id}")
            tool_contexts.append({"tool": tool_name, "result": dict(result)})
        else:
            # 失败后记录失败并安全降级，不伪造客户历史。
            tool_refs.append(f"tool_failed:{tool_name}")
            tool_contexts.append({"tool": tool_name, "error": _safe_error(last_error)})

    return {
        "tool_result_refs": tool_refs,
        "tool_signatures": signatures,
        "tool_contexts": tool_contexts,
        "next_node": "answer_with_context",
    }


def _safe_error(exc: Exception | None) -> str:
    """把异常压缩为不可推断业务细节的短消息。"""
    if exc is None:
        return "查询失败"
    text = str(exc)
    return text[:120] if text else "查询失败"


def answer_with_context_node(state: OrchestrationState) -> dict:
    """基于只读事实组织脱敏上下文并生成回复，明确区分系统记录与建议。"""
    _bump_step(state)
    from apps.ai.prompts.loader import load_prompt, render_prompt

    context_parts: list[str] = []
    for item in state.get("tool_contexts", []):
        tool_name = item.get("tool")
        if "error" in item:
            context_parts.append(f"- {tool_name}：查询失败，未能获取该项信息")
        else:
            context_parts.append(f"- {tool_name}：{_summarize_context(item.get('result'))}")

    context_text = "\n".join(context_parts) if context_parts else "（暂无系统记录）"
    prompt = render_prompt(
        "customer_answer",
        context=context_text,
        question=state.get("user_input", ""),
    )
    try:
        reply = _chat(load_prompt("customer_answer_system"), prompt)
    except Exception:  # noqa: BLE001
        reply = "暂时无法读取客户信息，请稍后重试。"
    message_id = _save_assistant_message(state.get("conversation_id"), reply)
    return {
        "next_node": "answer_with_context",
        "reply_content": reply,
        "assistant_message_id": message_id,
    }


def _summarize_context(result: Any) -> str:
    """把只读 Tool 结果压缩为受限的脱敏摘要，避免把完整资料带入提示词。"""
    if not isinstance(result, dict):
        return "已获取"
    parts: list[str] = []
    customer = result.get("customer")
    if isinstance(customer, dict):
        parts.append(f"客户 {customer.get('name', '')}")
    initial = result.get("initial_assessment") or result.get("assessment")
    if isinstance(initial, dict):
        status = initial.get("status_display") or initial.get("status") or ""
        if initial.get("exists"):
            parts.append(f"首次评估：{status or '已完成'}")
        else:
            parts.append("首次评估：尚未完成")
    if "recent_training_count" in result:
        parts.append(f"训练记录 {result['recent_training_count']} 条")
    if "total" in result and "items" in result:
        parts.append(f"共 {result['total']} 条记录")
    plan = result.get("active_plan")
    if isinstance(plan, dict) and plan.get("name"):
        parts.append(f"当前计划：{plan['name']}")
    return "；".join(parts) if parts else "已获取"


def ensure_customer_node(state: OrchestrationState) -> dict:
    """训练补记前确保客户已绑定。"""
    _bump_step(state)
    if state.get("customer_id") is None:
        return {"next_node": "wait_customer_selection", "missing_fields": ["customer_id"]}
    return {"next_node": "create_training_draft"}


def create_training_draft_node(state: OrchestrationState) -> dict:
    """生成训练补记草稿（pending），等待康复师确认。

    若已有草稿（恢复场景），不重复生成，只返回已有 draft_id。
    """
    _bump_step(state)
    orchestration_task = _task_from_state(state)

    existing_draft_id = (state.get("resource_refs") or {}).get("draft_id")
    if existing_draft_id:
        return {
            "resource_refs": state.get("resource_refs"),
            "next_node": "wait_draft_confirmation",
        }

    from apps.ai.services import training_parser
    from apps.assistant_tasks import services as task_services

    input_text = state.get("user_input", "") or _latest_user_message(orchestration_task)
    if not input_text.strip():
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
    """风险核查：生成非技术化的人工核查提醒，不自动诊断、不生成正式记录。"""
    _bump_step(state)
    from apps.ai.prompts.loader import load_prompt

    try:
        notice = _chat(load_prompt("risk_review_system"), state.get("user_input", ""))
    except Exception:  # noqa: BLE001
        notice = "这段描述可能涉及需要人工核查的风险或禁忌情况，请结合客户资料确认后再继续，系统不会自动生成任何正式记录。"
    message_id = _save_assistant_message(state.get("conversation_id"), notice)
    return {
        "next_node": "risk_review",
        "risk_notice": notice,
        "reply_content": notice,
        "assistant_message_id": message_id,
    }
