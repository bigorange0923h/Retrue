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
            "assistant_task",
            "training_record",
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
    assistant_task_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    # 从排课入口发起补记时允许显式携带排课，服务层还会与统一任务上下文复核。
    course_session_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    client_request_id = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=128,
        write_only=True,
    )


class ConfirmedExerciseSerializer(serializers.Serializer):
    """康复师确认的单项训练动作结构。"""

    exercise_name = serializers.CharField(max_length=128, allow_blank=False)
    sets = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    reps = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    weight = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    duration_seconds = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    sort_order = serializers.IntegerField(required=False, min_value=0)


class ConfirmedTrainingSerializer(serializers.Serializer):
    """正式写入前经过严格校验的训练记录结构。"""

    training_date = serializers.DateField(required=False, allow_null=True)
    exercises = ConfirmedExerciseSerializer(many=True, required=False, default=list, max_length=100)
    customer_feedback = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    therapist_observation = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    next_plan = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")


class ConfirmDraftSerializer(serializers.Serializer):
    """确认草稿请求校验。

    confirmed 为人工编辑后的最终结果，customer_id 为确认客户。
    """

    customer_id = serializers.IntegerField(write_only=True)
    course_session_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    confirmed = ConfirmedTrainingSerializer(write_only=True)
    idempotency_key = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=128,
        write_only=True,
    )

    def to_internal_value(self, data):
        """兼容前端未选择训练日期时提交空字符串，由领域服务使用当天日期。"""
        if isinstance(data, dict) and isinstance(data.get("confirmed"), dict):
            data = data.copy()
            confirmed = data["confirmed"].copy()
            if confirmed.get("training_date") == "":
                confirmed.pop("training_date")
            data["confirmed"] = confirmed
        return super().to_internal_value(data)


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
