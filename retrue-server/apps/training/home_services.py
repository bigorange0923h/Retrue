"""家庭训练交付服务：计划、动作和审计共同提交或回滚。"""

from django.db import transaction

from apps.audit.models import AuditAction, write_audit_log
from apps.training.models import HomeTrainingPlan
from apps.training.serializers import HomeTrainingPlanCreateSerializer, HomeTrainingPlanSerializer


@transaction.atomic
def create_home_plan(therapist, serializer: HomeTrainingPlanCreateSerializer) -> HomeTrainingPlan:
    """保存已校验的家庭训练及完整动作明细，审计失败时回滚。"""
    plan = serializer.save(therapist=therapist)
    write_audit_log(actor=therapist, action=AuditAction.CREATE, obj=plan,
                    after=dict(HomeTrainingPlanSerializer(plan).data), reason="新建家庭训练计划")
    return plan


def update_home_plan(therapist, plan: HomeTrainingPlan, serializer: HomeTrainingPlanCreateSerializer) -> HomeTrainingPlan:
    """更新已锁定计划并记录完整前后明细，调用方保证事务和权限。"""
    before = dict(HomeTrainingPlanSerializer(plan).data)
    updated = serializer.save()
    # 预取动作已被整体替换，清除旧缓存后才记录最新明细。
    updated._prefetched_objects_cache = {}
    write_audit_log(actor=therapist, action=AuditAction.UPDATE, obj=updated,
                    before=before, after=dict(HomeTrainingPlanSerializer(updated).data), reason="编辑家庭训练计划")
    return updated
