"""ai：AI 草稿序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.ai.models import AiDraft, RiskAlert


class AiDraftSerializer(serializers.ModelSerializer):
    """AI 草稿输出。

    不暴露完整原始敏感内容以外的附加信息，input_text 仅在有确认结果前展示。
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")

    class Meta:
        model = AiDraft
        fields = [
            "id",
            "status",
            "status_display",
            "customer",
            "customer_name",
            "input_text",
            "ai_result",
            "confirmed_result",
            "error_message",
            "created_at",
        ]


class ParseDraftSerializer(serializers.Serializer):
    """解析训练文本请求校验。"""

    input_text = serializers.CharField(max_length=5000, write_only=True)
    customer_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)


class ConfirmDraftSerializer(serializers.Serializer):
    """确认草稿请求校验。

    confirmed 为人工编辑后的最终结果，customer_id 为确认客户。
    """

    customer_id = serializers.IntegerField(write_only=True)
    confirmed = serializers.DictField(write_only=True)


class RiskAlertSerializer(serializers.ModelSerializer):
    """风险提醒输出。"""

    risk_level_display = serializers.CharField(source="get_risk_level_display", read_only=True)
    suggested_action_display = serializers.CharField(source="get_suggested_action_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = RiskAlert
        fields = [
            "id",
            "customer",
            "customer_name",
            "training_record",
            "risk_level",
            "risk_level_display",
            "evidence",
            "suggested_action",
            "suggested_action_display",
            "is_confirmed",
            "outcome",
            "created_at",
        ]
