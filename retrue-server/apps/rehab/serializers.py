"""rehab：康复计划与阶段序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.rehab.models import RehabPlan, RehabStage


class RehabStageSerializer(serializers.ModelSerializer):
    """康复阶段输出。"""

    stage_type_display = serializers.CharField(source="get_stage_type_display", read_only=True)
    customer = serializers.IntegerField(source="plan.customer_id", read_only=True)
    customer_name = serializers.CharField(source="plan.customer.name", read_only=True)

    class Meta:
        model = RehabStage
        fields = [
            "id",
            "customer",
            "customer_name",
            "plan",
            "stage_type",
            "stage_type_display",
            "start_date",
            "end_date",
            "note",
        ]


class RehabPlanSerializer(serializers.ModelSerializer):
    """康复周期计划输出/输入。"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    stages = RehabStageSerializer(many=True, read_only=True)
    course_count = serializers.IntegerField(source="plan_courses.count", read_only=True)

    class Meta:
        model = RehabPlan
        fields = [
            "id",
            "customer",
            "customer_name",
            "name",
            "start_date",
            "end_date",
            "status",
            "status_display",
            "goals",
            "note",
            "stages",
            "course_count",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"start_date": {"required": True}}

    def validate(self, attrs: dict) -> dict:
        """校验周期结束日期不早于开始日期。"""
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "结束日期不能早于开始日期"})
        return attrs
