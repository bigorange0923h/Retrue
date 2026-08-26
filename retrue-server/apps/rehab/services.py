"""rehab：康复计划与阶段业务服务。"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

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
        .prefetch_related("stages")
    )


def get_plan(therapist: AbstractUser, plan_id: int) -> RehabPlan | None:
    """获取属于当前康复师的康复计划。

    参数：
        therapist: 当前康复师。
        plan_id: 计划主键。
    返回：
        计划实例；不存在或无权访问时返回 None。
    """
    return RehabPlan.objects.filter(therapist=therapist, id=plan_id).prefetch_related("stages").first()


def create_plan(therapist: AbstractUser, data: dict) -> RehabPlan:
    """创建康复计划并记录审计。

    参数：
        therapist: 当前康复师。
        data: 计划字段数据。
    返回：
        新建的计划实例。
    """
    plan = RehabPlan.objects.create(therapist=therapist, **data)
    write_audit_log(actor=therapist, action=AuditAction.CREATE, obj=plan, after={"name": plan.name}, reason="创建康复计划")
    return plan


def set_stage(therapist: AbstractUser, data: dict) -> RehabStage:
    """为客户设置康复阶段（手动调整）。

    自动关闭该客户上一条未结束的阶段，确保同一时间只有一个有效阶段。

    参数：
        therapist: 当前康复师。
        data: 阶段字段数据。
    返回：
        新建的阶段实例。
    """
    customer = data.get("customer")
    customer_id = customer.id if customer is not None else None
    # 关闭之前的有效阶段
    RehabStage.objects.filter(
        therapist=therapist, customer_id=customer_id, end_date__isnull=True
    ).update(end_date=data.get("start_date"))
    stage = RehabStage.objects.create(therapist=therapist, **data)
    write_audit_log(
        actor=therapist,
        action=AuditAction.CREATE,
        obj=stage,
        after={"stage_type": stage.stage_type, "customer_id": customer_id},
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
        RehabStage.objects.filter(therapist=therapist, customer_id=customer_id, end_date__isnull=True)
        .order_by("-start_date")
        .first()
    )
