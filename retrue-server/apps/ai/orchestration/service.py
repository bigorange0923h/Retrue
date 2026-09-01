"""统一回合编排服务。

把一次用户输入统一送入受控图流程，并在图执行前后同步任务状态与审计事件。
本服务是 LangGraph 与 Django 领域服务之间的适配层：

- 权限：从登录康复师与任务归属校验，绝不信任客户端 therapist_id。
- 状态：任务状态迁移由 ``assistant_tasks.services`` 状态机负责。
- 写入：只读 Tool 与草稿生成由领域服务执行；正式写入始终要求康复师确认。
- 恢复：任务中断后可从 ``state_data`` 恢复到相同节点，不让模型重新猜测。

图状态只保存任务、会话、客户、意图、下一步与引用 ID；不保存聊天原文、手机号、
病史、完整工具输出或提示词。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.ai.orchestration.graph import build_graph, compile_graph
from apps.ai.orchestration.state import (
    OrchestrationState,
    build_initial_state,
    restore_state_from_task,
    serialize_state,
)
from apps.assistant_tasks import services as task_services
from apps.assistant_tasks.models import AssistantTask, AssistantTaskStatus


class OrchestrationDisabledError(RuntimeError):
    """编排功能被功能开关关闭。"""


def _ensure_enabled() -> None:
    if not getattr(settings, "AI_ORCHESTRATION_ENABLED", False):
        raise OrchestrationDisabledError("AI 助理编排功能未启用")


def _owner_id(therapist: Any) -> int:
    return task_services._owner_id(therapist)


def _save_message(conversation_id: int, role: str, content: str, metadata: dict | None = None):
    """保存一条不可变消息到会话，返回消息对象。"""
    from apps.conversations.models import Message

    return Message.objects.create(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata=metadata or {},
    )


def _run_graph(state: OrchestrationState) -> OrchestrationState:
    """运行一次图，返回最终状态；异常时由调用方降级。"""
    app = compile_graph(build_graph())
    result: OrchestrationState = app.invoke(dict(state))
    return result


def _sync_task_after_graph(task: AssistantTask, state: OrchestrationState) -> AssistantTask:
    """把图产出的安全状态同步回任务，并做必要的状态迁移。"""
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


def handle_turn(
    therapist: Any,
    *,
    message: str,
    conversation_id: int | None = None,
    customer_id: int | None = None,
    customer_name: str = "",
    client_request_id: str = "",
) -> dict[str, Any]:
    """发起一轮对话。

    流程：
    1. 保存用户消息（若有会话）。
    2. 创建或复用统一任务。
    3. 运行编排图。
    4. 同步任务状态，返回可恢复结果。
    """
    _ensure_enabled()
    owner_id = _owner_id(therapist)

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

    state = build_initial_state(
        assistant_task_id=task.id,
        conversation_id=conversation_id,
        customer_id=customer_id,
    )
    state["user_input"] = message
    state["customer_name"] = customer_name

    try:
        result = _run_graph(state)
    except Exception:
        # 图执行失败时降级为失败状态，不伪造客户历史。
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
        )
        raise

    task = _sync_task_after_graph(task, result)
    next_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(next_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=next_node,
        event_type="orchestration_turn_completed",
        event_data={"next_node": next_node, "intent": result.get("intent", "")},
    )

    return _turn_payload(task, result)


def resume_task(therapist: Any, task_id: int, *, message: str = "") -> dict[str, Any]:
    """恢复未完成任务：只接收允许继续的信息，不接受客户端伪造节点/状态。"""
    _ensure_enabled()
    task = task_services.get_owned_task(therapist, task_id)
    if task is None:
        raise task_services.TaskPermissionError("助手任务不存在或无权访问")

    state = restore_state_from_task(task.state_data)
    if message:
        state["user_input"] = message
        if task.conversation_id is not None:
            _save_message(task.conversation_id, "user", message)

    # 恢复前先处理因进程中断而卡在 running 的执行。
    task_services.recover_stale_running_tasks(therapist, task_id)

    # 先把等待状态转回 running，再执行图，最后落到新等待点或终态。
    if task.status in {
        AssistantTaskStatus.WAITING_USER,
        AssistantTaskStatus.WAITING_CONFIRMATION,
        AssistantTaskStatus.BLOCKED,
        AssistantTaskStatus.FAILED,
    }:
        task = task_services.transition_task(
            task,
            AssistantTaskStatus.RUNNING,
            event_type="orchestration_resumed",
        )

    result = _run_graph(state)
    task = _sync_task_after_graph(task, result)
    next_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(next_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=next_node,
        event_type="orchestration_turn_resumed",
        event_data={"next_node": next_node},
    )
    return _turn_payload(task, result)


def submit_customer_selection(therapist: Any, task_id: int, customer_id: int) -> dict[str, Any]:
    """提交同名客户选择：重新校验归属后从中断节点继续。"""
    _ensure_enabled()
    task = task_services.get_owned_task(therapist, task_id)
    if task is None:
        raise task_services.TaskPermissionError("助手任务不存在或无权访问")

    # 校验客户归属。
    customer = task_services._load_customer(therapist, customer_id)
    if customer is None:
        raise task_services.TaskPermissionError("客户不存在或无权访问")

    state = restore_state_from_task(task.state_data)
    state["customer_id"] = customer.id

    # 先把等待状态转回 running，再执行图。
    if task.status in {
        AssistantTaskStatus.WAITING_USER,
        AssistantTaskStatus.WAITING_CONFIRMATION,
        AssistantTaskStatus.BLOCKED,
        AssistantTaskStatus.FAILED,
    }:
        task = task_services.transition_task(
            task,
            AssistantTaskStatus.RUNNING,
            event_type="orchestration_customer_selection_started",
        )

    result = _run_graph(state)
    task = _sync_task_after_graph(task, result)
    next_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(next_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=next_node,
        event_type="orchestration_customer_selected",
        event_data={"next_node": next_node, "customer_id": customer.id},
    )
    return _turn_payload(task, result)


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
    }


__all__ = [
    "handle_turn",
    "resume_task",
    "submit_customer_selection",
    "OrchestrationDisabledError",
]
