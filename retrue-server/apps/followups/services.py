"""回访写入服务：状态、结果、显式下一项与审计在同一事务提交。"""

from django.db import transaction

from apps.audit.models import AuditAction, write_audit_log
from apps.followups.models import FollowUpTask
from apps.followups.serializers import FollowUpSerializer


@transaction.atomic
def create_followup(therapist, data: dict) -> FollowUpTask:
    """创建已校验归属的跟进并保存审计，任一步失败全部回滚。"""
    task = FollowUpTask.objects.create(therapist=therapist, **data)
    write_audit_log(actor=therapist, action=AuditAction.CREATE, obj=task,
                    after=dict(FollowUpSerializer(task).data), reason="新建回访/复查")
    return task


def update_followup(therapist, task: FollowUpTask, serializer: FollowUpSerializer) -> tuple[FollowUpTask, FollowUpTask | None]:
    """更新锁定的跟进，下一项只由提交的 next_task 创建；调用方负责事务与行锁。"""
    before = dict(FollowUpSerializer(task).data)
    next_data = serializer.validated_data.pop("next_task", None)
    serializer.validated_data.pop("customer", None)
    updated = serializer.save()
    next_task = create_followup(therapist, {"customer": task.customer, **next_data}) if next_data is not None else None
    after = dict(FollowUpSerializer(updated).data)
    if next_task is not None:
        after["next_task_id"] = next_task.id
    write_audit_log(actor=therapist, action=AuditAction.UPDATE, obj=updated,
                    before=before, after=after, reason="更新回访状态与结果")
    return updated, next_task
