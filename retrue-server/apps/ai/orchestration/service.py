"""统一回合编排服务。

把一次用户输入统一送入受控图流程，并在图执行前后同步任务状态与审计事件。
本服务是 LangGraph 与 Django 领域服务之间的适配层：

- 权限：从登录康复师与任务归属校验，绝不信任客户端 therapist_id。
- 状态：任务状态迁移由 ``assistant_tasks.services`` 状态机负责。
- 写入：只读 Tool 与草稿生成由领域服务执行；正式写入始终要求康复师确认。
- 恢复：任务中断后从暂停节点定向继续，绝不重跑整张图重新猜测意图。

图状态只保存任务、会话、客户、意图、下一步与引用 ID；不保存聊天原文、手机号、
病史、完整工具输出或提示词。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.ai.orchestration import nodes
from apps.ai.orchestration.graph import build_graph, compile_graph
from apps.ai.orchestration.state import (
    OrchestrationState,
    build_initial_state,
    restore_state_from_task,
    serialize_state,
)
from apps.assistant_tasks import services as task_services
from apps.assistant_tasks.models import (
    AssistantRun,
    AssistantRunStatus,
    AssistantTask,
    AssistantTaskStatus,
)


class OrchestrationDisabledError(RuntimeError):
    """编排功能被功能开关关闭。"""


def _ensure_enabled() -> None:
    if not getattr(settings, "AI_ORCHESTRATION_ENABLED", False):
        raise OrchestrationDisabledError("AI 助理编排功能未启用")


def _save_message(conversation_id: int, role: str, content: str, metadata: dict | None = None):
    """保存一条不可变消息到会话，返回消息对象。"""
    from apps.conversations.models import Message

    return Message.objects.create(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata=metadata or {},
    )


def _start_run(task: AssistantTask, *, client_request_id: str = "") -> AssistantRun:
    """创建或复用一次可追溯的 AssistantRun。"""
    from apps.assistant_tasks.models import AssistantRun

    attempt = (
        AssistantRun.objects.filter(task_id=task.id).count() + 1
    )
    return AssistantRun.objects.create(
        task_id=task.id,
        client_request_id=str(client_request_id or "").strip()[:128],
        attempt=attempt,
        status=AssistantRunStatus.RUNNING,
        started_at=timezone.now(),
    )


def _finish_run(run: AssistantRun, *, error: Exception | None = None) -> None:
    """结束一次执行，写状态与脱敏错误信息。"""
    run.finished_at = timezone.now()
    if error is None:
        run.status = AssistantRunStatus.SUCCEEDED
    else:
        run.status = AssistantRunStatus.FAILED
        run.error_code = str(getattr(error, "error_code", "orchestration_failed"))[:64]
        run.error_message = str(error)[:500]
    run.save(update_fields=["status", "error_code", "error_message", "finished_at", "updated_at"])


def _sync_task_after_graph(task: AssistantTask, state: OrchestrationState) -> AssistantTask:
    """把图产出的安全状态同步回任务。"""
    next_node = state.get("next_node") or ""
    task.current_step = next_node
    task.missing_fields = list(state.get("missing_fields") or [])
    task.state_data = serialize_state(state)
    task.last_activity_at = timezone.now()
    task.version = (task.version or 0) + 1
    task.save(
        update_fields=[
            "current_step",
            "missing_fields",
            "state_data",
            "last_activity_at",
            "version",
            "updated_at",
        ]
    )
    return task


def _waiting_status_for_node(next_node: str) -> str:
    """把等待节点映射为任务状态。"""
    if next_node in {"wait_draft_confirmation"}:
        return AssistantTaskStatus.WAITING_CONFIRMATION
    if next_node in {"wait_customer_name", "wait_customer_selection"}:
        return AssistantTaskStatus.WAITING_USER
    if next_node == "risk_review":
        return AssistantTaskStatus.BLOCKED
    return AssistantTaskStatus.COMPLETED


def _transition_from_waiting(task: AssistantTask, event_type: str) -> AssistantTask:
    """把等待态先转回 running，再继续执行。"""
    if task.status in {
        AssistantTaskStatus.WAITING_USER,
        AssistantTaskStatus.WAITING_CONFIRMATION,
        AssistantTaskStatus.BLOCKED,
        AssistantTaskStatus.FAILED,
    }:
        return task_services.transition_task(
            task,
            AssistantTaskStatus.RUNNING,
            event_type=event_type,
        )
    return task


def _run_graph(state: OrchestrationState) -> OrchestrationState:
    """运行完整图（仅首轮使用）。"""
    app = compile_graph(build_graph())
    result: OrchestrationState = app.invoke(dict(state))
    return result


def handle_turn(
    therapist: Any,
    *,
    message: str,
    conversation_id: int | None = None,
    customer_id: int | None = None,
    customer_name: str = "",
    client_request_id: str = "",
) -> dict[str, Any]:
    """发起一轮对话：保存消息、创建任务与执行、跑图、同步状态。"""
    _ensure_enabled()

    if conversation_id is not None:
        _save_message(conversation_id, "user", message)

    task = task_services.create_task(
        therapist,
        customer=customer_id,
        conversation=conversation_id,
        task_type="assistant_turn",
        skill_code="unified_assistant",
        origin="assistant_turns",
        client_request_id=client_request_id,
        status=AssistantTaskStatus.RUNNING,
    )

    run = _start_run(task, client_request_id=client_request_id)

    state = build_initial_state(
        assistant_task_id=task.id,
        conversation_id=conversation_id,
        customer_id=customer_id,
    )
    state["user_input"] = message
    state["customer_name"] = customer_name

    try:
        result = _run_graph(state)
    except Exception as exc:
        _finish_run(run, error=exc)
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
            event_data={"run_id": run.id},
        )
        raise

    _finish_run(run)
    task = _sync_task_after_graph(task, result)
    next_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(next_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=next_node,
        event_type="orchestration_turn_completed",
        event_data={"next_node": next_node, "intent": result.get("intent", ""), "run_id": run.id},
        run=run,
    )

    return _turn_payload(task, result)


def resume_task(therapist: Any, task_id: int, *, message: str = "") -> dict[str, Any]:
    """恢复未完成任务：严格从暂停节点继续，不重跑整张图。"""
    _ensure_enabled()
    task = task_services.get_owned_task(therapist, task_id)
    if task is None:
        raise task_services.TaskPermissionError("助手任务不存在或无权访问")

    task_services.recover_stale_running_tasks(therapist, task_id)
    state = restore_state_from_task(task.state_data)

    if message:
        state["user_input"] = message
        if task.conversation_id is not None:
            _save_message(task.conversation_id, "user", message)

    task = _transition_from_waiting(task, "orchestration_resumed")
    run = _start_run(task)
    next_node = state.get("next_node") or ""

    try:
        result = _continue_from_node(state, next_node, run, task)
    except Exception as exc:
        _finish_run(run, error=exc)
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
            event_data={"run_id": run.id},
            run=run,
        )
        raise

    _finish_run(run)
    task = _sync_task_after_graph(task, result)
    target_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(target_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=target_node,
        event_type="orchestration_turn_resumed",
        event_data={"next_node": target_node, "run_id": run.id},
        run=run,
    )
    return _turn_payload(task, result)


def submit_customer_selection(therapist: Any, task_id: int, customer_id: int) -> dict[str, Any]:
    """提交同名客户选择：重新校验归属后按原意图定向继续。"""
    _ensure_enabled()
    task = task_services.get_owned_task(therapist, task_id)
    if task is None:
        raise task_services.TaskPermissionError("助手任务不存在或无权访问")

    customer = task_services._load_customer(therapist, customer_id)
    if customer is None:
        raise task_services.TaskPermissionError("客户不存在或无权访问")

    state = restore_state_from_task(task.state_data)
    state["customer_id"] = customer.id

    task = _transition_from_waiting(task, "orchestration_customer_selection_started")
    run = _start_run(task)

    # 选择客户后按原意图定向：跳过姓名查询。
    intent = state.get("intent") or ""
    try:
        if intent == "training_record":
            result = nodes.ensure_customer_node(state)
            if result.get("next_node") == "create_training_draft":
                draft_result = nodes.create_training_draft_node(state)
                result = {**result, **draft_result}
        elif intent == "customer_question":
            result = nodes.choose_read_tools_node(state)
            exec_result = nodes.execute_read_tools_node(state)
            answer_result = nodes.answer_with_context_node(state)
            result = {**result, **exec_result, **answer_result}
        elif intent == "customer_lookup":
            result = nodes.bind_customer_node(state)
        else:
            result = {"next_node": "bound", "customer_id": customer.id}
    except Exception as exc:
        _finish_run(run, error=exc)
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
            event_data={"run_id": run.id},
            run=run,
        )
        raise

    _finish_run(run)
    # 选择客户后，任务正式绑定该客户。
    task.customer_id = customer.id
    task.save(update_fields=["customer", "updated_at"])
    task = _sync_task_after_graph(task, {**state, **result})
    target_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(target_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=target_node,
        event_type="orchestration_customer_selected",
        event_data={"next_node": target_node, "customer_id": customer.id, "run_id": run.id},
        run=run,
    )
    return _turn_payload(task, {**state, **result})


def _continue_from_node(
    state: OrchestrationState,
    next_node: str,
    run: AssistantRun,
    task: AssistantTask,
) -> OrchestrationState:
    """按暂停节点定向继续执行，绝不重新分类意图或猜测客户。"""
    state["user_input"] = state.get("user_input", "")
    if next_node in {"wait_customer_name", ""}:
        # 补充姓名后重新查客户。
        result = nodes.customer_lookup_node(state)
    elif next_node == "wait_customer_selection":
        # 未选客户不能继续读取或写入客户数据。
        result = {"next_node": "wait_customer_selection", "missing_fields": ["customer_id"]}
    elif next_node == "wait_draft_confirmation":
        # 只重新展示已有草稿，不重复生成。
        result = {
            "next_node": "wait_draft_confirmation",
            "resource_refs": state.get("resource_refs", {}),
        }
    elif next_node == "risk_review":
        result = {"next_node": "risk_review"}
    else:
        result = {"next_node": next_node or "completed"}
    merged = {**state, **result}
    return merged


def _turn_payload(task: AssistantTask, state: OrchestrationState) -> dict[str, Any]:
    """构造面向客户端的回合响应（不含图内部细节）。"""
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step,
        "missing_fields": task.missing_fields,
        "customer_id": state.get("customer_id"),
        "intent": state.get("intent", ""),
        "resource_refs": state.get("resource_refs", {}),
        "customer_candidates": state.get("customer_candidates", []),
        "needs_confirmation": state.get("needs_confirmation", False),
        "reply_content": state.get("reply_content", ""),
        "assistant_message_id": state.get("assistant_message_id"),
        "risk_notice": state.get("risk_notice", ""),
    }


__all__ = [
    "handle_turn",
    "resume_task",
    "submit_customer_selection",
    "OrchestrationDisabledError",
]
