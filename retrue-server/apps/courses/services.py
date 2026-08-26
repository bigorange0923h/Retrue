"""courses：课时管理业务服务。

课时消耗需满足：课程已完成 + 训练记录已确认保存。
请假/取消不扣课时；人工调整必须记录原因。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from apps.audit.models import AuditAction, write_audit_log
from apps.courses.models import CourseAdjustment, CoursePackage


def consume_session(therapist: AbstractUser, package: CoursePackage) -> None:
    """消耗一个课时。

    从课时包扣除一个课时并记录审计。调用方需确保前置条件满足
    （课程完成且训练记录已确认保存）。

    参数：
        therapist: 当前康复师。
        package: 要消耗的课时包。
    异常：
        ValueError: 剩余课时不足。
    """
    if package.remaining_sessions <= 0:
        raise ValueError("课时不足，无法消耗")
    package.used_sessions += 1
    package.save()
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=package,
        after={"used_sessions": package.used_sessions, "remaining": package.remaining_sessions},
        reason="消耗一个课时（课程完成且训练记录已确认）",
    )


def adjust_sessions(therapist: AbstractUser, package: CoursePackage, delta: int, reason: str) -> CoursePackage:
    """人工调整课时，必须填写原因。

    参数：
        therapist: 当前康复师。
        package: 课时包。
        delta: 调整量，正为增加、负为扣减。
        reason: 调整原因，必填。
    返回：
        调整后的课时包。
    """
    if not reason.strip():
        raise ValueError("人工调整课时必须填写原因")
    new_used = max(package.used_sessions + delta, 0)
    CourseAdjustment.objects.create(therapist=therapist, package=package, delta=delta, reason=reason)
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
