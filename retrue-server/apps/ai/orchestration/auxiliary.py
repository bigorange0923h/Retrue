"""复用 AssistantTask 持久排队辅助记忆评估，回复链路只排队、不等待模型。"""

from langgraph.graph import END, START, StateGraph
from django.db import transaction
from django.utils import timezone

from apps.ai.orchestration.state import OrchestrationState, build_initial_state
from apps.assistant_tasks import services
from apps.assistant_tasks.models import AssistantTask, AssistantTaskStatus


def enqueue_memory(state):
    """仅为归属一致的原始用户消息排队，同一来源幂等复用任务。"""
    from apps.conversations.models import Message
    source_task = AssistantTask.objects.filter(pk=state.get("assistant_task_id")).first()
    if source_task is None or not state.get("customer_id"):
        return {}
    message = Message.objects.filter(
        pk=state.get("user_message_id"), role="user",
        conversation_id=state.get("conversation_id"),
        conversation__therapist_id=source_task.therapist_id,
        conversation__customer_id=state.get("customer_id"),
    ).first()
    if message is None:
        return {}
    services.create_task(
        source_task.therapist_id, customer=state["customer_id"], conversation=state["conversation_id"],
        task_type="memory_evaluation", origin="deferred_memory", skill_code="memory_evaluation",
        client_request_id=f"memory-source:{message.id}", status=AssistantTaskStatus.PENDING,
        state_data={"resource_refs": {"user_message_id": message.id}},
    )
    return {}


def process_memory_task(task_id):
    """抢占一次执行，失败可重试；进程重启后已排队任务仍在数据库中。"""
    from apps.ai.orchestration import nodes
    from apps.ai.orchestration.execution import execution_scope
    from apps.ai.orchestration.service import _start_run, _finalize_attempt
    with transaction.atomic():
        task = AssistantTask.objects.select_for_update().get(pk=task_id, origin="deferred_memory")
        services.recover_stale_running_tasks(task.therapist_id, task.id)
        task.refresh_from_db()
        if task.status not in {AssistantTaskStatus.PENDING, AssistantTaskStatus.FAILED}:
            return False
        if task.runs.count() >= 3:
            services.transition_task(task, AssistantTaskStatus.BLOCKED, current_step="auxiliary_retry_exhausted",
                                     event_type="auxiliary_retry_exhausted")
            return False
        task = services.transition_task(task, AssistantTaskStatus.RUNNING, event_type="auxiliary_started")
        run = _start_run(task)
    state = build_initial_state(
        assistant_task_id=task.id, conversation_id=task.conversation_id, customer_id=task.customer_id,
    )
    state["user_message_id"] = (task.state_data.get("resource_refs") or {}).get("user_message_id")
    graph = StateGraph(OrchestrationState)
    graph.add_node("evaluate_memory", nodes.evaluate_memory_node)
    graph.add_edge(START, "evaluate_memory")
    graph.add_edge("evaluate_memory", END)
    try:
        with execution_scope(run):
            result = graph.compile().invoke(state)
        _finalize_attempt(task, run, result, event_type="auxiliary_completed")
    except Exception as exc:
        _finalize_attempt(task, run, error=exc, event_type="auxiliary_failed")
        return False
    return True


def process_pending_memory(limit=20):
    """一次处理有限任务，失败退避一分钟；可由定时命令持续消费，无需新服务。"""
    from datetime import timedelta
    from django.db.models import Q
    cutoff = timezone.now() - timedelta(minutes=1)
    ids = list(AssistantTask.objects.filter(origin="deferred_memory").filter(
        Q(status=AssistantTaskStatus.PENDING)
        | Q(status=AssistantTaskStatus.FAILED, updated_at__lt=cutoff)
        | Q(status=AssistantTaskStatus.RUNNING, last_activity_at__lt=cutoff),
    ).order_by("id").values_list("id", flat=True)[:max(1, min(limit, 100))])
    return sum(process_memory_task(task_id) for task_id in ids)
