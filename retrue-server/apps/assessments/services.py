"""assessments：评估业务服务。"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from apps.assessments.models import Assessment
from apps.audit.models import AuditAction, write_audit_log


def list_assessments(therapist: AbstractUser, customer_id: int) -> list:
    """查询某客户的评估列表。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
    返回：
        评估列表（含指标），按日期倒序。
    """
    return list(
        Assessment.objects.filter(therapist=therapist, customer_id=customer_id)
        .prefetch_related("metrics")
        .order_by("-assessment_date")
    )


def get_assessment(therapist: AbstractUser, assessment_id: int) -> Assessment | None:
    """获取属于当前康复师的评估。

    参数：
        therapist: 当前康复师。
        assessment_id: 评估主键。
    返回：
        评估实例；不存在或无权访问时返回 None。
    """
    return Assessment.objects.filter(therapist=therapist, id=assessment_id).prefetch_related("metrics").first()


def assessment_to_dict(assessment: Assessment) -> dict:
    """将评估转为审计快照。"""
    return {
        "id": assessment.id,
        "assessment_type": assessment.assessment_type,
        "assessment_date": assessment.assessment_date.isoformat(),
        "chief_complaint": assessment.chief_complaint,
        "metric_count": assessment.metrics.count(),
    }


def log_assessment_change(therapist: AbstractUser, assessment: Assessment, *, before: dict | None, after: dict, action: str, reason: str) -> None:
    """记录评估变更审计。"""
    write_audit_log(
        actor=therapist,
        action=action,
        obj=assessment,
        before=before,
        after=after,
        reason=reason,
    )
