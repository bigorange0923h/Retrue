"""计划内课程次数调整服务。"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import transaction

from apps.audit.models import AuditAction, write_audit_log
from apps.schedules.models import PlanCourseAdjustment, PlanCourseStatus, RehabPlanCourse


def completed_session_count(plan_course: RehabPlanCourse) -> int:
    """统计已有确认训练记录的完成课程次数。"""
    return plan_course.sessions.filter(
        status="completed", training_records__isnull=False
    ).distinct().count()


@transaction.atomic
def adjust_plan_course_count(
    therapist: AbstractUser,
    plan_course: RehabPlanCourse,
    delta_count: int,
    reason: str,
    assessment=None,
) -> RehabPlanCourse:
    """增减计划内课程次数并保留调整前后快照。

    调整后的次数不得小于已经完成的次数；增加已完成课程的次数时会重新启用该课程。
    """
    if delta_count == 0:
        raise ValueError("调整次数不能为 0")
    if not reason.strip():
        raise ValueError("调整课程次数必须填写原因")

    locked = RehabPlanCourse.objects.select_for_update().get(id=plan_course.id)
    completed_count = completed_session_count(locked)
    before_count = locked.planned_count
    after_count = before_count + delta_count
    if after_count < completed_count:
        raise ValueError(f"调整后次数不能少于已完成次数 {completed_count}")
    if after_count < 0:
        raise ValueError("调整后次数不能小于 0")

    locked.planned_count = after_count
    if after_count > completed_count and locked.status == PlanCourseStatus.COMPLETED:
        locked.status = PlanCourseStatus.ACTIVE
    elif after_count == completed_count and locked.status in {
        PlanCourseStatus.ACTIVE,
        PlanCourseStatus.PAUSED,
    }:
        locked.status = PlanCourseStatus.COMPLETED
    locked.save(update_fields=["planned_count", "status", "updated_at"])

    adjustment = PlanCourseAdjustment.objects.create(
        plan_course=locked,
        therapist=therapist,
        assessment=assessment,
        delta_count=delta_count,
        before_count=before_count,
        after_count=after_count,
        reason=reason.strip(),
    )
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=locked,
        before={"planned_count": before_count},
        after={"planned_count": after_count, "adjustment_id": adjustment.id},
        reason=f"调整计划内课程次数：{reason.strip()}",
    )
    return locked
