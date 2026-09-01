"""AssistantTask 通用领域服务。

本模块负责任务的幂等创建、康复师数据隔离、关联资源归属校验和生命周期
状态机。具体技能如何调用模型、使用什么提示词，应由上层技能适配器负责，
这里不依赖也不保存任何提示词。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
import json
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.assistant_tasks.models import (
    AssistantRun,
    AssistantRunStatus,
    AssistantTask,
    AssistantTaskStatus,
    TaskEvent,
    ToolExecutionStatus,
)


# 只有这些资源允许作为 AssistantTask 的上下文资源；新增资源类型时必须同步
# 补充归属校验，不能因客户端传入任意字符串而绕开数据隔离。
RESOURCE_TYPE_ALIASES = {
    "customer": "customer",
    "customers": "customer",
    "course_session": "course_session",
    "course-session": "course_session",
    "course_sessions": "course_session",
    "course-sessions": "course_session",
    "coursesession": "course_session",
    "assessment": "assessment",
    "assessments": "assessment",
    "training_record": "training_record",
    "training-record": "training_record",
    "training_records": "training_record",
    "training-records": "training_record",
    "trainingrecord": "training_record",
}

TASK_TERMINAL_STATUSES = {
    AssistantTaskStatus.COMPLETED,
    AssistantTaskStatus.CANCELLED,
    AssistantTaskStatus.EXPIRED,
}
TASK_UNFINISHED_STATUSES = {
    AssistantTaskStatus.PENDING,
    AssistantTaskStatus.RUNNING,
    AssistantTaskStatus.WAITING_USER,
    AssistantTaskStatus.WAITING_CONFIRMATION,
    AssistantTaskStatus.BLOCKED,
    AssistantTaskStatus.FAILED,
}
TASK_RESUMABLE_STATUSES = {
    AssistantTaskStatus.PENDING,
    AssistantTaskStatus.RUNNING,
    AssistantTaskStatus.WAITING_USER,
    AssistantTaskStatus.WAITING_CONFIRMATION,
    AssistantTaskStatus.BLOCKED,
    AssistantTaskStatus.FAILED,
}
TASK_ALLOWED_STATUSES = TASK_TERMINAL_STATUSES | TASK_UNFINISHED_STATUSES
MAX_STATE_DATA_BYTES = 16 * 1024
FORBIDDEN_STATE_KEYS = {
    "input_text",
    "raw_input",
    "original_text",
    "message_content",
    "draft",
    "ai_draft",
    "medical_history",
    "phone",
}


class TaskBusinessError(ValueError):
    """助手任务领域错误基类。"""

    code = "task_invalid"
    http_status = 400

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        if error_code:
            self.code = error_code


class TaskPermissionError(TaskBusinessError):
    """当前康复师无权访问任务或其关联资源。"""

    code = "task_forbidden"
    http_status = 403


class ResourceOwnershipError(TaskPermissionError):
    """任务上下文资源不属于当前康复师。"""

    code = "resource_forbidden"


class ResourceValidationError(TaskBusinessError):
    """任务上下文资源类型、标识或客户一致性校验失败。"""

    code = "resource_invalid"


class TaskTransitionError(TaskBusinessError):
    """任务状态不能按当前生命周期规则转换。"""

    code = "invalid_task_transition"


class TaskVersionConflict(TaskBusinessError):
    """客户端使用旧版本更新任务状态数据。"""

    code = "task_version_conflict"
    http_status = 409


class TaskIdempotencyConflict(TaskBusinessError):
    """同一幂等键被用于不同任务上下文。"""

    code = "task_idempotency_conflict"
    http_status = 409


def _validate_state_data(value: Any) -> dict[str, Any]:
    """限制恢复 JSON 的大小并拒绝保存原始健康文本或完整草稿。"""
    if not isinstance(value, dict):
        raise ResourceValidationError("state_data 必须是对象", error_code="state_data_invalid")

    pending: list[Any] = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                normalized_key = str(key).strip().lower()
                if normalized_key in FORBIDDEN_STATE_KEYS:
                    raise ResourceValidationError(
                        "state_data 只能保存恢复摘要和资源标识",
                        error_code="state_data_sensitive_field",
                    )
                pending.append(item)
        elif isinstance(current, list):
            pending.extend(current)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResourceValidationError("state_data 必须是合法 JSON", error_code="state_data_invalid") from exc
    if len(encoded) > MAX_STATE_DATA_BYTES:
        raise ResourceValidationError(
            f"state_data 不能超过 {MAX_STATE_DATA_BYTES // 1024}KB",
            error_code="state_data_too_large",
        )
    return value


def _ensure_reusable_task(
    existing: AssistantTask,
    *,
    customer_id: int | None,
    conversation_id: int | None,
    task_type: str,
    skill_code: str,
    context_resource_type: str,
    context_resource_id: str,
    business_key: str,
    compare_conversation: bool,
) -> AssistantTask:
    """幂等复用前核对任务指纹，禁止同一键静默切换客户或资源。"""
    expected = {
        "customer_id": customer_id,
        "task_type": task_type,
        "skill_code": skill_code,
        "context_resource_type": context_resource_type,
        "context_resource_id": context_resource_id,
    }
    actual = {key: getattr(existing, key) for key in expected}
    if compare_conversation:
        expected["conversation_id"] = conversation_id
        expected["business_key"] = business_key
        actual["conversation_id"] = existing.conversation_id
        actual["business_key"] = existing.business_key
    if actual != expected:
        raise TaskIdempotencyConflict("同一请求标识已用于其他客户或业务上下文")
    return existing


def _owner_id(therapist: Any) -> int:
    """解析康复师用户主键，兼容 User 与 Therapist 身份对象。"""
    if therapist is None:
        raise TaskPermissionError("缺少康复师身份", error_code="therapist_required")
    # Therapist 模型通过 user_id 指向 accounts.User；API 默认传入的则是 User。
    if hasattr(therapist, "user_id") and not hasattr(therapist, "is_authenticated"):
        value = therapist.user_id
    else:
        value = getattr(therapist, "pk", therapist)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TaskPermissionError("康复师身份无效", error_code="therapist_invalid") from exc


def _object_id(value: Any, field_name: str) -> int:
    """读取资源或客户对象的整数主键。"""
    raw = getattr(value, "pk", value)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ResourceValidationError(
            f"{field_name} 标识无效",
            error_code="resource_id_invalid",
        ) from exc


def _resource_type(value: str | None) -> str:
    """标准化并校验上下文资源类型。"""
    normalized = str(value or "").strip().lower().replace(" ", "_")
    canonical = RESOURCE_TYPE_ALIASES.get(normalized)
    if canonical is None:
        raise ResourceValidationError(
            "不支持的上下文资源类型",
            error_code="resource_type_not_allowed",
        )
    return canonical


def validate_resource_ownership(
    therapist: Any,
    resource_type: str | None = "",
    resource_id: Any = "",
    customer: Any = None,
    *,
    context_resource_type: str | None = None,
    context_resource_id: Any = None,
    expected_customer: Any = None,
) -> Any:
    """校验任务上下文资源的白名单、康复师归属和客户一致性。

    参数：
        therapist: 当前康复师用户或 Therapist 身份对象。
        resource_type/resource_id: 资源类型和业务主键；支持 customer、
            course_session、assessment、training_record。
        customer: 可选的任务客户对象或客户主键，用于一致性校验。
        context_resource_type/context_resource_id: 与字段名一致的可选别名，
            便于服务调用方直接传入任务上下文字典。
        expected_customer: ``customer`` 参数的兼容别名。
    返回：
        通过校验的资源对象；未提供资源时返回 None。
    异常：
        ResourceOwnershipError: 资源不属于当前康复师。
        ResourceValidationError: 类型不在白名单、资源不存在或客户不一致。
    """
    if context_resource_type is not None:
        resource_type = context_resource_type
    if context_resource_id is not None:
        resource_id = context_resource_id
    if customer is None and expected_customer is not None:
        customer = expected_customer

    raw_type = str(resource_type or "").strip()
    raw_id = "" if resource_id is None else str(getattr(resource_id, "pk", resource_id)).strip()
    if not raw_type and not raw_id:
        return None
    if not raw_type or not raw_id:
        raise ResourceValidationError(
            "上下文资源类型和标识必须同时提供",
            error_code="resource_reference_incomplete",
        )

    canonical_type = _resource_type(raw_type)
    try:
        resource_pk = _object_id(raw_id, "资源")
    except ResourceValidationError:
        raise

    # 延迟导入可避免跨业务域模型在 Django 初始化阶段形成循环依赖。
    from apps.assessments.models import Assessment
    from apps.customers.models import Customer
    from apps.schedules.models import CourseSession
    from apps.training.models import TrainingRecord

    resource_models = {
        "customer": Customer,
        "course_session": CourseSession,
        "assessment": Assessment,
        "training_record": TrainingRecord,
    }
    model = resource_models[canonical_type]
    resource = model.objects.filter(pk=resource_pk).first()
    if resource is None:
        raise ResourceValidationError("关联资源不存在", error_code="resource_not_found")

    owner_id = _owner_id(therapist)
    if getattr(resource, "therapist_id", None) != owner_id:
        # 对外统一表现为无权，避免通过错误信息枚举其他康复师的数据。
        raise ResourceOwnershipError("关联资源不存在或无权访问")

    expected_customer_id = None if customer is None else _object_id(customer, "客户")
    resource_customer_id = resource.pk if canonical_type == "customer" else getattr(resource, "customer_id", None)
    if expected_customer_id is not None and resource_customer_id != expected_customer_id:
        raise ResourceValidationError(
            "任务客户与关联资源客户不一致",
            error_code="resource_customer_mismatch",
        )
    return resource


def _load_customer(therapist: Any, customer: Any) -> Any:
    """加载并校验任务客户。"""
    if customer is None:
        return None
    from apps.customers.models import Customer

    customer_pk = _object_id(customer, "客户")
    instance = customer if isinstance(customer, Customer) else Customer.objects.filter(pk=customer_pk).first()
    if instance is None:
        raise ResourceValidationError("客户不存在", error_code="customer_not_found")
    if instance.therapist_id != _owner_id(therapist):
        raise TaskPermissionError("客户不存在或无权访问", error_code="customer_forbidden")
    return instance


def _load_conversation(therapist: Any, conversation: Any) -> Any:
    """加载并校验任务会话归属。"""
    if conversation is None:
        return None
    from apps.conversations.models import Conversation

    conversation_pk = _object_id(conversation, "会话")
    instance = (
        conversation
        if isinstance(conversation, Conversation)
        else Conversation.objects.filter(pk=conversation_pk).first()
    )
    if instance is None:
        raise ResourceValidationError("会话不存在", error_code="conversation_not_found")
    if instance.therapist_id != _owner_id(therapist):
        raise TaskPermissionError("会话不存在或无权访问", error_code="conversation_forbidden")
    return instance


def _validate_status(status: str | AssistantTaskStatus) -> str:
    """校验任务状态并转换为字符串值。"""
    value = getattr(status, "value", status)
    value = str(value)
    if value not in TASK_ALLOWED_STATUSES:
        raise TaskBusinessError("不支持的任务状态", error_code="task_status_invalid")
    return value


def _resource_customer(resource: Any, resource_type: str) -> Any:
    """从通过校验的上下文资源取得客户对象。"""
    if resource is None:
        return None
    if resource_type == "customer":
        return resource
    customer_id = getattr(resource, "customer_id", None)
    if customer_id is None:
        return None
    return resource.customer


def create_task(
    therapist: Any,
    *,
    customer: Any = None,
    conversation: Any = None,
    skill_code: str = "",
    task_type: str = "",
    invocation_mode: str = "manual",
    origin: str = "",
    context_resource_type: str = "",
    context_resource_id: Any = "",
    business_key: str = "",
    client_request_id: str = "",
    status: str | AssistantTaskStatus = AssistantTaskStatus.PENDING,
    current_step: str = "",
    missing_fields: list[Any] | None = None,
    state_data: dict[str, Any] | None = None,
    draft_resource_type: str = "",
    draft_resource_id: Any = "",
    result_resource_type: str = "",
    result_resource_id: Any = "",
    expires_at: Any = None,
    **aliases: Any,
) -> AssistantTask:
    """创建或复用一个助手任务，并记录任务创建事件。

    参数：
        therapist: 当前康复师用户或身份对象。
        client_request_id: 同一康复师范围内的客户端幂等键，已存在时原样复用。
        business_key: 同一康复师和客户范围内未完成任务的业务复用键。
        customer/conversation/context_resource_*: 任务上下文，均执行归属校验。
        skill_code/task_type/invocation_mode/origin: 由调用方定义的技能和入口分类，
            服务层不内置提示词或业务文案。
        aliases: 兼容 ``draft_resource_ref``、``result_resource_ref`` 等调用方字典。
    返回：
        新建或幂等复用的 AssistantTask 实例。
    异常：
        TaskBusinessError: 参数、归属、状态或关联资源不合法。
    """
    owner_id = _owner_id(therapist)

    # 一些编排器会以 {type, id} 形式传递资源引用；在这里仅做结构拆解，
    # 不把引用解释成具体业务动作。
    draft_ref = aliases.pop("draft_resource_ref", None)
    result_ref = aliases.pop("result_resource_ref", None)
    idempotency_alias = aliases.pop("idempotency_key", "")
    if not client_request_id:
        client_request_id = idempotency_alias
    if customer is None and "customer_id" in aliases:
        customer = aliases.pop("customer_id")
    if conversation is None and "conversation_id" in aliases:
        conversation = aliases.pop("conversation_id")
    context_ref = aliases.pop("context_resource", None)
    if isinstance(context_ref, dict):
        context_resource_type = context_ref.get("type", context_resource_type)
        context_resource_id = context_ref.get("id", context_resource_id)
    if not context_resource_type:
        context_resource_type = aliases.pop("resource_type", context_resource_type)
    if not context_resource_id:
        context_resource_id = aliases.pop("resource_id", context_resource_id)
    if draft_ref and isinstance(draft_ref, dict):
        draft_resource_type = draft_ref.get("type", draft_resource_type)
        draft_resource_id = draft_ref.get("id", draft_resource_id)
    if result_ref and isinstance(result_ref, dict):
        result_resource_type = result_ref.get("type", result_resource_type)
        result_resource_id = result_ref.get("id", result_resource_id)
    if aliases:
        unknown = next(iter(aliases))
        raise TypeError(f"create_task() got an unexpected keyword argument '{unknown}'")

    customer_instance = _load_customer(therapist, customer)
    conversation_instance = _load_conversation(therapist, conversation)
    if conversation_instance is not None:
        if (
            customer_instance is not None
            and conversation_instance.customer_id is not None
            and conversation_instance.customer_id != customer_instance.id
        ):
            raise ResourceValidationError(
                "任务客户与会话客户不一致",
                error_code="conversation_customer_mismatch",
            )
        if customer_instance is None and conversation_instance.customer_id is not None:
            customer_instance = _load_customer(therapist, conversation_instance.customer_id)

    raw_context_type = str(context_resource_type or "").strip()
    canonical_context_type = "" if not raw_context_type else _resource_type(raw_context_type)
    resource = validate_resource_ownership(
        therapist,
        canonical_context_type,
        context_resource_id,
        customer_instance,
    )
    if customer_instance is None and resource is not None:
        customer_instance = _resource_customer(resource, canonical_context_type)

    normalized_client_request_id = str(client_request_id or "").strip()
    normalized_business_key = str(business_key or "").strip()
    normalized_task_type = str(task_type or "").strip()
    normalized_skill_code = str(skill_code or "").strip()
    normalized_context_id = "" if context_resource_id is None else str(context_resource_id).strip()
    normalized_state_data = _validate_state_data({} if state_data is None else state_data)
    normalized_status = _validate_status(status)
    if normalized_status in TASK_TERMINAL_STATUSES:
        raise TaskBusinessError(
            "新建任务不能直接使用结束状态",
            error_code="task_initial_status_invalid",
        )

    def _create_in_transaction() -> AssistantTask:
        """在事务中执行幂等查找、创建和事件记录。"""
        if normalized_client_request_id:
            existing = (
                AssistantTask.objects.select_for_update()
                .filter(therapist_id=owner_id, client_request_id=normalized_client_request_id)
                .first()
            )
            if existing is not None:
                return _ensure_reusable_task(
                    existing,
                    customer_id=getattr(customer_instance, "id", None),
                    conversation_id=getattr(conversation_instance, "id", None),
                    task_type=normalized_task_type,
                    skill_code=normalized_skill_code,
                    context_resource_type=canonical_context_type,
                    context_resource_id=normalized_context_id,
                    business_key=normalized_business_key,
                    compare_conversation=True,
                )

        if normalized_business_key:
            # 业务键要和客户上下文一起判断，避免同一康复师为不同客户的任务
            # 因为一个过于宽泛的业务键而互相复用。
            business_queryset = AssistantTask.objects.select_for_update().filter(
                therapist_id=owner_id,
                business_key=normalized_business_key,
                status__in=TASK_UNFINISHED_STATUSES,
            )
            if customer_instance is None:
                business_queryset = business_queryset.filter(customer__isnull=True)
            else:
                business_queryset = business_queryset.filter(customer_id=customer_instance.id)
            existing = business_queryset.order_by("id").first()
            if existing is not None:
                return _ensure_reusable_task(
                    existing,
                    customer_id=getattr(customer_instance, "id", None),
                    conversation_id=getattr(conversation_instance, "id", None),
                    task_type=normalized_task_type,
                    skill_code=normalized_skill_code,
                    context_resource_type=canonical_context_type,
                    context_resource_id=normalized_context_id,
                    business_key=normalized_business_key,
                    compare_conversation=False,
                )

        task = AssistantTask.objects.create(
            therapist_id=owner_id,
            customer=customer_instance,
            conversation=conversation_instance,
            skill_code=normalized_skill_code,
            task_type=normalized_task_type,
            invocation_mode=str(invocation_mode or "manual").strip() or "manual",
            origin=str(origin or "").strip(),
            context_resource_type=canonical_context_type,
            context_resource_id=normalized_context_id,
            business_key=normalized_business_key,
            client_request_id=normalized_client_request_id,
            status=normalized_status,
            current_step=str(current_step or ""),
            missing_fields=[] if missing_fields is None else missing_fields,
            state_data=normalized_state_data,
            draft_resource_type=str(draft_resource_type or "").strip(),
            draft_resource_id="" if draft_resource_id is None else str(draft_resource_id).strip(),
            result_resource_type=str(result_resource_type or "").strip(),
            result_resource_id="" if result_resource_id is None else str(result_resource_id).strip(),
            expires_at=expires_at,
            last_activity_at=timezone.now(),
        )
        TaskEvent.objects.create(
            task=task,
            actor_id=owner_id,
            event_type="task_created",
            to_status=task.status,
            event_data={
                "business_key": task.business_key,
                "client_request_id": task.client_request_id,
            },
        )
        return task

    try:
        with transaction.atomic():
            return _create_in_transaction()
    except IntegrityError:
        # 并发请求可能同时看不到幂等键；唯一约束负责仲裁，获胜事务提交后
        # 再读取其任务即可，调用方仍得到幂等结果而不是数据库异常。
        if normalized_client_request_id:
            existing = AssistantTask.objects.filter(
                therapist_id=owner_id,
                client_request_id=normalized_client_request_id,
            ).first()
            if existing is not None:
                return _ensure_reusable_task(
                    existing,
                    customer_id=getattr(customer_instance, "id", None),
                    conversation_id=getattr(conversation_instance, "id", None),
                    task_type=normalized_task_type,
                    skill_code=normalized_skill_code,
                    context_resource_type=canonical_context_type,
                    context_resource_id=normalized_context_id,
                    business_key=normalized_business_key,
                    compare_conversation=True,
                )
        if normalized_business_key:
            existing = AssistantTask.objects.filter(
                therapist_id=owner_id,
                customer_id=getattr(customer_instance, "id", None),
                business_key=normalized_business_key,
                status__in=TASK_UNFINISHED_STATUSES,
            ).order_by("id").first()
            if existing is not None:
                return _ensure_reusable_task(
                    existing,
                    customer_id=getattr(customer_instance, "id", None),
                    conversation_id=getattr(conversation_instance, "id", None),
                    task_type=normalized_task_type,
                    skill_code=normalized_skill_code,
                    context_resource_type=canonical_context_type,
                    context_resource_id=normalized_context_id,
                    business_key=normalized_business_key,
                    compare_conversation=False,
                )
        raise


def get_owned_task(therapist: Any, task_id: Any, for_update: bool = False) -> AssistantTask | None:
    """获取当前康复师拥有的任务。

    参数：
        therapist: 当前康复师用户或身份对象。
        task_id: 任务主键。
        for_update: 是否在当前事务中锁定任务行，供训练接入的状态更新使用。
    返回：
        所属当前康复师的任务；不存在或无权访问时返回 None。
    """
    try:
        owner_id = _owner_id(therapist)
        task_pk = _object_id(task_id, "任务")
    except (TaskBusinessError, ResourceValidationError):
        return None
    queryset = AssistantTask.objects.filter(pk=task_pk, therapist_id=owner_id)
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first()


def recover_stale_running_tasks(therapist: Any, task_id: Any = None) -> int:
    """把因进程中断而长期停留在 running 的执行恢复为可重试失败状态。"""
    owner_id = _owner_id(therapist)
    timeout_seconds = max(int(getattr(settings, "AI_TIMEOUT", 60)) + 30, 90)
    cutoff = timezone.now() - timedelta(seconds=timeout_seconds)
    queryset = AssistantTask.objects.filter(
        therapist_id=owner_id,
        status=AssistantTaskStatus.RUNNING,
        last_activity_at__lt=cutoff,
    )
    if task_id is not None:
        try:
            queryset = queryset.filter(pk=_object_id(task_id, "任务"))
        except ResourceValidationError:
            return 0

    recovered = 0
    for candidate_id in queryset.values_list("id", flat=True)[:100]:
        with transaction.atomic():
            task = AssistantTask.objects.select_for_update().filter(
                pk=candidate_id,
                therapist_id=owner_id,
                status=AssistantTaskStatus.RUNNING,
                last_activity_at__lt=cutoff,
            ).first()
            if task is None:
                continue
            run = task.runs.filter(status=AssistantRunStatus.RUNNING).order_by("-started_at", "-id").first()
            if run is not None and (run.started_at is None or run.started_at >= cutoff):
                continue

            now = timezone.now()
            if run is not None:
                run.tool_executions.filter(
                    status__in=[ToolExecutionStatus.PENDING, ToolExecutionStatus.RUNNING]
                ).update(
                    status=ToolExecutionStatus.FAILED,
                    error_code="execution_timed_out",
                    error_message="执行中断，可安全重试",
                    finished_at=now,
                    updated_at=now,
                )
                run.status = AssistantRunStatus.TIMED_OUT
                run.error_code = "execution_timed_out"
                run.error_message = "执行中断，可安全重试"
                run.finished_at = now
                run.save(
                    update_fields=["status", "error_code", "error_message", "finished_at", "updated_at"]
                )

            # 解析在模型返回前已经创建空草稿；异常中断时不能把空草稿呈现为可确认。
            try:
                from apps.ai.models import AiDraft, AiDraftStatus

                AiDraft.objects.filter(
                    assistant_task_id=task.id,
                    status=AiDraftStatus.PENDING,
                    ai_result={},
                ).update(
                    status=AiDraftStatus.FAILED,
                    error_message="整理过程意外中断，请重新提交训练描述",
                    updated_at=now,
                )
            except (ImportError, ModuleNotFoundError):
                pass

            transition_task(
                task,
                AssistantTaskStatus.FAILED,
                current_step="execution_interrupted",
                event_type="execution_timed_out",
                event_data={"retryable": True},
                run=run,
            )
            recovered += 1
    return recovered


def list_owned_tasks(
    therapist: Any,
    *,
    customer: Any = None,
    status: str | Iterable[str] | None = None,
    resumable: bool | None = None,
) -> QuerySet[AssistantTask]:
    """查询当前康复师的任务列表，并应用客户、状态和可恢复筛选。

    参数：
        therapist: 当前康复师用户或身份对象。
        customer: 可选客户对象或客户主键；会先校验客户归属。
        status: 单个状态、逗号分隔状态或状态可迭代对象。
        resumable: 为 True 时仅返回可恢复任务，为 False 时排除可恢复任务。
    返回：
        按更新时间倒序排列的 AssistantTask QuerySet。
    """
    owner_id = _owner_id(therapist)
    queryset = AssistantTask.objects.filter(therapist_id=owner_id)
    if customer is not None:
        customer_instance = _load_customer(therapist, customer)
        queryset = queryset.filter(customer_id=customer_instance.id)
    if status is not None:
        if isinstance(status, str):
            statuses = [item.strip() for item in status.split(",") if item.strip()]
        else:
            statuses = [str(getattr(item, "value", item)) for item in status]
        invalid = set(statuses) - TASK_ALLOWED_STATUSES
        if invalid:
            raise TaskBusinessError("不支持的任务状态", error_code="task_status_invalid")
        queryset = queryset.filter(status__in=statuses)
    if resumable is True:
        queryset = queryset.filter(status__in=TASK_RESUMABLE_STATUSES)
    elif resumable is False:
        queryset = queryset.exclude(status__in=TASK_RESUMABLE_STATUSES)
    return queryset.select_related("customer", "conversation").order_by("-updated_at", "-id")


def _transition_allowed(current: str, target: str) -> bool:
    """使用显式迁移矩阵约束任务生命周期。"""
    if current == target:
        return True
    if current in TASK_TERMINAL_STATUSES:
        return False
    if target in {AssistantTaskStatus.CANCELLED, AssistantTaskStatus.EXPIRED}:
        return True
    transitions = {
        AssistantTaskStatus.PENDING: {
            AssistantTaskStatus.RUNNING,
            AssistantTaskStatus.WAITING_USER,
            AssistantTaskStatus.BLOCKED,
            AssistantTaskStatus.FAILED,
        },
        AssistantTaskStatus.RUNNING: {
            AssistantTaskStatus.WAITING_USER,
            AssistantTaskStatus.WAITING_CONFIRMATION,
            AssistantTaskStatus.BLOCKED,
            AssistantTaskStatus.COMPLETED,
            AssistantTaskStatus.FAILED,
        },
        AssistantTaskStatus.WAITING_USER: {
            AssistantTaskStatus.RUNNING,
            AssistantTaskStatus.BLOCKED,
            AssistantTaskStatus.FAILED,
        },
        AssistantTaskStatus.WAITING_CONFIRMATION: {
            AssistantTaskStatus.RUNNING,
            AssistantTaskStatus.BLOCKED,
            AssistantTaskStatus.COMPLETED,
            AssistantTaskStatus.FAILED,
        },
        AssistantTaskStatus.BLOCKED: {
            AssistantTaskStatus.PENDING,
            AssistantTaskStatus.RUNNING,
            AssistantTaskStatus.WAITING_USER,
            AssistantTaskStatus.FAILED,
        },
        AssistantTaskStatus.FAILED: {
            AssistantTaskStatus.PENDING,
            AssistantTaskStatus.RUNNING,
        },
    }
    return target in transitions.get(current, set())


def transition_task(
    task: AssistantTask,
    status: str | AssistantTaskStatus,
    current_step: str = "",
    event_type: str = "",
    event_data: dict[str, Any] | None = None,
    run: Any = None,
) -> AssistantTask:
    """原子地转换任务状态、更新版本并写入任务事件。

    参数：
        task: 待转换的 AssistantTask 实例。
        status: 目标任务状态。
        current_step: 可选当前步骤；为空时保留原步骤。
        event_type: 可选事件类型，省略时使用 ``status_changed``。
        event_data: 可选事件 JSON 数据。
    返回：
        已更新的任务实例；传入对象也会同步为最新字段。
    异常：
        TaskTransitionError: 任务不存在、目标状态非法或违反状态机。
    """
    if task is None or getattr(task, "pk", None) is None:
        raise TaskTransitionError("任务不存在", error_code="task_not_found")
    target_status = _validate_status(status)
    payload = {} if event_data is None else dict(event_data)
    run_id = getattr(run, "pk", run)
    if run_id is not None and getattr(run, "task_id", task.pk) != task.pk:
        raise TaskTransitionError("执行记录不属于当前任务", error_code="task_run_mismatch")

    with transaction.atomic():
        current = AssistantTask.objects.select_for_update().filter(pk=task.pk).first()
        if current is None:
            raise TaskTransitionError("任务不存在", error_code="task_not_found")
        if not _transition_allowed(current.status, target_status):
            raise TaskTransitionError(
                f"任务不能从 {current.status} 转为 {target_status}",
                error_code="task_transition_not_allowed",
            )

        now = timezone.now()
        previous_status = current.status
        current.status = target_status
        if current_step:
            current.current_step = str(current_step)
        if target_status == AssistantTaskStatus.COMPLETED:
            current.completed_at = current.completed_at or now
        if target_status == AssistantTaskStatus.CANCELLED:
            current.cancelled_at = current.cancelled_at or now
        current.last_activity_at = now
        current.version = (current.version or 0) + 1
        current.save(
            update_fields=[
                "status",
                "current_step",
                "completed_at",
                "cancelled_at",
                "last_activity_at",
                "version",
                "updated_at",
            ]
        )

        if previous_status != target_status or event_type:
            TaskEvent.objects.create(
                task=current,
                run_id=run_id,
                actor_id=current.therapist_id,
                event_type=event_type or "status_changed",
                from_status=previous_status,
                to_status=target_status,
                event_data=payload,
            )

    # 让调用方持有的对象无需 refresh_from_db 即可继续使用最新状态。
    for field in (
        "status",
        "current_step",
        "completed_at",
        "cancelled_at",
        "last_activity_at",
        "version",
        "updated_at",
    ):
        setattr(task, field, getattr(current, field))
    return task


_UNSET = object()


def update_task_state(
    task: AssistantTask,
    expected_version: int,
    *,
    current_step: Any = _UNSET,
    missing_fields: Any = _UNSET,
    state_data: Any = _UNSET,
    customer: Any = _UNSET,
    conversation: Any = _UNSET,
) -> AssistantTask:
    """使用乐观锁更新任务可恢复数据，并记录状态数据变更事件。

    参数：
        task: 待更新任务。
        expected_version: 客户端读取任务时得到的版本号，必须与数据库一致。
        current_step/missing_fields/state_data: 允许客户端保存的恢复数据。
        customer/conversation: 可选的新上下文，必须通过当前康复师和客户一致性校验。
    返回：
        更新后的任务实例。
    异常：
        TaskVersionConflict: 版本已被其他请求更新，调用方应重新读取任务。
        TaskBusinessError: 任务已终态或关联数据不合法。
    """
    if task is None or getattr(task, "pk", None) is None:
        raise TaskTransitionError("任务不存在", error_code="task_not_found")
    try:
        expected = int(expected_version)
    except (TypeError, ValueError) as exc:
        raise TaskBusinessError("version 必须是整数", error_code="task_version_invalid") from exc
    if expected < 1:
        raise TaskBusinessError("version 必须是正整数", error_code="task_version_invalid")

    with transaction.atomic():
        current = AssistantTask.objects.select_for_update().filter(pk=task.pk).first()
        if current is None:
            raise TaskTransitionError("任务不存在", error_code="task_not_found")
        if current.version != expected:
            raise TaskVersionConflict("任务已被更新，请刷新后重试")
        if current.status in TASK_TERMINAL_STATUSES:
            raise TaskTransitionError("已结束任务不能保存恢复数据", error_code="task_terminal")

        owner = current.therapist_id
        customer_instance = current.customer
        conversation_instance = current.conversation
        if customer is not _UNSET:
            # 这里不能直接复用传入 task 的 therapist，数据库行上的 owner 才是
            # 权限判断依据，避免调用方持有过期对象时越权更新。
            customer_instance = _load_customer(owner, customer) if customer is not None else None
        if conversation is not _UNSET:
            conversation_instance = _load_conversation(owner, conversation) if conversation is not None else None
        if conversation_instance is not None and customer_instance is not None:
            if (
                conversation_instance.customer_id is not None
                and conversation_instance.customer_id != customer_instance.id
            ):
                raise ResourceValidationError(
                    "任务客户与会话客户不一致",
                    error_code="conversation_customer_mismatch",
                )
        if current.context_resource_type and current.context_resource_id:
            resource = validate_resource_ownership(
                owner,
                current.context_resource_type,
                current.context_resource_id,
                customer_instance,
            )
            if customer_instance is None and resource is not None:
                customer_instance = _resource_customer(resource, current.context_resource_type)

        changed_fields: list[str] = []
        if current_step is not _UNSET:
            current.current_step = str(current_step or "")
            changed_fields.append("current_step")
        if missing_fields is not _UNSET:
            if not isinstance(missing_fields, list):
                raise ResourceValidationError("missing_fields 必须是数组", error_code="missing_fields_invalid")
            current.missing_fields = missing_fields
            changed_fields.append("missing_fields")
        if state_data is not _UNSET:
            current.state_data = _validate_state_data(state_data)
            changed_fields.append("state_data")
        if customer is not _UNSET and current.customer_id != getattr(customer_instance, "id", None):
            current.customer = customer_instance
            changed_fields.append("customer")
        if conversation is not _UNSET and current.conversation_id != getattr(conversation_instance, "id", None):
            current.conversation = conversation_instance
            changed_fields.append("conversation")

        if not changed_fields:
            return current
        current.version += 1
        current.last_activity_at = timezone.now()
        current.save(
            update_fields=changed_fields + ["version", "last_activity_at", "updated_at"]
        )
        TaskEvent.objects.create(
            task=current,
            actor_id=current.therapist_id,
            event_type="task_state_updated",
            from_status=current.status,
            to_status=current.status,
            event_data={"fields": changed_fields, "version": current.version},
        )

    for field in (
        "customer",
        "conversation",
        "current_step",
        "missing_fields",
        "state_data",
        "version",
        "last_activity_at",
        "updated_at",
    ):
        setattr(task, field, getattr(current, field))
    return task


def cancel_task(task: AssistantTask, reason: str = "") -> AssistantTask:
    """取消尚未结束的任务并记录取消事件。

    参数：
        task: 待取消的任务实例。
        reason: 康复师或调用方提供的取消原因，可为空。
    返回：
        已取消的任务；重复取消已取消任务时幂等返回。
    异常：
        TaskTransitionError: 任务已完成或不存在，不能取消。
    """
    if task.status == AssistantTaskStatus.CANCELLED:
        return task
    if task.status in {
        AssistantTaskStatus.COMPLETED,
        AssistantTaskStatus.EXPIRED,
    }:
        raise TaskTransitionError("已完成任务不能取消", error_code="task_already_completed")
    event_data = {"reason": str(reason or "").strip()} if str(reason or "").strip() else {}
    return transition_task(task, AssistantTaskStatus.CANCELLED, event_type="task_cancelled", event_data=event_data)


def get_tasks_for_therapist(
    therapist: Any,
    *,
    customer: Any = None,
    status: str | Iterable[str] | None = None,
    resumable: bool | None = None,
) -> QuerySet[AssistantTask]:
    """按康复师查询任务的兼容入口，等价于 ``list_owned_tasks``。"""
    return list_owned_tasks(therapist, customer=customer, status=status, resumable=resumable)


def list_tasks(
    therapist: Any,
    *,
    customer: Any = None,
    status: str | Iterable[str] | None = None,
    resumable: bool | None = None,
) -> QuerySet[AssistantTask]:
    """查询当前康复师任务的简短兼容入口。"""
    return list_owned_tasks(therapist, customer=customer, status=status, resumable=resumable)


def create_assistant_task(therapist: Any, **kwargs: Any) -> AssistantTask:
    """创建助手任务的语义化兼容入口，等价于 ``create_task``。"""
    return create_task(therapist, **kwargs)


def validate_task_resource(
    therapist: Any,
    resource_type: str | None = "",
    resource_id: Any = "",
    customer: Any = None,
) -> Any:
    """校验任务资源归属的语义化兼容入口。"""
    return validate_resource_ownership(therapist, resource_type, resource_id, customer)
