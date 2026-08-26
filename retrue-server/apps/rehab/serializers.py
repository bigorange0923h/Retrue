"""rehab：康复计划与阶段序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.rehab.models import RehabPlan, RehabStage


class RehabStageSerializer(serializers.ModelSerializer):
    """康复阶段输出/输入。"""

    stage_type_display = serializers.CharField(source="get_stage_type_display", read_only=True)

    class Meta:
        model = RehabStage
        fields = [
            "id",
            "customer",
            "plan",
            "stage_type",
            "stage_type_display",
            "start_date",
            "end_date",
            "note",
        ]
        extra_kwargs = {"stage_type": {"required": True}, "start_date": {"required": True}}


class RehabPlanSerializer(serializers.ModelSerializer):
    """康复计划输出/输入。"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    stages = RehabStageSerializer(many=True, read_only=True)

    class Meta:
        model = RehabPlan
        fields = [
            "id",
            "customer",
            "customer_name",
            "name",
            "start_date",
            "status",
            "status_display",
            "note",
            "stages",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"start_date": {"required": True}}
