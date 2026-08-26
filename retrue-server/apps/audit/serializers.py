"""audit：审计日志序列化器。

用于审计日志列表查询的输出，不暴露敏感业务快照以外的附加信息。
"""

from __future__ import annotations

from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """审计日志输出。

    字段：
        id: 日志 ID。
        action: 动作类型。
        action_display: 动作类型中文名。
        actor_name: 操作人展示名。
        before_data: 操作前快照。
        after_data: 操作后快照。
        reason: 修改原因。
        created_at: 记录时间。
    """

    action_display = serializers.CharField(source="get_action_display", read_only=True)
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "action_display",
            "actor_name",
            "before_data",
            "after_data",
            "reason",
            "created_at",
        ]

    def get_actor_name(self, obj: AuditLog) -> str:
        """获取操作人展示名。"""
        if obj.actor_id is None:
            return "系统"
        return obj.actor.get_username() if obj.actor is not None else "系统"
