"""训练记录 AI 解析与草稿确认服务。

负责：
- 调用 provider 将自然语言解析为结构化草稿。
- 保存原始输入、AI 初始结果。
- 客户识别不确定时提供候选。
- 人工确认后创建正式训练记录。
- 记录 AI 调用审计，避免输出敏感内容到日志。
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from apps.ai.models import AiDraft, AiDraftStatus
from apps.ai.providers.base import AIProviderError
from apps.ai.providers.factory import get_provider
from apps.ai.schemas.training import TrainingDraft
from apps.audit.models import AuditAction, write_audit_log
from apps.customers.models import Customer
from apps.training.models import TrainingExercise, TrainingRecord


def parse_training_draft(therapist: AbstractUser, input_text: str, customer_id: int | None = None) -> AiDraft:
    """将自然语言解析为待确认 AI 草稿。

    参数：
        therapist: 当前康复师。
        input_text: 自然语言训练描述。
        customer_id: 明确的客户 ID，可空（不确定时后续候选确认）。
    返回：
        新建的 AiDraft 草稿实例（状态 pending 或 failed）。
    """
    draft = AiDraft.objects.create(
        therapist=therapist,
        customer_id=customer_id,
        status=AiDraftStatus.PENDING,
        input_text=input_text,
    )

    provider = get_provider()
    try:
        raw = provider.parse_training_text(input_text)
        # 校验 Pydantic schema，确保结构合法
        parsed = TrainingDraft(**raw)
        draft.ai_result = parsed.model_dump()
        draft.status = AiDraftStatus.PENDING
    except (AIProviderError, ValueError) as exc:
        draft.status = AiDraftStatus.FAILED
        draft.error_message = str(exc)[:500]
    draft.save()

    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=draft,
        after={"status": draft.status, "input_length": len(input_text)},
        reason="AI 生成训练草稿",
    )
    return draft


def confirm_training_draft(therapist: AbstractUser, draft_id: int, confirmed: dict, customer_id: int | None) -> AiDraft:
    """人工确认草稿并创建正式训练记录。

    草稿必须属于当前康复师且状态为 pending。确认后创建 TrainingRecord。

    参数：
        therapist: 当前康复师。
        draft_id: 草稿 ID。
        confirmed: 人工编辑后的最终结果。
        customer_id: 确认的客户 ID。
    返回：
        更新为已确认的草稿实例。
    异常：
        ValueError: 草稿不存在、不属于当前康复师或状态不允许确认。
    """
    draft = AiDraft.objects.filter(therapist=therapist, id=draft_id).first()
    if draft is None:
        raise ValueError("草稿不存在或无权访问")
    if draft.status != AiDraftStatus.PENDING:
        raise ValueError(f"草稿当前状态不允许确认：{draft.get_status_display()}")

    customer = Customer.objects.filter(therapist=therapist, id=customer_id).first()
    if customer is None:
        raise ValueError("所选客户不存在或无权访问")

    # 创建正式训练记录
    record = TrainingRecord.objects.create(
        therapist=therapist,
        customer=customer,
        training_date=confirmed.get("training_date") or date.today().isoformat(),
        customer_feedback=confirmed.get("customer_feedback", ""),
        therapist_observation=confirmed.get("therapist_observation", ""),
        next_plan=confirmed.get("next_plan", ""),
        note=confirmed.get("note", ""),
    )
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

    # 更新草稿状态与确认结果
    draft.status = AiDraftStatus.CONFIRMED
    draft.confirmed_result = confirmed
    draft.customer = customer
    draft.confirmed_at = timezone.now()
    draft.save()

    write_audit_log(
        actor=therapist,
        action=AuditAction.CONFIRM,
        obj=record,
        after={"draft_id": draft.id, "customer_id": customer.id},
        reason="AI 草稿确认创建训练记录",
    )
    return draft


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
    draft = AiDraft.objects.filter(therapist=therapist, id=draft_id).first()
    if draft is None:
        raise ValueError("草稿不存在或无权访问")
    if draft.status == AiDraftStatus.CONFIRMED:
        raise ValueError("已确认的草稿不能取消")
    draft.status = AiDraftStatus.CANCELLED
    draft.save()
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
