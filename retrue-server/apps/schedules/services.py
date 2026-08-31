"""课程计划与课表联动的业务服务。

这里集中处理计划次数、单节排课、批量排课和时间冲突规则。视图层只负责
解析请求并把面向康复师的错误消息返回给前端，避免单次排课和批量排课出现
不一致的业务判断。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction, write_audit_log
from apps.schedules.models import (
    CourseArrangementType,
    CourseSession,
    CourseSessionStatus,
    PlanCourseAdjustment,
    PlanCourseStatus,
    RehabPlanCourse,
)


class BatchScheduleConflictError(ValueError):
    """批量确认时发现时间冲突。"""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__("有课程时间冲突，请调整时间后再确认")


def _session_queryset(plan_course: RehabPlanCourse):
    """返回计划课程的排课查询集。"""
    return CourseSession.objects.filter(plan_course_id=plan_course.id)


def completed_session_count(plan_course: RehabPlanCourse) -> int:
    """统计已有确认训练记录的完成课程次数。"""
    return _session_queryset(plan_course).filter(
        status=CourseSessionStatus.COMPLETED,
        training_records__isnull=False,
    ).distinct().count()


def scheduled_session_count(
    plan_course: RehabPlanCourse,
    exclude_session_id: int | None = None,
) -> int:
    """统计仍占用计划次数的排课。

    逾期但仍为“待上课”的课程也必须计入，避免康复师在未处理逾期课程前
    重复安排同一节课。
    """
    queryset = _session_queryset(plan_course).filter(status=CourseSessionStatus.SCHEDULED)
    if exclude_session_id is not None:
        queryset = queryset.exclude(id=exclude_session_id)
    return queryset.count()


def plan_course_progress(plan_course: RehabPlanCourse) -> dict[str, int]:
    """返回计划课程的进度统计。"""
    completed = completed_session_count(plan_course)
    scheduled = scheduled_session_count(plan_course)
    overdue = _session_queryset(plan_course).filter(
        status=CourseSessionStatus.SCHEDULED,
        date__lt=timezone.localdate(),
    ).count()
    return {
        "planned_count": plan_course.planned_count,
        "completed_count": completed,
        "scheduled_count": scheduled,
        "unscheduled_count": max(plan_course.planned_count - completed - scheduled, 0),
        "overdue_count": overdue,
    }


def ensure_plan_course_capacity(
    plan_course: RehabPlanCourse,
    *,
    exclude_session_id: int | None = None,
) -> None:
    """确认再增加一节待上课排课不会超过计划次数。"""
    completed = completed_session_count(plan_course)
    scheduled = scheduled_session_count(plan_course, exclude_session_id=exclude_session_id)
    if completed + scheduled >= plan_course.planned_count:
        raise ValueError("该课程已全部安排，不能继续添加；如需增加请先调整计划次数")


def ensure_plan_course_status_change_allowed(
    plan_course: RehabPlanCourse,
    new_status: str,
) -> None:
    """暂停或取消课程前，确保康复师已处理待上课排课。"""
    if new_status not in {PlanCourseStatus.PAUSED, PlanCourseStatus.CANCELLED}:
        return
    pending = scheduled_session_count(plan_course)
    if pending:
        raise ValueError(f"该课程还有 {pending} 节待上课课程，请先取消或改期后再{_status_action(new_status)}")


def _status_action(status: str) -> str:
    return "暂停" if status == PlanCourseStatus.PAUSED else "取消"


def _format_time(value: time | None) -> str:
    return value.strftime("%H:%M") if value else ""


def format_conflict_message(session_date: date, start_time: time | None) -> str:
    """生成康复师能直接理解的冲突提示。"""
    return (
        f"{session_date.month}月{session_date.day}日 {_format_time(start_time)}"
        "已有其他客户课程，请调整时间"
    )


def find_session_time_conflict(
    therapist: AbstractUser,
    session_date: date,
    start_time: time | None,
    end_time: time | None,
    *,
    exclude_session_id: int | None = None,
) -> CourseSession | None:
    """查找同一康复师在同一时段的有效课程。

    没有完整时间的课程不会误报冲突；已取消和请假课程不占用时间。
    """
    if not start_time or not end_time:
        return None
    queryset = CourseSession.objects.filter(
        therapist=therapist,
        date=session_date,
        status__in=[CourseSessionStatus.SCHEDULED, CourseSessionStatus.COMPLETED],
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).order_by("start_time", "id")
    if exclude_session_id is not None:
        queryset = queryset.exclude(id=exclude_session_id)
    return queryset.select_related("customer").first()


def _ensure_valid_assignment(
    therapist: AbstractUser,
    customer,
    plan_course: RehabPlanCourse | None,
    arrangement_type: str,
    *,
    status: str,
    exclude_session_id: int | None = None,
    allow_existing_id: int | None = None,
) -> RehabPlanCourse | None:
    """服务层再次校验客户、计划课程和安排类型，防止绕过 API 直接调用。"""
    if customer is None:
        raise ValueError("请先选择客户")
    if customer.therapist_id != therapist.id:
        raise ValueError("无权为该客户排课")
    if plan_course is None:
        if arrangement_type == CourseArrangementType.PLAN:
            raise ValueError("计划课程必须选择一门课程")
        return None
    if arrangement_type != CourseArrangementType.PLAN:
        raise ValueError("选择了计划内课程后，安排类型应为计划课程")
    course_id = getattr(plan_course, "id", plan_course)
    plan_course = (
        RehabPlanCourse.objects.select_for_update()
        .select_related("rehab_plan__customer", "course_type")
        .get(id=course_id)
    )
    if plan_course.rehab_plan.therapist_id != therapist.id:
        raise ValueError("无权使用该计划内课程")
    if plan_course.rehab_plan.customer_id != customer.id:
        raise ValueError("计划内课程的客户与排期客户不一致")
    is_existing_assignment = plan_course.id == allow_existing_id
    if (not is_existing_assignment or status == CourseSessionStatus.SCHEDULED) and plan_course.rehab_plan.status != "active":
        raise ValueError("已结束的课程计划不能继续排课")
    if (not is_existing_assignment or status == CourseSessionStatus.SCHEDULED) and plan_course.status != PlanCourseStatus.ACTIVE:
        raise ValueError("只能为进行中的计划内课程排课")
    if status == CourseSessionStatus.SCHEDULED:
        ensure_plan_course_capacity(plan_course, exclude_session_id=exclude_session_id)
    return plan_course


@transaction.atomic
def create_course_session(therapist: AbstractUser, data: dict) -> CourseSession:
    """创建单节排课并校验计划次数和时间冲突。"""
    data = dict(data)
    customer = data.get("customer")
    plan_course = data.get("plan_course")
    arrangement_type = data.get(
        "arrangement_type",
        CourseArrangementType.PLAN if plan_course is not None else CourseArrangementType.OTHER,
    )
    status = data.get("status", CourseSessionStatus.SCHEDULED)
    locked_plan_course = _ensure_valid_assignment(
        therapist,
        customer,
        plan_course,
        arrangement_type,
        status=status,
    )
    if locked_plan_course is not None:
        data["plan_course"] = locked_plan_course
        data.setdefault("session_count", locked_plan_course.session_cost)
        if not data.get("session_topic"):
            data["session_topic"] = locked_plan_course.course_type.name
    data["arrangement_type"] = arrangement_type
    conflict = (
        find_session_time_conflict(
            therapist,
            data["date"],
            data.get("start_time"),
            data.get("end_time"),
        )
        if status == CourseSessionStatus.SCHEDULED
        else None
    )
    if conflict is not None:
        raise ValueError(format_conflict_message(conflict.date, conflict.start_time))
    return CourseSession.objects.create(therapist=therapist, **data)


@transaction.atomic
def update_course_session(
    therapist: AbstractUser,
    session: CourseSession,
    data: dict,
) -> CourseSession:
    """更新单节排课，必要时重新检查计划余量与时间冲突。"""
    locked_session = (
        CourseSession.objects.select_for_update()
        .get(id=session.id, therapist=therapist)
    )
    merged = {
        "customer": locked_session.customer,
        "plan_course": locked_session.plan_course,
        "arrangement_type": locked_session.arrangement_type,
        "status": locked_session.status,
        "date": locked_session.date,
        "start_time": locked_session.start_time,
        "end_time": locked_session.end_time,
        "session_count": locked_session.session_count,
    }
    merged.update(data)
    plan_course = merged.get("plan_course")
    arrangement_type = merged.get("arrangement_type")
    # 变更计划课程时，用新的计划课程快照填充默认课时；保留显式修改值。
    if plan_course is not None and "session_count" not in data:
        merged["session_count"] = plan_course.session_cost
    locked_plan_course = _ensure_valid_assignment(
        therapist,
        merged["customer"],
        plan_course,
        arrangement_type,
        status=merged["status"],
        exclude_session_id=locked_session.id,
        allow_existing_id=locked_session.plan_course_id,
    )
    if locked_plan_course is not None:
        merged["plan_course"] = locked_plan_course
        if "session_topic" not in data and not locked_session.session_topic:
            merged["session_topic"] = locked_plan_course.course_type.name
    if merged["status"] == CourseSessionStatus.SCHEDULED:
        conflict = find_session_time_conflict(
            therapist,
            merged["date"],
            merged.get("start_time"),
            merged.get("end_time"),
            exclude_session_id=locked_session.id,
        )
        if conflict is not None:
            raise ValueError(format_conflict_message(conflict.date, conflict.start_time))
    for field, value in data.items():
        setattr(locked_session, field, value)
    if "arrangement_type" not in data:
        locked_session.arrangement_type = arrangement_type
    if "plan_course" in data and "session_count" not in data and locked_plan_course is not None:
        locked_session.session_count = locked_plan_course.session_cost
    locked_session.save()
    return locked_session


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("开始日期格式错误，应为 YYYY-MM-DD") from exc


def _parse_time(value) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("上课时间格式错误，应为 HH:MM") from exc


def _normalise_weekdays(value, start_date: date) -> list[int]:
    """将前端 0=周日、1-6=周一至周六转换为内部同一约定。"""
    if value in (None, "", []):
        return [(start_date.weekday() + 1) % 7]
    if isinstance(value, (str, int)):
        value = [value]
    try:
        weekdays = [int(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError("上课星期格式不正确") from exc
    # 同时兼容常见的 ISO 7=周日写法；0-6 仍是首选接口约定。
    weekdays = [0 if item == 7 else item for item in weekdays]
    if any(item < 0 or item > 6 for item in weekdays):
        raise ValueError("上课星期应为周日到周六")
    if len(set(weekdays)) != len(weekdays):
        raise ValueError("上课星期不能重复")
    return sorted(weekdays)


def _batch_options(options: dict, plan_course: RehabPlanCourse) -> dict:
    """兼容批量安排请求的常见字段名，并补齐默认值。"""
    options = dict(options)
    start_date = _parse_date(options.get("start_date"))
    weekdays = _normalise_weekdays(options.get("weekdays"), start_date)
    frequency = options.get("frequency", options.get("weekly_count"))
    if frequency in (None, ""):
        frequency = len(weekdays)
    try:
        frequency = int(frequency)
    except (TypeError, ValueError) as exc:
        raise ValueError("每周上课次数应为 1 到 7 次") from exc
    if frequency < 1 or frequency > 7:
        raise ValueError("每周上课次数应为 1 到 7 次")
    if len(weekdays) != frequency:
        raise ValueError("每周上课次数应与选择的星期数量一致")
    start_time = _parse_time(options.get("start_time"))
    end_time = _parse_time(options.get("end_time"))
    if start_time and end_time and end_time <= start_time:
        raise ValueError("结束时间必须晚于开始时间")
    if start_time and end_time is None:
        if not plan_course.duration:
            raise ValueError("请先为该课程设置单次时长，再安排课程")
        end_time = (
            datetime.combine(start_date, start_time) + timedelta(minutes=plan_course.duration)
        ).time()
        # 跨午夜的课程不适合在日历中拆分，明确提示康复师调整时长。
        if end_time <= start_time:
            raise ValueError("课程时长不能跨越午夜，请调整开始时间")
    try:
        session_count = Decimal(str(options.get("session_count", plan_course.session_cost)))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValueError("单次课程数量应为正数") from exc
    if session_count <= 0:
        raise ValueError("单次课程数量应为正数")
    if session_count * 2 != int(session_count * 2):
        raise ValueError("单次课程数量应以 0.5 为最小单位")
    return {
        "start_date": start_date,
        "weekdays": weekdays,
        "frequency": frequency,
        "start_time": start_time,
        "end_time": end_time,
        "session_topic": options.get("session_topic") or plan_course.course_type.name,
        "session_count": session_count,
    }


def _generate_batch_candidates(plan_course: RehabPlanCourse, options: dict) -> list[dict]:
    """按计划余量生成候选日期，不写入数据库。"""
    options = _batch_options(options, plan_course)
    progress = plan_course_progress(plan_course)
    remaining = progress["unscheduled_count"]
    if remaining <= 0:
        raise ValueError("该课程已全部安排，无需继续安排")
    start_date = options["start_date"]
    plan = plan_course.rehab_plan
    if start_date < plan.start_date:
        raise ValueError("开始日期不能早于课程计划开始日期")
    if plan.end_date and start_date > plan.end_date:
        raise ValueError("开始日期不能晚于课程计划结束日期")
    candidates: list[dict] = []
    # 无结束日期时最多向后查找一年，避免异常参数导致服务长时间循环。
    last_date = plan.end_date or (start_date + timedelta(days=366))
    current = start_date
    while current <= last_date and len(candidates) < remaining:
        api_weekday = (current.weekday() + 1) % 7
        if api_weekday in options["weekdays"]:
            candidates.append(
                {
                    "date": current,
                    "start_time": options["start_time"],
                    "end_time": options["end_time"],
                    "session_topic": options["session_topic"],
                    "session_count": Decimal(str(options["session_count"])),
                }
            )
        current += timedelta(days=1)
    if len(candidates) < remaining:
        raise ValueError("课程计划剩余次数无法在有效日期内全部安排，请调整开始日期或上课频率")
    return candidates


def _candidate_output(plan_course: RehabPlanCourse, candidate: dict, conflict=None) -> dict:
    """将候选课程转换为前端预览结构。"""
    result = {
        "id": None,
        "customer": plan_course.rehab_plan.customer_id,
        "customer_name": plan_course.rehab_plan.customer.name,
        "plan_course": plan_course.id,
        "plan_course_name": plan_course.course_type.name,
        "rehab_plan_name": plan_course.rehab_plan.name,
        "arrangement_type": CourseArrangementType.PLAN,
        "arrangement_type_display": CourseArrangementType.PLAN.label,
        "session_topic": candidate["session_topic"],
        "session_count": candidate["session_count"],
        "date": candidate["date"].isoformat(),
        "start_time": candidate["start_time"].isoformat() if candidate["start_time"] else None,
        "end_time": candidate["end_time"].isoformat() if candidate["end_time"] else None,
        "status": CourseSessionStatus.SCHEDULED,
        "status_display": CourseSessionStatus.SCHEDULED.label,
        "session_consumed": False,
        "training_record_id": None,
        "note": "",
    }
    if conflict is not None:
        result["conflict"] = format_conflict_message(conflict.date, conflict.start_time)
    return result


def _build_conflicts(therapist, candidates: list[dict]) -> list[dict]:
    conflicts: list[dict] = []
    for candidate in candidates:
        conflict = find_session_time_conflict(
            therapist,
            candidate["date"],
            candidate["start_time"],
            candidate["end_time"],
        )
        if conflict is not None:
            conflicts.append(
                {
                    "date": candidate["date"].isoformat(),
                    "start_time": candidate["start_time"].isoformat(),
                    "end_time": candidate["end_time"].isoformat(),
                    "existing_session_id": conflict.id,
                    "message": format_conflict_message(conflict.date, conflict.start_time),
                }
            )
    return conflicts


def _get_locked_plan_course(
    therapist: AbstractUser,
    plan_course,
    *,
    for_update: bool = True,
) -> RehabPlanCourse:
    """获取当前康复师的计划内课程；确认阶段可选择加行锁。"""
    course_id = getattr(plan_course, "id", plan_course)
    queryset = RehabPlanCourse.objects.select_related(
        "rehab_plan__customer", "course_type"
    ).filter(id=course_id, rehab_plan__therapist=therapist)
    if for_update:
        queryset = queryset.select_for_update()
    locked = queryset.first()
    if locked is None:
        raise ValueError("计划内课程不存在或无权访问")
    if locked.rehab_plan.status != "active":
        raise ValueError("已结束的课程计划不能安排课程")
    if locked.status != PlanCourseStatus.ACTIVE:
        raise ValueError("只能为进行中的计划内课程安排课程")
    return locked


def preview_batch_schedule(therapist: AbstractUser, data: dict) -> dict:
    """生成批量排课预览，不写数据库。"""
    plan_course = _get_locked_plan_course(
        therapist, data.get("plan_course"), for_update=False
    )
    customer = data.get("customer")
    if customer is not None:
        if customer.therapist_id != therapist.id:
            raise ValueError("无权为该客户安排课程")
        if customer.id != plan_course.rehab_plan.customer_id:
            raise ValueError("客户与计划内课程不一致")
    candidates = _generate_batch_candidates(plan_course, data)
    conflicts = _build_conflicts(therapist, candidates)
    items = []
    for candidate in candidates:
        conflict = next(
            (
                item
                for item in conflicts
                if item["date"] == candidate["date"].isoformat()
                and item["start_time"]
                == (candidate["start_time"].isoformat() if candidate["start_time"] else None)
            ),
            None,
        )
        items.append(_candidate_output(plan_course, candidate, conflict))
    progress = plan_course_progress(plan_course)
    return {
        "plan_course": plan_course.id,
        "customer": plan_course.rehab_plan.customer_id,
        "requested_count": len(candidates),
        "total_count": len(candidates),
        "scheduled_count": progress["scheduled_count"],
        "unscheduled_count": progress["unscheduled_count"],
        "items": items,
        "sessions": items,
        "conflicts": conflicts,
        "can_confirm": not conflicts,
    }


@transaction.atomic
def confirm_batch_schedule(therapist: AbstractUser, data: dict) -> dict:
    """原子确认批量排课；确认时重新计算余量并检查冲突。"""
    plan_course = _get_locked_plan_course(therapist, data.get("plan_course"))
    customer = data.get("customer")
    if customer is not None:
        if customer.therapist_id != therapist.id:
            raise ValueError("无权为该客户安排课程")
        if customer.id != plan_course.rehab_plan.customer_id:
            raise ValueError("客户与计划内课程不一致")
    candidates = _generate_batch_candidates(plan_course, data)
    conflicts = _build_conflicts(therapist, candidates)
    if conflicts:
        raise BatchScheduleConflictError(conflicts)
    sessions = [
        CourseSession(
            therapist=therapist,
            customer_id=plan_course.rehab_plan.customer_id,
            plan_course=plan_course,
            arrangement_type=CourseArrangementType.PLAN,
            session_topic=candidate["session_topic"],
            session_count=candidate["session_count"],
            date=candidate["date"],
            start_time=candidate["start_time"],
            end_time=candidate["end_time"],
            status=CourseSessionStatus.SCHEDULED,
        )
        for candidate in candidates
    ]
    CourseSession.objects.bulk_create(sessions)
    return {
        "plan_course": plan_course.id,
        "customer": plan_course.rehab_plan.customer_id,
        "created_count": len(sessions),
        "items": sessions,
        "sessions": sessions,
        "conflicts": [],
    }


@transaction.atomic
def adjust_plan_course_count(
    therapist: AbstractUser,
    plan_course: RehabPlanCourse,
    delta_count: int,
    reason: str,
    assessment=None,
) -> RehabPlanCourse:
    """增减计划内课程次数并保留调整前后快照。

    调整后的次数不得小于“已完成 + 待上课”次数；逾期但尚未处理的排课也
    属于待上课，康复师应先取消或改期后再减少计划次数。
    """
    if delta_count == 0:
        raise ValueError("调整次数不能为 0")
    if not reason.strip():
        raise ValueError("调整课程次数必须填写原因")

    locked = (
        RehabPlanCourse.objects.select_for_update()
        .select_related("rehab_plan__customer")
        .get(id=plan_course.id)
    )
    if locked.rehab_plan.therapist_id != therapist.id:
        raise ValueError("无权操作该计划内课程")
    completed_count = completed_session_count(locked)
    scheduled_count = scheduled_session_count(locked)
    before_count = locked.planned_count
    after_count = before_count + delta_count
    minimum_count = completed_count + scheduled_count
    if after_count < minimum_count:
        if scheduled_count:
            raise ValueError(
                f"调整后次数不能少于已完成 {completed_count} 次和已安排 {scheduled_count} 次，"
                "请先处理多出的待上课课程"
            )
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
