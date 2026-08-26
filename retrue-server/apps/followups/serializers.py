"""followups：回访/复查序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.followups.models import FollowUpTask


class FollowUpSerializer(serializers.ModelSerializer):
    """回访/复查输出/输入。"""

    followup_type_display = serializers.CharField(source="get_followup_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = FollowUpTask
        fields = [
            "id",
            "customer",
            "customer_name",
            "followup_type",
            "followup_type_display",
            "due_date",
            "content",
            "status",
            "status_display",
            "result",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"due_date": {"required": True}}
