"""评估、训练修订与随访草稿的解析与确认服务。

与训练补记草稿共享 ``AiDraft`` 模型，通过 ``draft_type`` 区分类型。
AI 只生成待确认草稿；正式写入（创建评估、更新训练记录、创建随访）在康复师
确认后由本服务执行，且仍受领域服务既有约束（评估首评唯一、课程唯一等）保护。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ai.models import AiDraft, AiDraftStatus, AiDraftType
from apps.ai.providers.factory import get_provider
from apps.ai.schemas.domain import AssessmentDraft, FollowUpDraft, TrainingRevisionDraft
from apps.audit.models import AuditAction, write_audit_log
from apps.customers.models import Customer


def _validate_customer(therapist: AbstractUser, customer_id: int | None) -> Customer | None:
    """校验客户存在且属于当前康复师。"""
    if customer_id is None:
        return None
    customer = Customer.objects.filter(therapist=therapist, id=customer_id).first()
    if customer is None:
        raise ValueError("所选客户不存在或无权访问")
    return customer


def _get_pending_draft(therapist: AbstractUser, draft_id: int, draft_type: AiDraftType):
    """按类型获取属于当前康复师的待确认草稿。"""
    return (
        AiDraft.objects.select_for_update()
        .filter(therapist=therapist, id=draft_id, draft_type=draft_type)
        .first()
    )


def _finish_draft(draft: AiDraft, status: AiDraftStatus, error: str = "") -> None:
    draft.status = status
    if error:
        draft.error_message = error[:500]
    draft.save(update_fields=["status", "error_message", "updated_at"])


def _parse(
    therapist: AbstractUser,
    input_text: str,
    *,
    draft_type: AiDraftType,
    customer_id: int | None,
    assistant_task_id: int | None,
    schema,
    provider_method: str,
) -> AiDraft:
    """通用的草稿解析：调用 provider、校验 schema、落库为 pending/failed。"""
    customer = _validate_customer(therapist, customer_id)
    draft = AiDraft.objects.create(
        therapist=therapist,
        customer=customer,
        assistant_task_id=assistant_task_id,
        draft_type=draft_type,
        status=AiDraftStatus.PENDING,
        input_text=input_text,
    )
    try:
        provider = get_provider()
        raw = getattr(provider, provider_method)(input_text)
        parsed = schema(**raw)
        draft.ai_result = parsed.model_dump()
        draft.status = AiDraftStatus.PENDING
    except Exception as exc:  # noqa: BLE001
        draft.status = AiDraftStatus.FAILED
        draft.error_message = str(exc)[:500]
    draft.save(update_fields=["ai_result", "status", "error_message", "updated_at"])
    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=draft,
        after={"draft_type": draft_type, "status": draft.status},
        reason="AI 生成领域草稿",
    )
    return draft


def parse_assessment_draft(
    therapist: AbstractUser,
    input_text: str,
    customer_id: int | None = None,
    assistant_task_id: int | None = None,
) -> AiDraft:
    """将自然语言解析为评估草稿。"""
    return _parse(
        therapist,
        input_text,
        draft_type=AiDraftType.ASSESSMENT,
        customer_id=customer_id,
        assistant_task_id=assistant_task_id,
        schema=AssessmentDraft,
        provider_method="parse_assessment_text",
    )


def parse_training_revision_draft(
    therapist: AbstractUser,
    input_text: str,
    customer_id: int | None = None,
    assistant_task_id: int | None = None,
    target_record_id: int | None = None,
) -> AiDraft:
    """将自然语言解析为训练记录修订草稿。"""
    draft = _parse(
        therapist,
        input_text,
        draft_type=AiDraftType.TRAINING_REVISION,
        customer_id=customer_id,
        assistant_task_id=assistant_task_id,
        schema=TrainingRevisionDraft,
        provider_method="parse_training_revision_text",
    )
    if target_record_id is not None:
        draft.ai_result = {**draft.ai_result, "target_record_id": target_record_id}
        draft.save(update_fields=["ai_result", "updated_at"])
    return draft


def parse_followup_draft(
    therapist: AbstractUser,
    input_text: str,
    customer_id: int | None = None,
    assistant_task_id: int | None = None,
) -> AiDraft:
    """将自然语言解析为随访草稿。"""
    return _parse(
        therapist,
        input_text,
        draft_type=AiDraftType.FOLLOWUP,
        customer_id=customer_id,
        assistant_task_id=assistant_task_id,
        schema=FollowUpDraft,
        provider_method="parse_followup_text",
    )


@transaction.atomic
def confirm_assessment_draft(
    therapist: AbstractUser,
    draft_id: int,
    confirmed: dict,
    customer_id: int,
    idempotency_key: str | None = None,
) -> AiDraft:
    """确认评估草稿，创建正式评估记录（status=draft，由评估工作台继续完成）。"""
    draft = _get_pending_draft(therapist, draft_id, AiDraftType.ASSESSMENT)
    if draft is None:
        raise ValueError("评估草稿不存在或无权访问")
    if draft.status == AiDraftStatus.CONFIRMED:
        return draft
    if draft.status != AiDraftStatus.PENDING:
        raise ValueError(f"草稿当前状态不允许确认：{draft.get_status_display()}")

    customer = _validate_customer(therapist, customer_id)
    if customer is None:
        raise ValueError("确认客户不能为空")

    from apps.assessments.models import Assessment, AssessmentStatus, AssessmentType

    confirmed = dict(confirmed)
    if isinstance(confirmed.get("assessment_date"), date):
        confirmed["assessment_date"] = confirmed["assessment_date"].isoformat()

    assessment_type = (
        AssessmentType.REASSESSMENT
        if confirmed.get("assessment_type") == AssessmentType.REASSESSMENT
        else AssessmentType.INITIAL
    )
    try:
        with transaction.atomic():
            assessment = Assessment.objects.create(
                therapist=therapist,
                customer=customer,
                assessment_type=assessment_type,
                status=AssessmentStatus.DRAFT,
                assessment_date=confirmed.get("assessment_date") or date.today().isoformat(),
                chief_complaint=confirmed.get("chief_complaint", ""),
                medical_history=confirmed.get("medical_history", ""),
                rehab_goal=confirmed.get("rehab_goal", ""),
                current_status=confirmed.get("current_status", ""),
                note=confirmed.get("note", ""),
            )
    except IntegrityError as exc:
        raise ValueError("该客户已有首次评估，无法再次创建") from exc

    draft.status = AiDraftStatus.CONFIRMED
    draft.confirmed_result = confirmed
    draft.customer = customer
    draft.assessment = assessment
    if idempotency_key:
        draft.confirmation_key = idempotency_key
    draft.confirmed_at = timezone.now()
    draft.save(
        update_fields=[
            "status",
            "confirmed_result",
            "customer",
            "assessment",
            "confirmation_key",
            "confirmed_at",
            "updated_at",
        ]
    )
    write_audit_log(
        actor=therapist,
        action=AuditAction.CONFIRM,
        obj=assessment,
        after={"draft_id": draft.id, "customer_id": customer.id},
        reason="AI 评估草稿确认创建评估",
    )
    return draft


@transaction.atomic
def confirm_followup_draft(
    therapist: AbstractUser,
    draft_id: int,
    confirmed: dict,
    customer_id: int,
    idempotency_key: str | None = None,
) -> AiDraft:
    """确认随访草稿，创建正式随访待办。"""
    draft = _get_pending_draft(therapist, draft_id, AiDraftType.FOLLOWUP)
    if draft is None:
        raise ValueError("随访草稿不存在或无权访问")
    if draft.status == AiDraftStatus.CONFIRMED:
        return draft
    if draft.status != AiDraftStatus.PENDING:
        raise ValueError(f"草稿当前状态不允许确认：{draft.get_status_display()}")

    customer = _validate_customer(therapist, customer_id)
    if customer is None:
        raise ValueError("确认客户不能为空")

    from apps.followups.models import FollowUpStatus, FollowUpTask, FollowUpType

    confirmed = dict(confirmed)
    if isinstance(confirmed.get("due_date"), date):
        confirmed["due_date"] = confirmed["due_date"].isoformat()
    followup_type = confirmed.get("followup_type") or FollowUpType.VISIT
    if followup_type not in FollowUpType.values:
        followup_type = FollowUpType.VISIT

    followup = FollowUpTask.objects.create(
        therapist=therapist,
        customer=customer,
        followup_type=followup_type,
        due_date=confirmed.get("due_date") or date.today().isoformat(),
        content=confirmed.get("content", ""),
        status=FollowUpStatus.PENDING,
    )

    draft.status = AiDraftStatus.CONFIRMED
    draft.confirmed_result = confirmed
    draft.customer = customer
    draft.followup = followup
    if idempotency_key:
        draft.confirmation_key = idempotency_key
    draft.confirmed_at = timezone.now()
    draft.save(
        update_fields=[
            "status",
            "confirmed_result",
            "customer",
            "followup",
            "confirmation_key",
            "confirmed_at",
            "updated_at",
        ]
    )
    write_audit_log(
        actor=therapist,
        action=AuditAction.CONFIRM,
        obj=followup,
        after={"draft_id": draft.id, "customer_id": customer.id},
        reason="AI 随访草稿确认创建随访",
    )
    return draft


@transaction.atomic
def confirm_training_revision_draft(
    therapist: AbstractUser,
    draft_id: int,
    confirmed: dict,
    customer_id: int,
    idempotency_key: str | None = None,
) -> AiDraft:
    """确认训练修订草稿，更新目标训练记录的修订字段。"""
    draft = _get_pending_draft(therapist, draft_id, AiDraftType.TRAINING_REVISION)
    if draft is None:
        raise ValueError("训练修订草稿不存在或无权访问")
    if draft.status == AiDraftStatus.CONFIRMED:
        return draft
    if draft.status != AiDraftStatus.PENDING:
        raise ValueError(f"草稿当前状态不允许确认：{draft.get_status_display()}")

    customer = _validate_customer(therapist, customer_id)
    if customer is None:
        raise ValueError("确认客户不能为空")

    from apps.training.models import TrainingRecord

    target_record_id = (draft.ai_result or {}).get("target_record_id")
    if not target_record_id:
        raise ValueError("训练修订缺少目标训练记录")
    record = TrainingRecord.objects.select_for_update().filter(
        therapist=therapist, id=target_record_id, customer=customer
    ).first()
    if record is None:
        raise ValueError("目标训练记录不存在或无权访问")

    confirmed = dict(confirmed)
    record.customer_feedback = confirmed.get("customer_feedback", record.customer_feedback)
    record.therapist_observation = confirmed.get("therapist_observation", record.therapist_observation)
    record.next_plan = confirmed.get("next_plan", record.next_plan)
    record.note = confirmed.get("note", record.note)
    record.save(
        update_fields=[
            "customer_feedback",
            "therapist_observation",
            "next_plan",
            "note",
            "updated_at",
        ]
    )

    draft.status = AiDraftStatus.CONFIRMED
    draft.confirmed_result = confirmed
    draft.customer = customer
    draft.training_record = record
    if idempotency_key:
        draft.confirmation_key = idempotency_key
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
    write_audit_log(
        actor=therapist,
        action=AuditAction.CONFIRM,
        obj=record,
        after={"draft_id": draft.id, "customer_id": customer.id},
        reason="AI 训练修订草稿确认更新训练记录",
    )
    return draft


@transaction.atomic
def cancel_domain_draft(therapist: AbstractUser, draft_id: int) -> AiDraft:
    """取消领域草稿（评估/训练修订/随访），不写正式记录。"""
    draft = (
        AiDraft.objects.select_for_update()
        .filter(therapist=therapist, id=draft_id)
        .first()
    )
    if draft is None:
        raise ValueError("草稿不存在或无权访问")
    if draft.status == AiDraftStatus.CONFIRMED:
        raise ValueError("已确认的草稿不能取消")
    draft.status = AiDraftStatus.CANCELLED
    draft.save(update_fields=["status", "updated_at"])
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=draft,
        after={"status": draft.status, "draft_type": draft.draft_type},
        reason="取消 AI 领域草稿",
    )
    return draft
