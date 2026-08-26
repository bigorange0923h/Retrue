"""assessments：评估序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.assessments.models import Assessment, AssessmentMetric


class AssessmentMetricSerializer(serializers.ModelSerializer):
    """评估指标输入/输出。"""

    metric_type_display = serializers.CharField(source="get_metric_type_display", read_only=True)

    class Meta:
        model = AssessmentMetric
        fields = [
            "id",
            "metric_type",
            "metric_type_display",
            "body_part",
            "score",
            "score_max",
            "description",
            "sort_order",
        ]
        extra_kwargs = {"metric_type": {"required": True}}


class AssessmentSerializer(serializers.ModelSerializer):
    """评估输出，包含指标。"""

    assessment_type_display = serializers.CharField(source="get_assessment_type_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    metrics = AssessmentMetricSerializer(many=True, read_only=True)

    class Meta:
        model = Assessment
        fields = [
            "id",
            "customer",
            "customer_name",
            "plan",
            "assessment_type",
            "assessment_type_display",
            "assessment_date",
            "chief_complaint",
            "medical_history",
            "rehab_goal",
            "current_status",
            "note",
            "metrics",
            "created_at",
            "updated_at",
        ]


class AssessmentCreateSerializer(serializers.ModelSerializer):
    """评估创建/更新输入，支持嵌套指标。"""

    metrics = AssessmentMetricSerializer(many=True, required=False)

    class Meta:
        model = Assessment
        fields = [
            "customer",
            "plan",
            "assessment_type",
            "assessment_date",
            "chief_complaint",
            "medical_history",
            "rehab_goal",
            "current_status",
            "note",
            "metrics",
        ]
        extra_kwargs = {"assessment_date": {"required": True}}

    def create(self, validated_data: dict) -> Assessment:
        """创建评估及其指标。"""
        metrics_data = validated_data.pop("metrics", [])
        assessment = Assessment.objects.create(**validated_data)
        self._create_metrics(assessment, metrics_data)
        return assessment

    def update(self, instance: Assessment, validated_data: dict) -> Assessment:
        """更新评估并同步指标（整体替换）。"""
        metrics_data = validated_data.pop("metrics", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if metrics_data is not None:
            instance.metrics.all().delete()
            self._create_metrics(instance, metrics_data)
        return instance

    def _create_metrics(self, assessment: Assessment, metrics_data: list) -> None:
        """批量创建评估指标。"""
        for index, item in enumerate(metrics_data):
            item["sort_order"] = item.get("sort_order", index)
            AssessmentMetric.objects.create(assessment=assessment, **item)
