"""训练记录 AI 解析与草稿确认服务。

负责：
- 调用 provider 将自然语言解析为结构化草稿。
- 保存原始输入、AI 初始结果。
- 客户识别不确定时提供候选。
- 人工确认后创建正式训练记录。
- 记录 AI 调用审计，避免输出敏感内容到日志。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.ai.models import AiDraft, AiDraftStatus
from apps.ai.providers.base import AIProviderError
from apps.ai.providers.factory import get_provider
from apps.ai.schemas.training import TrainingDraft
from apps.audit.models import AuditAction, write_audit_log
from apps.customers.models import Customer
from apps.training.models import TrainingExercise, TrainingRecord


_TASK_STATUS_ALIASES = {
    # 统一任务的正式状态以 waiting_confirmation 为准；waiting_input 是旧模型兼容值。
    "running": ("running", "in_progress", "processing"),
    "waiting_confirmation": (
        "waiting_confirmation",
        "waiting_input",
        "pending_confirmation",
        "pending",
    ),
    "completed": ("completed", "succeeded"),
    "failed": ("failed",),
    "cancelled": ("cancelled",),
}


def _load_task_services():
    """按需加载统一任务服务，保留旧部署未安装任务 app 时的兼容性。"""
    try:
        from apps.assistant_tasks.services import get_owned_task, transition_task
    except (ImportError, ModuleNotFoundError):
        return None
    return get_owned_task, transition_task


def _task_value(task: Any, *names: str) -> Any:
    """读取任务对象的第一个非空属性，兼容任务模型的枚举值和关联对象。"""
    for name in names:
        value = getattr(task, name, None)
        if value is None or value == "":
            continue
        return getattr(value, "value", value)
    return None


def _as_int(value: Any) -> int | None:
    """将任务上下文中的资源标识安全转换为整数。"""
    if value is None or value == "":
        return None
    try:
        return int(getattr(value, "id", value))
    except (TypeError, ValueError):
        return None


def _nested_context_values(task: Any, keys: tuple[str, ...]) -> list[Any]:
    """从任务状态 JSON 中读取上下文值，不信任客户端嵌套结构。"""
    values: list[Any] = []
    candidates = (
        _task_value(task, "state_data", "context_data", "context", "metadata", "payload"),
    )
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        pending: list[tuple[Mapping[str, Any], int]] = [(candidate, 0)]
        while pending:
            current, depth = pending.pop()
            for key in keys:
                if key in current and current[key] not in (None, ""):
                    values.append(current[key])
            if depth >= 2:
                continue
            for nested in current.values():
                if isinstance(nested, Mapping):
                    pending.append((nested, depth + 1))
    return values


def _task_customer_id(task: Any) -> int | None:
    """读取统一任务绑定的客户 ID。"""
    value = _task_value(task, "customer_id", "customer")
    customer_id = _as_int(value)
    if customer_id is not None:
        return customer_id
    for value in _nested_context_values(task, ("customer_id", "customer")):
        customer_id = _as_int(value)
        if customer_id is not None:
            return customer_id
    return None


def _task_resource_type(task: Any) -> str:
    """读取统一任务当前上下文资源类型。"""
    value = _task_value(task, "context_resource_type", "resource_type")
    if value:
        return str(value).strip().lower()
    for value in _nested_context_values(task, ("context_resource_type", "resource_type")):
        if value:
            return str(value).strip().lower()
    return ""


def _task_course_session_id(task: Any) -> int | None:
    """读取任务绑定的课程排期 ID。"""
    direct = _task_value(task, "course_session_id", "course_session", "session_id")
    course_session_id = _as_int(direct)
    if course_session_id is not None:
        return course_session_id

    resource_type = _task_resource_type(task)
    course_resource_types = {
        "course_session",
        "course-session",
        "course",
        "session",
        "schedule",
        "schedule_session",
    }
    resource_id = _task_value(task, "context_resource_id", "resource_id")
    if resource_id is not None and resource_type in course_resource_types:
        course_session_id = _as_int(resource_id)
        if course_session_id is not None:
            return course_session_id
    for value in _nested_context_values(
        task,
        ("course_session_id", "course_session", "session_id"),
    ):
        course_session_id = _as_int(value)
        if course_session_id is not None:
            return course_session_id
    return None


def _task_status_value(task: Any, semantic_status: str) -> str:
    """按任务模型实际 choices 选择状态值，兼容旧版 waiting_input。"""
    try:
        choices = {
            value
            for value, _label in task._meta.get_field("status").choices
            if value
        }
    except (AttributeError, LookupError):
        choices = set()
    for candidate in _TASK_STATUS_ALIASES.get(semantic_status, (semantic_status,)):
        if not choices or candidate in choices:
            return candidate
    return _TASK_STATUS_ALIASES.get(semantic_status, (semantic_status,))[0]


def _get_owned_training_task(
    therapist: AbstractUser,
    assistant_task_id: int | None,
    *,
    for_update: bool = False,
):
    """获取并校验属于当前康复师的训练补记任务。"""
    if assistant_task_id is None:
        return None
    task_services = _load_task_services()
    if task_services is None:
        raise ValueError("统一任务不存在或无权访问")
    get_owned_task, _transition_task = task_services
    try:
        task = get_owned_task(therapist, assistant_task_id, for_update=for_update)
    except (ObjectDoesNotExist, ValueError):
        task = None
    if task is None:
        raise ValueError("统一任务不存在或无权访问")
    task_type = str(_task_value(task, "task_type", "type") or "").strip().lower()
    if task_type != "training_record":
        raise ValueError("统一任务类型不是训练补记")
    return task


def _transition_training_task(
    task: Any,
    semantic_status: str,
    *,
    current_step: str,
    event_type: str,
    event_data: dict[str, Any] | None = None,
    run: Any = None,
):
    """通过统一任务服务记录训练补记状态转换。"""
    if task is None:
        return None
    task_services = _load_task_services()
    if task_services is None:
        return task
    _get_owned_task, transition_task = task_services
    transitioned = transition_task(
        task,
        _task_status_value(task, semantic_status),
        current_step=current_step,
        event_type=event_type,
        event_data=event_data or {},
        run=run,
    )
    return transitioned or task


def _update_task_resource(
    task: Any,
    *,
    resource_kind: str,
    resource_id: int,
) -> None:
    """更新统一任务的草稿或正式结果资源引用，不覆盖并发状态字段。"""
    if task is None:
        return
    updates: dict[str, Any] = {}
    if resource_kind == "draft" and hasattr(task, "draft_resource_type"):
        updates.update(
            draft_resource_type="ai_draft",
            draft_resource_id=str(resource_id),
        )
    if resource_kind == "result" and hasattr(task, "result_resource_type"):
        updates.update(
            result_resource_type="training_record",
            result_resource_id=str(resource_id),
        )
    if not updates:
        return
    # transition_task 负责状态事件；资源字段属于统一任务的检查点，使用
    # 条件更新并递增版本，避免直接覆盖另一页面刚写入的状态版本。
    now = timezone.now()
    type(task).objects.filter(pk=task.pk).update(
        **updates,
        version=F("version") + 1,
        last_activity_at=now,
        updated_at=now,
    )
    task.version = (task.version or 0) + 1
    task.last_activity_at = now
    task.updated_at = now


def _bind_task_customer(task: Any, customer: Customer | None):
    """在任务尚未绑定客户时，以任务服务的乐观锁规则补齐客户上下文。"""
    if task is None or customer is None or getattr(task, "customer_id", None) == customer.id:
        return task
    if getattr(task, "customer_id", None) is not None:
        raise ValueError("统一任务客户与补记客户不一致")
    task_services = _load_task_services()
    if task_services is None:
        return task
    try:
        from apps.assistant_tasks.services import update_task_state

        return update_task_state(task, task.version, customer=customer)
    except AttributeError:
        # 兼容尚未提供恢复数据服务的旧任务部署；新统一任务 app 必须走上面的
        # 受控更新，以递增 version、更新时间并记录 TaskEvent。
        return task


def _bind_task_course_session(task: Any, course_session_id: int | None):
    """把客户级训练任务收窄到具体排课，并以版本条件防止并发覆盖。"""
    if task is None or course_session_id is None:
        return task
    current_type = str(getattr(task, "context_resource_type", "") or "").strip().lower()
    current_id = str(getattr(task, "context_resource_id", "") or "").strip()
    course_types = {"course_session", "course-session", "course", "session"}
    customer_types = {"customer", "customers"}
    if current_type and current_type not in course_types | customer_types:
        raise ValueError("统一任务上下文资源与补记课程不一致")
    if current_type in course_types:
        if current_id and current_id != str(course_session_id):
            raise ValueError("统一任务课程与补记课程不一致")
        if current_id:
            return task
    # customer -> course_session 是允许的权限收窄；客户一致性已在
    # _validate_task_context 中通过当前康复师和客户归属复核。

    task_services = _load_task_services()
    if task_services is None:
        return task
    try:
        from apps.assistant_tasks.models import TaskEvent
    except (ImportError, ModuleNotFoundError):
        return task

    expected_version = getattr(task, "version", None)
    now = timezone.now()
    updated = type(task).objects.filter(
        pk=task.pk,
        version=expected_version,
    ).update(
        context_resource_type="course_session",
        context_resource_id=str(course_session_id),
        version=F("version") + 1,
        last_activity_at=now,
        updated_at=now,
    )
    if updated != 1:
        raise ValueError("统一任务已被更新，请刷新后重试")
    TaskEvent.objects.create(
        task_id=task.pk,
        event_type="task_context_bound",
        from_status=getattr(task, "status", ""),
        to_status=getattr(task, "status", ""),
        event_data={
            "fields": ["context_resource_type", "context_resource_id"],
            "context_resource_type": "course_session",
            "context_resource_id": str(course_session_id),
            "version": (expected_version or 0) + 1,
        },
    )
    task.context_resource_type = "course_session"
    task.context_resource_id = str(course_session_id)
    task.version = (expected_version or 0) + 1
    task.last_activity_at = now
    task.updated_at = now
    return task


def _validate_customer(therapist: AbstractUser, customer_id: int | None) -> Customer | None:
    """校验客户存在且属于当前康复师。"""
    if customer_id is None:
        return None
    customer = Customer.objects.filter(therapist=therapist, id=customer_id).first()
    if customer is None:
        raise ValueError("所选客户不存在或无权访问")
    return customer


def _get_course_session(
    therapist: AbstractUser,
    customer: Customer | None,
    course_session_id: int | None,
    *,
    for_update: bool = False,
):
    """校验课程排期归属、客户上下文并在需要时加行锁。"""
    if course_session_id is None:
        return None
    from apps.schedules.models import CourseSession

    queryset = CourseSession.objects.filter(therapist=therapist, id=course_session_id)
    if for_update:
        queryset = queryset.select_for_update()
    course_session = queryset.first()
    if course_session is None:
        raise ValueError("关联课程不存在、无权访问或客户不一致")
    if customer is not None and course_session.customer_id != customer.id:
        raise ValueError("训练记录客户与关联课程客户不一致")
    return course_session


def _validate_task_context(
    therapist: AbstractUser,
    task: Any,
    customer_id: int | None,
    course_session_id: int | None,
    *,
    lock_course: bool = False,
) -> tuple[Customer | None, Any, int | None]:
    """复核统一任务、客户和课程上下文，返回规范化资源。"""
    task_customer_id = _task_customer_id(task) if task is not None else None
    if task_customer_id is not None:
        if customer_id is not None and customer_id != task_customer_id:
            raise ValueError("统一任务客户与补记客户不一致")
        customer_id = task_customer_id

    customer = _validate_customer(therapist, customer_id)

    task_course_session_id = _task_course_session_id(task) if task is not None else None
    if (
        task_course_session_id is not None
        and course_session_id is not None
        and task_course_session_id != course_session_id
    ):
        raise ValueError("统一任务课程与补记课程不一致")
    if course_session_id is None:
        course_session_id = task_course_session_id

    course_session = _get_course_session(
        therapist,
        customer,
        course_session_id,
        for_update=lock_course,
    )
    if customer is None and course_session is not None:
        customer = _validate_customer(therapist, course_session.customer_id)
    return customer, course_session, course_session_id


def _start_task_run(
    task: Any,
    *,
    tool_name: str,
    input_summary: dict[str, Any],
    is_write: bool,
    requires_confirmation: bool,
    client_request_id: str = "",
):
    """锁定任务后创建执行记录，避免并发 attempt 和幂等键重复。"""
    if task is None:
        return None, None, True
    try:
        from apps.assistant_tasks.models import (
            AssistantRun,
            AssistantRunStatus,
            ToolExecution,
            ToolExecutionStatus,
        )
    except (ImportError, ModuleNotFoundError):
        return None, None, True

    normalized_request_id = str(client_request_id or "").strip()
    with transaction.atomic():
        type(task).objects.select_for_update().get(pk=task.pk)
        if normalized_request_id:
            existing = AssistantRun.objects.filter(
                task_id=task.pk,
                client_request_id=normalized_request_id,
            ).first()
            if existing is not None:
                return existing, existing.tool_executions.order_by("sequence", "id").first(), False
        if AssistantRun.objects.filter(task_id=task.pk, status=AssistantRunStatus.RUNNING).exists():
            raise ValueError("已有训练内容正在整理，请稍后刷新任务")

        attempt = (
            AssistantRun.objects.filter(task_id=task.pk).aggregate(max_attempt=Max("attempt"))["max_attempt"]
            or 0
        ) + 1
        now = timezone.now()
        run = AssistantRun.objects.create(
            task=task,
            client_request_id=normalized_request_id,
            attempt=attempt,
            status=AssistantRunStatus.RUNNING,
            started_at=now,
            input_summary=input_summary,
        )
        tool = ToolExecution.objects.create(
            run=run,
            task=task,
            sequence=0,
            tool_name=tool_name,
            status=ToolExecutionStatus.RUNNING,
            input_summary=input_summary,
            is_write=is_write,
            requires_confirmation=requires_confirmation,
        )
    return run, tool, True


def _existing_parse_draft(therapist: AbstractUser, task: Any, run: Any) -> AiDraft:
    """解析请求重试时返回首次执行的草稿，不再调用模型或创建新草稿。"""
    from apps.assistant_tasks.models import AssistantRunStatus

    if run.status in {AssistantRunStatus.RUNNING, AssistantRunStatus.QUEUED}:
        raise ValueError("训练内容仍在整理中，请稍后刷新任务")
    draft_id = (run.output_summary or {}).get("draft_id") or getattr(task, "draft_resource_id", "")
    try:
        normalized_id = int(draft_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("原解析请求缺少可恢复草稿，请重新开始补记") from exc
    draft = AiDraft.objects.filter(
        id=normalized_id,
        therapist=therapist,
        assistant_task_id=task.pk,
    ).first()
    if draft is None:
        raise ValueError("原解析请求的草稿不存在，请重新开始补记")
    return draft


def _safe_parse_error(exc: Exception) -> str:
    """将供应商异常转换为不包含原始健康文本的康复师提示。"""
    if isinstance(exc, AIProviderError):
        return "AI 服务暂时无法整理训练内容，请稍后重试"
    if isinstance(exc, ValueError):
        return "训练内容的解析结果不完整，请调整描述后重试"
    return "整理训练内容时发生异常，请稍后重试"


def _finish_task_run(
    run: Any,
    tool: Any,
    *,
    succeeded: bool,
    output_summary: dict[str, Any] | None = None,
    error_code: str = "",
    error_message: str = "",
    confirmed_by: AbstractUser | None = None,
) -> None:
    """完成训练补记 Run/Tool 记录，仅写脱敏结果摘要。"""
    if run is None or tool is None:
        return
    from apps.assistant_tasks.models import AssistantRunStatus, ToolExecutionStatus

    now = timezone.now()
    tool.status = ToolExecutionStatus.SUCCEEDED if succeeded else ToolExecutionStatus.FAILED
    tool.output_summary = output_summary or {}
    tool.error_code = error_code[:64]
    tool.error_message = error_message[:500]
    tool.finished_at = now
    if succeeded and confirmed_by is not None:
        tool.confirmed_by = confirmed_by
        tool.confirmed_at = now
    tool.save(
        update_fields=[
            "status",
            "output_summary",
            "error_code",
            "error_message",
            "finished_at",
            "confirmed_by",
            "confirmed_at",
            "updated_at",
        ]
    )
    run.status = AssistantRunStatus.SUCCEEDED if succeeded else AssistantRunStatus.FAILED
    run.output_summary = output_summary or {}
    run.error_code = error_code[:64]
    run.error_message = error_message[:500]
    run.finished_at = now
    run.save(
        update_fields=[
            "status",
            "output_summary",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )


def parse_training_input(input_text: str) -> TrainingDraft:
    """仅解析并校验训练描述，不创建草稿或正式业务记录。

    固定课程回填入口会先用本函数判断原文是否包含实际完成的项目；只有存在
    可记录内容时才创建 ``AiDraft``，避免把咨询、请假或空泛描述保存为空草稿。
    """
    provider = get_provider()
    raw = provider.parse_training_text(input_text)
    return TrainingDraft(**raw)


def parse_training_draft(
    therapist: AbstractUser,
    input_text: str,
    customer_id: int | None = None,
    assistant_task_id: int | None = None,
    course_session_id: int | None = None,
    client_request_id: str | None = None,
    *,
    parsed_input: TrainingDraft | None = None,
) -> AiDraft:
    """将自然语言解析为待确认 AI 草稿。

    参数：
        therapist: 当前康复师。
        input_text: 自然语言训练描述。
        customer_id: 明确的客户 ID，可空（不确定时后续候选确认）。
        assistant_task_id: 可选统一任务 ID；任务必须属于当前康复师且类型为训练补记。
        course_session_id: 可选课程排期 ID；会与任务中的课程上下文复核。
        parsed_input: 可选的已校验解析结果，供编排节点避免重复调用模型。
    返回：
        新建的 AiDraft 草稿实例（状态 pending 或 failed）。
    """
    task = _get_owned_training_task(therapist, assistant_task_id)
    customer, _course_session, _course_session_id = _validate_task_context(
        therapist,
        task,
        customer_id,
        course_session_id,
    )
    task = _bind_task_customer(task, customer)
    task = _bind_task_course_session(task, _course_session_id)

    run, tool, run_created = _start_task_run(
        task,
        tool_name="create_training_draft",
        input_summary={
            "input_length": len(input_text),
            "customer_id": customer.id if customer is not None else None,
            "course_session_id": _course_session_id,
        },
        is_write=False,
        requires_confirmation=True,
        client_request_id=str(client_request_id or "").strip(),
    )
    if not run_created:
        return _existing_parse_draft(therapist, task, run)

    superseded_draft_ids: list[int] = []
    if task is not None:
        # “重新解析”代表康复师选择以新的描述替换旧草稿。先作废旧的待确认
        # 草稿，避免两个草稿都能被确认成正式记录。
        superseded_draft_ids = list(
            AiDraft.objects.filter(
                therapist=therapist,
                assistant_task_id=task.pk,
                status=AiDraftStatus.PENDING,
            ).values_list("id", flat=True)
        )
        if superseded_draft_ids:
            AiDraft.objects.filter(id__in=superseded_draft_ids).update(status=AiDraftStatus.CANCELLED)
        _transition_training_task(
            task,
            "running",
            current_step="parsing",
            event_type="training_parse_started",
            event_data={
                "customer_id": customer.id if customer is not None else None,
                "superseded_draft_ids": superseded_draft_ids,
            },
            run=run,
        )

    draft = AiDraft.objects.create(
        therapist=therapist,
        customer=customer,
        assistant_task=task,
        status=AiDraftStatus.PENDING,
        input_text=input_text,
    )
    _update_task_resource(task, resource_kind="draft", resource_id=draft.id)

    try:
        parsed = parsed_input or parse_training_input(input_text)
        # 从排课入口回填时，排课日期是可信业务上下文，优先于模型推测的“今天”。
        if _course_session is not None:
            parsed.training_date = _course_session.date.isoformat()
        draft.ai_result = parsed.model_dump()
        draft.status = AiDraftStatus.PENDING
    except Exception as exc:
        draft.status = AiDraftStatus.FAILED
        draft.error_message = _safe_parse_error(exc)
    draft.save(update_fields=["ai_result", "status", "error_message", "updated_at"])

    if task is not None:
        if draft.status == AiDraftStatus.FAILED:
            _finish_task_run(
                run,
                tool,
                succeeded=False,
                output_summary={"draft_id": draft.id, "status": draft.status},
                error_code="training_parse_failed",
                error_message=draft.error_message,
            )
            _transition_training_task(
                task,
                "failed",
                current_step="parsing",
                event_type="training_parse_failed",
                event_data={
                    "draft_id": draft.id,
                    "error_message": draft.error_message,
                    "retryable": True,
                },
                run=run,
            )
        else:
            _finish_task_run(
                run,
                tool,
                succeeded=True,
                output_summary={
                    "draft_id": draft.id,
                    "status": draft.status,
                    "resource_type": "ai_draft",
                    "resource_id": draft.id,
                },
            )
            _transition_training_task(
                task,
                "waiting_confirmation",
                current_step="waiting_confirmation",
                event_type="training_draft_created",
                event_data={
                    "draft_id": draft.id,
                    "resource_type": "ai_draft",
                    "resource_id": draft.id,
                    "draft_resource_type": "ai_draft",
                    "draft_resource_id": draft.id,
                },
                run=run,
            )

    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=draft,
        after={"status": draft.status, "input_length": len(input_text)},
        reason="AI 生成训练草稿",
    )
    return draft


@transaction.atomic
def confirm_training_draft(
    therapist: AbstractUser,
    draft_id: int,
    confirmed: dict,
    customer_id: int | None,
    course_session_id: int | None = None,
    idempotency_key: str | None = None,
) -> AiDraft:
    """人工确认草稿并创建正式训练记录。

    草稿必须属于当前康复师且状态为 pending。确认后创建 TrainingRecord。
    草稿行会先加 ``select_for_update`` 锁；相同幂等键的重试直接返回首次创建的
    正式记录，避免重复训练记录和重复扣课时。

    参数：
        therapist: 当前康复师。
        draft_id: 草稿 ID。
        confirmed: 人工编辑后的最终结果。
        customer_id: 确认的客户 ID。
        course_session_id: 可选关联的课程排期 ID。
        idempotency_key: 确认请求幂等键，可空。
    返回：
        更新为已确认的草稿实例。
    异常：
        ValueError: 草稿不存在、不属于当前康复师或状态不允许确认。
    """
    normalized_key = (idempotency_key or "").strip()
    draft = (
        AiDraft.objects.select_for_update()
        .filter(therapist=therapist, id=draft_id)
        .first()
    )
    if draft is None:
        raise ValueError("草稿不存在或无权访问")

    if draft.status == AiDraftStatus.CONFIRMED:
        # 草稿一旦确认即不可再次生成正式记录。页面刷新后即使客户端丢失了
        # 首次幂等键，只要客户和课程一致，也安全返回原正式结果。
        if draft.training_record_id is None:
            raise ValueError("草稿已确认但缺少正式训练记录")
        if customer_id is not None and draft.customer_id != customer_id:
            raise ValueError("确认客户与已确认草稿客户不一致")
        if course_session_id is not None:
            record = TrainingRecord.objects.filter(id=draft.training_record_id).first()
            if record is not None and record.course_session_id != course_session_id:
                raise ValueError("确认课程与已确认训练记录不一致")
        return draft
    if draft.status != AiDraftStatus.PENDING:
        raise ValueError(f"草稿当前状态不允许确认：{draft.get_status_display()}")

    task = _get_owned_training_task(
        therapist,
        draft.assistant_task_id,
        for_update=True,
    )
    if draft.customer_id is not None and customer_id != draft.customer_id:
        raise ValueError("确认客户与草稿客户不一致")
    customer, course_session, _course_session_id = _validate_task_context(
        therapist,
        task,
        customer_id,
        course_session_id,
        lock_course=True,
    )
    if customer is None:
        raise ValueError("确认客户不能为空")
    task = _bind_task_customer(task, customer)
    task = _bind_task_course_session(task, _course_session_id)
    if course_session is not None and course_session.training_records.exists():
        raise ValueError("该课程已经有正式训练记录")
    if course_session is not None:
        from apps.schedules.models import CourseSessionStatus

        confirmed_date = str(confirmed.get("training_date") or date.today().isoformat())
        if confirmed_date != course_session.date.isoformat():
            raise ValueError("训练日期与所选排课日期不一致，请先调整排课")
        if course_session.status != CourseSessionStatus.SCHEDULED:
            raise ValueError(f"{course_session.get_status_display()}课程不能关联新的训练记录")

    run, tool, _run_created = _start_task_run(
        task,
        tool_name="confirm_training_record",
        input_summary={
            "draft_id": draft.id,
            "customer_id": customer.id,
            "course_session_id": course_session.id if course_session is not None else None,
        },
        is_write=True,
        requires_confirmation=True,
        client_request_id=normalized_key,
    )
    if task is not None:
        _transition_training_task(
            task,
            "running",
            current_step="confirming",
            event_type="training_confirmation_started",
            event_data={"draft_id": draft.id, "customer_id": customer.id},
            run=run,
        )

    confirmed = dict(confirmed)
    if isinstance(confirmed.get("training_date"), date):
        confirmed["training_date"] = confirmed["training_date"].isoformat()

    # 创建正式训练记录
    try:
        # 用 savepoint 将唯一约束冲突转成业务错误，同时保留外层事务可继续回滚。
        with transaction.atomic():
            record = TrainingRecord.objects.create(
                therapist=therapist,
                customer=customer,
                course_session=course_session,
                training_date=confirmed.get("training_date") or date.today().isoformat(),
                customer_feedback=confirmed.get("customer_feedback", ""),
                therapist_observation=confirmed.get("therapist_observation", ""),
                next_plan=confirmed.get("next_plan", ""),
                note=confirmed.get("note", ""),
            )
    except IntegrityError as exc:
        if course_session is not None:
            raise ValueError("该课程已经有正式训练记录") from exc
        raise
    for index, item in enumerate(confirmed.get("exercises", [])):
        TrainingExercise.objects.create(
            training_record=record,
            exercise_name=item.get("exercise_name", ""),
            sets=item.get("sets"),
            reps=item.get("reps"),
            weight=item.get("weight", ""),
            duration_seconds=item.get("duration_seconds"),
            note=item.get("note", ""),
            sort_order=index,
        )

    from apps.courses.services import complete_session_for_record

    complete_session_for_record(therapist, record)

    # 更新草稿状态与确认结果
    draft.status = AiDraftStatus.CONFIRMED
    draft.confirmed_result = confirmed
    draft.customer = customer
    draft.training_record = record
    if normalized_key:
        draft.confirmation_key = normalized_key
    draft.confirmed_at = timezone.now()
    draft.save(
        update_fields=[
            "status",
            "confirmed_result",
            "customer",
            "training_record",
            "confirmation_key",
            "confirmed_at",
            "updated_at",
        ]
    )

    if task is not None:
        transitioned_task = _transition_training_task(
            task,
            "completed",
            current_step="completed",
            event_type="training_confirmation_completed",
            event_data={
                "draft_id": draft.id,
                "resource_type": "training_record",
                "resource_id": record.id,
                "result_resource_type": "training_record",
                "result_resource_id": record.id,
            },
            run=run,
        )
        _update_task_resource(
            transitioned_task,
            resource_kind="result",
            resource_id=record.id,
        )
    _finish_task_run(
        run,
        tool,
        succeeded=True,
        output_summary={
            "training_record_id": record.id,
            "resource_type": "training_record",
            "resource_id": record.id,
        },
        confirmed_by=therapist,
    )

    write_audit_log(
        actor=therapist,
        action=AuditAction.CONFIRM,
        obj=record,
        after={"draft_id": draft.id, "customer_id": customer.id},
        reason="AI 草稿确认创建训练记录",
    )
    return draft


@transaction.atomic
def cancel_draft(therapist: AbstractUser, draft_id: int) -> AiDraft:
    """取消 AI 草稿，不创建正式记录。

    参数：
        therapist: 当前康复师。
        draft_id: 草稿 ID。
    返回：
        已取消的草稿实例。
    异常：
        ValueError: 草稿不存在、不属于当前康复师或状态不允许取消。
    """
    draft = (
        AiDraft.objects.select_for_update()
        .filter(therapist=therapist, id=draft_id)
        .first()
    )
    if draft is None:
        raise ValueError("草稿不存在或无权访问")
    if draft.status == AiDraftStatus.CONFIRMED:
        raise ValueError("已确认的草稿不能取消")

    task = _get_owned_training_task(
        therapist,
        draft.assistant_task_id,
        for_update=True,
    )
    if task is not None and str(getattr(task, "status", "")) not in {
        "completed",
        "succeeded",
        "cancelled",
        "expired",
    }:
        _transition_training_task(
            task,
            "cancelled",
            current_step="cancelled",
            event_type="training_draft_cancelled",
            event_data={"draft_id": draft.id},
        )
    draft.status = AiDraftStatus.CANCELLED
    draft.save(update_fields=["status", "updated_at"])
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=draft,
        after={"status": draft.status, "assistant_task_id": draft.assistant_task_id},
        reason="取消 AI 训练草稿",
    )
    return draft


def suggest_customer_candidates(therapist: AbstractUser, name_hint: str) -> list[dict]:
    """按姓名提示返回客户候选列表。

    当草稿未明确客户或识别不确定时，供前端选择。

    参数：
        therapist: 当前康复师。
        name_hint: 客户姓名提示。
    返回：
        候选客户字典列表（含 id、name、phone_masked）。
    """
    candidates = Customer.objects.filter(therapist=therapist).filter(name__icontains=name_hint or "")[:10]
    return [
        {"id": c.id, "name": c.name, "phone_masked": c.phone_masked}
        for c in candidates
    ]
