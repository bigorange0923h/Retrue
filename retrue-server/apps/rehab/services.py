"""rehab：康复计划与阶段业务服务。"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, transaction

from apps.audit.models import AuditAction, write_audit_log
from apps.rehab.models import RehabPlan, RehabStage


def list_plans(therapist: AbstractUser, customer_id: int) -> list:
    """查询某客户的康复计划列表。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
    返回：
        康复计划列表（含阶段）。
    """
    return list(
        RehabPlan.objects.filter(therapist=therapist, customer_id=customer_id)
        .prefetch_related("stages", "plan_courses")
    )


def get_plan(therapist: AbstractUser, plan_id: int) -> RehabPlan | None:
    """获取属于当前康复师的康复计划。

    参数：
        therapist: 当前康复师。
        plan_id: 计划主键。
    返回：
        计划实例；不存在或无权访问时返回 None。
    """
    return (
        RehabPlan.objects.filter(therapist=therapist, id=plan_id)
        .prefetch_related("stages", "plan_courses")
        .first()
    )


def create_plan(therapist: AbstractUser, data: dict) -> RehabPlan:
    """创建康复计划并记录审计。

    参数：
        therapist: 当前康复师。
        data: 计划字段数据。
    返回：
        新建的计划实例。
    """
    customer = data.get("customer")
    try:
        with transaction.atomic():
            customer.__class__.objects.select_for_update().get(id=customer.id)
            if data.get("status", "active") == "active" and RehabPlan.objects.filter(
                therapist=therapist, customer=customer, status="active"
            ).exists():
                raise ValueError("该客户已有进行中的康复周期，请先结束原周期")
            plan = RehabPlan.objects.create(therapist=therapist, **data)
            write_audit_log(
                actor=therapist,
                action=AuditAction.CREATE,
                obj=plan,
                after={"name": plan.name},
                reason="创建康复计划",
            )
            return plan
    except IntegrityError as exc:
        raise ValueError("该客户已有进行中的康复周期，请先结束原周期") from exc


def update_plan(therapist: AbstractUser, plan: RehabPlan, data: dict) -> RehabPlan:
    """更新康复周期计划并记录审计。"""
    try:
        with transaction.atomic():
            locked = RehabPlan.objects.select_for_update().select_related("customer").get(id=plan.id)
            locked.customer.__class__.objects.select_for_update().get(id=locked.customer_id)
            if data.get("status") == "active" and RehabPlan.objects.filter(
                therapist=therapist,
                customer=locked.customer,
                status="active",
            ).exclude(id=locked.id).exists():
                raise ValueError("该客户已有其他进行中的康复周期")
            before = {
                "name": locked.name,
                "start_date": locked.start_date,
                "end_date": locked.end_date,
                "status": locked.status,
                "goals": locked.goals,
            }
            for field, value in data.items():
                setattr(locked, field, value)
            current_stage = locked.stages.filter(end_date__isnull=True).first()
            if (
                locked.status == "closed"
                and locked.end_date is not None
                and current_stage is not None
                and locked.end_date < current_stage.start_date
            ):
                raise ValueError("周期结束日期不能早于当前阶段的进入日期")
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
                reason="更新康复周期计划",
            )
            return locked
    except IntegrityError as exc:
        raise ValueError("该客户已有其他进行中的康复周期") from exc


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
        raise ValueError("无权操作该康复周期")
    if plan.status != "active":
        raise ValueError("已结束的康复周期不能设置阶段")
    start_date = data["start_date"]
    end_date = data.get("end_date")
    if start_date < plan.start_date or (plan.end_date and start_date > plan.end_date):
        raise ValueError("阶段进入日期必须位于康复周期内")
    if end_date and (end_date < start_date or (plan.end_date and end_date > plan.end_date)):
        raise ValueError("阶段结束日期必须位于康复周期内且不早于进入日期")
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
