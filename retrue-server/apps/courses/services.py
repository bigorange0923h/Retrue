"""courses：课时管理业务服务。

课时消耗需满足：课程关联正式训练记录。
请假/取消不扣课时；人工调整必须记录原因。
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import transaction

from apps.audit.models import AuditAction, write_audit_log
from apps.courses.models import CourseAdjustment, CourseAdjustmentType, CoursePackage


@transaction.atomic
def consume_session(therapist: AbstractUser, package: CoursePackage) -> None:
    """消耗一个课时。

    从课时包扣除一个课时并记录审计。调用方需确保前置条件满足
    （课程关联正式训练记录）。

    参数：
        therapist: 当前康复师。
        package: 要消耗的课时包。
    异常：
        ValueError: 剩余课时不足。
    """
    locked_package = CoursePackage.objects.select_for_update().get(
        id=package.id,
        therapist=therapist,
    )
    _deduct(
        therapist,
        locked_package,
        Decimal("1"),
        "课程完成并保存正式训练记录，自动扣减课时",
    )


def _deduct(
    therapist: AbstractUser,
    package: CoursePackage,
    amount: Decimal,
    reason: str,
    course_session=None,
) -> None:
    """从课时包扣减指定课时量并记录审计。

    参数：
        therapist: 当前康复师。
        package: 课时包。
        amount: 扣减课时量（支持 0.5 半课）。
        reason: 扣减原因。
    异常：
        ValueError: 剩余课时不足。
    """
    if package.remaining_sessions < amount:
        raise ValueError("课时不足，无法消耗")
    package.used_sessions = Decimal(package.used_sessions) + amount
    package.save()
    CourseAdjustment.objects.create(
        therapist=therapist,
        package=package,
        course_session=course_session,
        adjustment_type=CourseAdjustmentType.CONSUMPTION,
        delta=amount,
        reason=reason,
    )
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=package,
        after={"used_sessions": package.used_sessions, "remaining": package.remaining_sessions},
        reason=reason,
    )


@transaction.atomic
def complete_session_for_record(therapist: AbstractUser, record) -> None:
    """确认训练记录后完成对应排课并幂等扣减课时。

    训练记录、课程完成状态和课时扣减处于同一事务。余额不足会明确报错并回滚，
    取消或请假的课程不能通过训练记录完成。
    """
    if record.course_session_id is None:
        return

    from apps.schedules.models import CourseSession, CourseSessionStatus, PlanCourseStatus

    # 仅锁定排课本身；plan_course 可空，PostgreSQL 不允许对外连接的可空侧 FOR UPDATE。
    session = CourseSession.objects.select_for_update().get(id=record.course_session_id)
    if session.therapist_id != therapist.id:
        raise ValueError("关联课程不属于当前康复师")
    if session.customer_id != record.customer_id:
        raise ValueError("训练记录客户与关联课程客户不一致")
    if session.training_records.exclude(id=record.id).exists():
        raise ValueError("该课程已经有正式训练记录")
    if session.status in {CourseSessionStatus.CANCELLED, CourseSessionStatus.ABSENT}:
        raise ValueError("已取消或请假的课程不能确认训练记录")

    package = getattr(session.plan_course, "package", None)
    if package is not None and not session.session_consumed:
        locked_package = CoursePackage.objects.select_for_update().get(id=package.id)
        _deduct(
            therapist,
            locked_package,
            Decimal(session.session_count),
            f"排课 {session.id} 保存正式训练记录，自动扣减 {session.session_count} 课时",
            course_session=session,
        )
        session.session_consumed = True

    session.status = CourseSessionStatus.COMPLETED
    session.save(update_fields=["status", "session_consumed", "updated_at"])

    plan_course = session.plan_course
    if plan_course is not None:
        completed_count = plan_course.sessions.filter(
            status=CourseSessionStatus.COMPLETED,
            training_records__isnull=False,
        ).distinct().count()
        if completed_count >= plan_course.planned_count and plan_course.status in {
            PlanCourseStatus.ACTIVE,
            PlanCourseStatus.PAUSED,
        }:
            plan_course.status = PlanCourseStatus.COMPLETED
            plan_course.save(update_fields=["status", "updated_at"])


@transaction.atomic
def adjust_sessions(
    therapist: AbstractUser,
    package: CoursePackage,
    delta: Decimal,
    reason: str,
) -> CoursePackage:
    """人工调整课时，必须填写原因。

    参数：
        therapist: 当前康复师。
        package: 课时包。
        delta: 已用课时调整量，正为补扣、负为退还。
        reason: 调整原因，必填。
    返回：
        调整后的课时包。
    """
    if not reason.strip():
        raise ValueError("人工调整课时必须填写原因")
    if delta == 0 or delta % Decimal("0.5") != 0:
        raise ValueError("调整量必须是非零的 0.5 倍数")
    package = CoursePackage.objects.select_for_update().get(
        id=package.id,
        therapist=therapist,
    )
    new_used = Decimal(package.used_sessions) + delta
    if new_used < 0:
        raise ValueError("退还后的已用课时不能小于 0")
    if new_used > package.total_sessions:
        raise ValueError("调整后的已用课时不能超过总课时")
    CourseAdjustment.objects.create(
        therapist=therapist,
        package=package,
        adjustment_type=CourseAdjustmentType.MANUAL,
        delta=delta,
        reason=reason,
    )
    package.used_sessions = new_used
    package.save()
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=package,
        after={"used_sessions": package.used_sessions, "delta": delta, "reason": reason},
        reason=f"人工调整课时：{reason}",
    )
    return package
