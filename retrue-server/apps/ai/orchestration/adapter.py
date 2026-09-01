"""图节点转换与 AssistantTask / TaskEvent / AssistantRun 的同步适配器。

LangGraph 节点只产生“进入哪个节点、分支原因、下一步”等编排事实；这些事实
通过本适配器同步到任务领域表，作为可恢复、可审计的权威记录。适配器不直接
写任何客户业务表，也不保存提示词或原始对话。

同步内容：
1. ``AssistantTask.current_step``、``missing_fields``、安全的 ``state_data``；
2. ``TaskEvent``（含节点、分支原因、Run ID、脱敏摘要）；
3. 节点转换导致的 ``AssistantRun`` 状态变化（由 service 层完成）。
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.assistant_tasks.models import (
    AssistantRun,
    AssistantTask,
    TaskEvent,
)
from apps.ai.orchestration.state import OrchestrationState, serialize_state


def sync_node_event(
    task: AssistantTask,
    *,
    node_name: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    run: AssistantRun | None = None,
) -> TaskEvent:
    """为一次节点转换写入不可变 TaskEvent，并返回该事件。

    事件数据只保留节点名、分支原因等脱敏摘要，绝不写入用户输入或工具结果。
    """
    payload: dict[str, Any] = {"node": str(node_name)[:128]}
    if event_data:
        payload.update({str(k): v for k, v in event_data.items()})
    return TaskEvent.objects.create(
        task=task,
        run=run,
        actor_id=task.therapist_id,
        event_type=str(event_type)[:64],
        from_status=task.status,
        to_status=task.status,
        event_data=payload,
    )


def sync_state(
    task: AssistantTask,
    state: OrchestrationState,
    *,
    run: AssistantRun | None = None,
) -> AssistantTask:
    """把图状态的安全白名单字段同步到任务的可恢复字段。

    状态数据经 ``serialize_state`` 白名单过滤后写入；任务状态迁移本身仍由
    ``apps.assistant_tasks.services`` 的状态机负责，这里不越权改状态。
    """
    task.current_step = str(state.get("next_node") or state.get("intent") or "")
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
    TaskEvent.objects.create(
        task=task,
        run=run,
        actor_id=task.therapist_id,
        event_type="orchestration_state_synced",
        from_status=task.status,
        to_status=task.status,
        event_data={
            "node": str(state.get("next_node") or "")[:128],
            "version": task.version,
        },
    )
    return task


__all__ = ["sync_node_event", "sync_state"]
