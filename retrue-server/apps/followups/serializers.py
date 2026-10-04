"""followups：回访/复查序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.followups.models import FollowUpStatus, FollowUpTask, FollowUpType


class NextFollowUpSerializer(serializers.Serializer):
    """显式安排同一客户的下一次跟进，不推测日期或自动续建。"""

    followup_type = serializers.ChoiceField(choices=FollowUpType.choices, default=FollowUpType.VISIT)
    due_date = serializers.DateField()
    content = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")


class FollowUpSerializer(serializers.ModelSerializer):
    """回访/复查输出/输入。"""

    followup_type_display = serializers.CharField(source="get_followup_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    next_task = NextFollowUpSerializer(required=False, write_only=True)

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
            "next_task",
        ]
        extra_kwargs = {"due_date": {"required": True}}

    def validate(self, attrs: dict) -> dict:
        """完成必须记录结果，跳过必须说明原因；下一项只接受显式完成操作。"""
        status = attrs.get("status", self.instance.status if self.instance else FollowUpStatus.PENDING)
        result = attrs.get("result", self.instance.result if self.instance else "").strip()
        if self.instance is not None and attrs.get("status") in {FollowUpStatus.DONE, FollowUpStatus.SKIPPED}:
            if attrs["status"] != self.instance.status and not attrs.get("result", "").strip():
                raise serializers.ValidationError({"result": "变更为完成或跳过时请明确填写本次结果或原因"})
        if status in {FollowUpStatus.DONE, FollowUpStatus.SKIPPED}:
            if not result or result in {"完成", "已完成", "跳过", "已跳过"}:
                message = "请填写实际回访结果" if status == FollowUpStatus.DONE else "请填写跳过原因"
                raise serializers.ValidationError({"result": message})
        if "result" in attrs:
            attrs["result"] = result
        if "next_task" in attrs:
            if not attrs["next_task"].get("due_date"):
                raise serializers.ValidationError({"next_task": "请明确填写下一项计划日期"})
            if self.instance is None or attrs.get("status") != FollowUpStatus.DONE:
                raise serializers.ValidationError({"next_task": "完成当前回访时才能显式安排下一项"})
            if self.instance.status != FollowUpStatus.PENDING:
                raise serializers.ValidationError({"next_task": "当前回访已处理，请单独新建后续回访"})
        customer = attrs.get("customer")
        if self.instance is not None and customer is not None and customer.id != self.instance.customer_id:
            raise serializers.ValidationError({"customer": "回访不能更换客户"})
        return attrs
