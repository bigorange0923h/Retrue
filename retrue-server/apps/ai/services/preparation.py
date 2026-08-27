"""备课助手服务。

系统自动汇总客户历史数据（上次训练、当前疼痛、康复阶段、下次计划等），
再调用 AI provider 生成备课建议。汇总数据不含完整敏感信息。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from apps.ai.providers.factory import get_provider
from apps.rehab.services import get_current_stage
from apps.training.models import TrainingRecord


def prepare_lesson(therapist: AbstractUser, customer_id: int) -> dict:
    """为客户生成备课助手内容。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
    返回：
        含 customer_summary 与 ai_suggestions 的字典。
    """
    records = list(
        TrainingRecord.objects.filter(therapist=therapist, customer_id=customer_id)
        .prefetch_related("exercises")
        .order_by("-training_date", "-created_at")[:5]
    )
    last_record = records[0] if records else None
    stage = get_current_stage(therapist, customer_id)

    # 汇总客户历史（不含完整敏感字段）
    summary = {
        "last_record_date": last_record.training_date.isoformat() if last_record else None,
        "last_exercises": [e.exercise_name for e in last_record.exercises.all()] if last_record else [],
        "customer_feedback": last_record.customer_feedback if last_record else "",
        "therapist_observation": last_record.therapist_observation if last_record else "",
        "next_plan": last_record.next_plan if last_record else "",
        "current_stage": stage.get_stage_type_display() if stage else "",
        "note": last_record.note if last_record else "",
    }

    # 调用 provider 生成建议
    provider = get_provider()
    ai_suggestions = provider.prepare_lesson(summary)

    return {"customer_summary": summary, "ai_suggestions": ai_suggestions}
