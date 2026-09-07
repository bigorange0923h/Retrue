"""training：训练记录业务服务。

承载数据隔离、时间线查询与修订审计等业务规则。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from apps.audit.models import AuditAction, write_audit_log
from apps.training.models import TrainingRecord


def list_records(
    therapist: AbstractUser,
    customer_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """分页查询某客户的训练记录，强制数据隔离。

    参数：
        therapist: 当前登录康复师。
        customer_id: 客户主键。
        page: 页码。
        page_size: 每页条数。
    返回：
        分页字典 {items, page, page_size, total}。
    """
    queryset = (
        TrainingRecord.objects.filter(therapist=therapist, customer_id=customer_id)
        .select_related("customer", "course_session__plan_course__course_type")
        .prefetch_related("exercises")
    )
    total = queryset.count()
    start = (page - 1) * page_size
    items = list(queryset[start : start + page_size])
    return {"items": items, "page": page, "page_size": page_size, "total": total}


def get_record(therapist: AbstractUser, record_id: int) -> TrainingRecord | None:
    """获取属于当前康复师的单条训练记录。

    参数：
        therapist: 当前登录康复师。
        record_id: 训练记录主键。
    返回：
        记录实例；不属于当前康复师或不存在时返回 None。
    """
    return (
        TrainingRecord.objects.filter(therapist=therapist, id=record_id)
        .select_related("customer", "course_session__plan_course__course_type")
        .prefetch_related("exercises")
        .first()
    )


def get_customer_timeline(therapist: AbstractUser, customer_id: int) -> list:
    """获取客户时间线（按训练日期倒序），含每条记录及其动作。

    参数：
        therapist: 当前登录康复师。
        customer_id: 客户主键。
    返回：
        训练记录列表（已按日期倒序），含嵌套 exercises。
    """
    return list(
        TrainingRecord.objects.filter(therapist=therapist, customer_id=customer_id)
        .select_related("customer", "course_session__plan_course__course_type")
        .prefetch_related("exercises")
        .order_by("-training_date", "-created_at")
    )


def record_to_dict(record: TrainingRecord) -> dict:
    """将训练记录转为审计快照字典。

    参数：
        record: 训练记录实例。
    返回：
        含关键字段的字典。
    """
    return {
        "id": record.id,
        "training_date": record.training_date.isoformat() if record.training_date else None,
        "customer_feedback": record.customer_feedback,
        "therapist_observation": record.therapist_observation,
        "next_plan": record.next_plan,
        "note": record.note,
        "exercises": [
            {
                "name": e.exercise_name,
                "sets": e.sets,
                "reps": e.reps,
                "weight": e.weight,
                "duration_seconds": e.duration_seconds,
            }
            for e in record.exercises.all()
        ],
    }


def write_revision_log(
    therapist: AbstractUser,
    record: TrainingRecord,
    *,
    before: dict,
    after: dict,
    reason: str,
) -> None:
    """记录训练记录的人工修订审计。

    参数：
        therapist: 操作人（康复师）。
        record: 被修订的训练记录。
        before: 修订前快照。
        after: 修订后快照。
        reason: 修改原因，必填。
    """
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=record,
        before=before,
        after=after,
        reason=reason,
    )
