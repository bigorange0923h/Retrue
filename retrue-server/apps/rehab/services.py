"""rehab：康复计划与阶段业务服务。"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q

from apps.audit.models import AuditAction, write_audit_log
from apps.rehab.models import RehabPlan, RehabPlanTemplate, RehabPlanTemplateCourse, RehabStage
from apps.schedules.models import CourseSession, CourseSessionStatus, RehabPlanCourse


def list_plan_templates(
    therapist: AbstractUser,
    keyword: str = "",
    active_only: bool = False,
):
    """查询当前康复师的课程计划模板，并预取课程组成。"""
    queryset = RehabPlanTemplate.objects.filter(therapist=therapist).prefetch_related(
        "courses__course_type"
    )
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset


def get_plan_template(
    therapist: AbstractUser,
    template_id: int,
) -> RehabPlanTemplate | None:
    """获取属于当前康复师的一条课程计划模板。"""
    return (
        RehabPlanTemplate.objects.filter(therapist=therapist, id=template_id)
        .prefetch_related("courses__course_type")
        .first()
    )


def _validate_template_courses(
    therapist: AbstractUser,
    courses: list[dict],
    is_active: bool,
) -> None:
    """校验课程计划模板中的课程归属和启用状态。"""
    for item in courses:
        course_type = item["course_type"]
        if course_type.therapist_id != therapist.id:
            raise ValueError("课程计划模板中包含无权使用的课程模板")
        if is_active and not course_type.is_active:
            raise ValueError(f"课程模板“{course_type.name}”已停用，不能加入启用的课程计划模板")


@transaction.atomic
def create_plan_template(therapist: AbstractUser, data: dict) -> RehabPlanTemplate:
    """创建课程计划模板及其课程组成。"""
    courses = data.pop("courses", [])
    is_active = data.get("is_active", True)
    _validate_template_courses(therapist, courses, is_active)
    template = RehabPlanTemplate.objects.create(therapist=therapist, **data)
    RehabPlanTemplateCourse.objects.bulk_create(
        [
            RehabPlanTemplateCourse(template=template, **item)
            for item in courses
        ]
    )
    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=template,
        after={"name": template.name, "course_count": len(courses)},
        reason="创建课程计划模板",
    )
    return get_plan_template(therapist, template.id) or template


@transaction.atomic
def update_plan_template(
    therapist: AbstractUser,
    template: RehabPlanTemplate,
    data: dict,
) -> RehabPlanTemplate:
    """更新课程计划模板；替换模板课程但不修改已创建的客户计划。"""
    courses = data.pop("courses", None)
    is_active = data.get("is_active", template.is_active)
    if courses is not None:
        _validate_template_courses(therapist, courses, is_active)
    elif is_active:
        _validate_template_courses(
            therapist,
            [{"course_type": item.course_type} for item in template.courses.select_related("course_type")],
            is_active,
        )
    before = {
        "name": template.name,
        "is_active": template.is_active,
        "course_count": template.courses.count(),
    }
    for field, value in data.items():
        setattr(template, field, value)
    template.save()
    if courses is not None:
        template.courses.all().delete()
        RehabPlanTemplateCourse.objects.bulk_create(
            [
                RehabPlanTemplateCourse(template=template, **item)
                for item in courses
            ]
        )
    write_audit_log(
        actor=therapist,
        action=AuditAction.UPDATE,
        obj=template,
        before=before,
        after={
            "name": template.name,
            "is_active": template.is_active,
            "course_count": template.courses.count(),
        },
        reason="更新课程计划模板",
    )
    return get_plan_template(therapist, template.id) or template


def list_plans(therapist: AbstractUser, customer_id: int) -> list:
    """查询某客户的课程计划列表。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
    返回：
        课程计划列表（含康复阶段）。
    """
    return list(
        RehabPlan.objects.filter(therapist=therapist, customer_id=customer_id)
        .prefetch_related(
            "stages",
            Prefetch(
                "plan_courses",
                queryset=RehabPlanCourse.objects.select_related(
                    "course_type", "package"
                ).prefetch_related(
                    Prefetch(
                        "sessions",
                        queryset=CourseSession.objects.select_related(
                            "customer", "plan_course__course_type", "plan_course__rehab_plan"
                        ).prefetch_related("training_records"),
                        to_attr="_integration_sessions",
                    )
                ),
            ),
        )
    )


def get_plan(therapist: AbstractUser, plan_id: int) -> RehabPlan | None:
    """获取属于当前康复师的课程计划。

    参数：
        therapist: 当前康复师。
        plan_id: 计划主键。
    返回：
        计划实例；不存在或无权访问时返回 None。
    """
    return (
        RehabPlan.objects.filter(therapist=therapist, id=plan_id)
        .prefetch_related(
            "stages",
            Prefetch(
                "plan_courses",
                queryset=RehabPlanCourse.objects.select_related(
                    "course_type", "package"
                ).prefetch_related(
                    Prefetch(
                        "sessions",
                        queryset=CourseSession.objects.select_related(
                            "customer", "plan_course__course_type", "plan_course__rehab_plan"
                        ).prefetch_related("training_records"),
                        to_attr="_integration_sessions",
                    )
                ),
            ),
        )
        .first()
    )


def create_plan(therapist: AbstractUser, data: dict) -> RehabPlan:
    """创建客户课程计划并记录审计。

    参数：
        therapist: 当前康复师。
        data: 计划字段数据。
    返回：
        新建的计划实例。
    """
    data = dict(data)
    customer = data.get("customer")
    course_drafts = data.pop("courses", None)
    source_template = data.get("source_template")
    if source_template is not None:
        if source_template.therapist_id != therapist.id:
            raise ValueError("无权使用该课程计划模板")
        if not source_template.is_active:
            raise ValueError("该课程计划模板已停用")
        if course_drafts is None:
            course_drafts = [
                {
                    "course_type": item.course_type,
                    "planned_count": item.planned_count,
                    "session_cost": item.session_cost,
                    "duration": item.duration,
                    "goals": item.goals,
                }
                for item in source_template.courses.select_related("course_type")
            ]
    course_drafts = course_drafts or []
    if source_template is not None and not course_drafts:
        raise ValueError("从课程计划模板创建客户计划时至少保留一门课程")
    course_type_ids: set[int] = set()
    for item in course_drafts:
        course_type = item["course_type"]
        package = item.get("package")
        if course_type.id in course_type_ids:
            raise ValueError("同一客户计划不能重复添加相同课程")
        course_type_ids.add(course_type.id)
        if course_type.therapist_id != therapist.id:
            raise ValueError("客户计划中包含无权使用的课程模板")
        if not course_type.is_active:
            raise ValueError(f"课程模板“{course_type.name}”已停用")
        if package is not None and (
            package.therapist_id != therapist.id or package.customer_id != customer.id
        ):
            raise ValueError("课时包与课程计划客户不一致")
    try:
        with transaction.atomic():
            customer.__class__.objects.select_for_update().get(id=customer.id)
            if data.get("status", "active") == "active" and RehabPlan.objects.filter(
                therapist=therapist, customer=customer, status="active"
            ).exists():
                raise ValueError("该客户已有进行中的课程计划，请先结束原计划")
            plan = RehabPlan.objects.create(therapist=therapist, **data)
            for item in course_drafts:
                course_type = item["course_type"]
                RehabPlanCourse.objects.create(
                    rehab_plan=plan,
                    course_type=course_type,
                    package=item.get("package"),
                    planned_count=item["planned_count"],
                    session_cost=item.get("session_cost", course_type.default_session_cost),
                    duration=item.get("duration", course_type.default_duration),
                    goals=item.get("goals", course_type.default_goals),
                )
            write_audit_log(
                actor=therapist,
                action=AuditAction.CREATE,
                obj=plan,
                after={
                    "name": plan.name,
                    "source_template_id": plan.source_template_id,
                    "course_count": len(course_drafts),
                },
                reason="创建客户课程计划",
            )
            return plan
    except IntegrityError as exc:
        raise ValueError("该客户已有进行中的课程计划，请先结束原计划") from exc


def update_plan(therapist: AbstractUser, plan: RehabPlan, data: dict) -> RehabPlan:
    """更新客户课程计划并记录审计。"""
    try:
        with transaction.atomic():
            locked = RehabPlan.objects.select_for_update().select_related("customer").get(id=plan.id)
            locked.customer.__class__.objects.select_for_update().get(id=locked.customer_id)
            if data.get("status") == "active" and RehabPlan.objects.filter(
                therapist=therapist,
                customer=locked.customer,
                status="active",
            ).exclude(id=locked.id).exists():
                raise ValueError("该客户已有其他进行中的课程计划")
            before = {
                "name": locked.name,
                "start_date": locked.start_date,
                "end_date": locked.end_date,
                "status": locked.status,
                "goals": locked.goals,
            }
            requested_start_date = data.get("start_date", locked.start_date)
            requested_end_date = data.get("end_date", locked.end_date)
            pending_sessions = CourseSession.objects.filter(
                plan_course__rehab_plan_id=locked.id,
                status=CourseSessionStatus.SCHEDULED,
            )
            pending_count = pending_sessions.count()
            if requested_start_date is not None:
                early_count = pending_sessions.filter(date__lt=requested_start_date).count()
                if early_count:
                    raise ValueError(
                        f"开始日期晚于 {early_count} 节待上课课程，请先处理这些课程后再修改日期"
                    )
            if before["status"] != "closed" and locked.status != "closed" and data.get("status") == "closed":
                if pending_count:
                    raise ValueError(
                        f"该课程计划还有 {pending_count} 节待上课课程，请先取消或改期后再结束计划"
                    )
            if requested_end_date is not None:
                late_count = pending_sessions.filter(date__gt=requested_end_date).count()
                if late_count:
                    raise ValueError(
                        f"结束日期早于 {late_count} 节待上课课程，请先处理这些课程后再修改日期"
                    )
            for field, value in data.items():
                setattr(locked, field, value)
            current_stage = locked.stages.filter(end_date__isnull=True).first()
            if (
                locked.status == "closed"
                and locked.end_date is not None
                and current_stage is not None
                and locked.end_date < current_stage.start_date
            ):
                raise ValueError("计划结束日期不能早于当前阶段的进入日期")
            locked.save()
            if before["status"] != "closed" and locked.status == "closed":
                close_date = locked.end_date or date.today()
                for stage in locked.stages.filter(end_date__isnull=True):
                    stage.end_date = close_date
                    stage.save(update_fields=["end_date", "updated_at"])
            write_audit_log(
                actor=therapist,
                action=AuditAction.UPDATE,
                obj=locked,
                before=before,
                after={
                    "name": locked.name,
                    "start_date": locked.start_date,
                    "end_date": locked.end_date,
                    "status": locked.status,
                    "goals": locked.goals,
                },
                reason="更新客户课程计划",
            )
            return locked
    except IntegrityError as exc:
        raise ValueError("该客户已有其他进行中的课程计划") from exc


@transaction.atomic
def set_stage(therapist: AbstractUser, data: dict) -> RehabStage:
    """为客户设置康复阶段（手动调整）。

    自动关闭该客户上一条未结束的阶段，确保同一时间只有一个有效阶段。

    参数：
        therapist: 当前康复师。
        data: 阶段字段数据。
    返回：
        新建的阶段实例。
    """
    plan = RehabPlan.objects.select_for_update().get(id=data["plan"].id)
    if plan.therapist_id != therapist.id:
        raise ValueError("无权操作该课程计划")
    if plan.status != "active":
        raise ValueError("已结束的课程计划不能设置阶段")
    start_date = data["start_date"]
    end_date = data.get("end_date")
    if start_date < plan.start_date or (plan.end_date and start_date > plan.end_date):
        raise ValueError("阶段进入日期必须位于课程计划日期范围内")
    if end_date and (end_date < start_date or (plan.end_date and end_date > plan.end_date)):
        raise ValueError("阶段结束日期必须位于课程计划日期范围内且不早于进入日期")
    current_stage = RehabStage.objects.filter(plan=plan, end_date__isnull=True).first()
    if end_date is None and current_stage is not None and start_date < current_stage.start_date:
        raise ValueError("新阶段进入日期不能早于当前阶段")
    # 关闭之前的有效阶段
    if end_date is None:
        RehabStage.objects.filter(
            plan=plan, end_date__isnull=True
        ).update(end_date=start_date)
    stage = RehabStage.objects.create(**{**data, "plan": plan})
    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=stage,
        after={"stage_type": stage.stage_type, "customer_id": plan.customer_id},
        reason="设置康复阶段",
    )
    return stage


def get_current_stage(therapist: AbstractUser, customer_id: int) -> RehabStage | None:
    """获取客户当前有效阶段（未结束的阶段）。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
    返回：
        当前阶段实例；无则 None。
    """
    return (
        RehabStage.objects.filter(
            plan__therapist=therapist,
            plan__customer_id=customer_id,
            plan__status="active",
            end_date__isnull=True,
        )
        .order_by("-start_date")
        .first()
    )
