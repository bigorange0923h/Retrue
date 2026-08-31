"""assessments：评估序列化器。"""

from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from apps.assessments.metric_definitions import MetricValidationError, validate_metric_payload
from apps.assessments.models import Assessment, AssessmentMetric


class AssessmentMetricSerializer(serializers.ModelSerializer):
    """评估指标输入/输出。

    ``score_max``、``scale_code`` 和 ``unit`` 是服务端派生字段，保留在响应中
    方便展示和趋势服务，但不接受客户端决定其值。
    """

    metric_type_display = serializers.CharField(source="get_metric_type_display", read_only=True)

    class Meta:
        model = AssessmentMetric
        fields = [
            "id",
            "metric_type",
            "metric_type_display",
            "body_part",
            "side",
            "context",
            "movement",
            "measurement_mode",
            "score",
            "score_max",
            "scale_code",
            "unit",
            "result_code",
            "details",
            "description",
            "sort_order",
        ]
        extra_kwargs = {
            # id 允许写，用于更新时按原 id 做差异同步；新建或旧客户端不传则忽略。
            "id": {"read_only": False, "required": False},
            "metric_type": {"required": True},
            "body_part": {"required": False, "allow_blank": True},
            "side": {"required": False, "allow_blank": True},
            "context": {"required": False, "allow_blank": True},
            "movement": {"required": False, "allow_blank": True},
            "measurement_mode": {"required": False, "allow_blank": True},
            "score": {"required": False, "allow_null": True},
            "result_code": {"required": False, "allow_blank": True},
            "details": {"required": False, "allow_null": True},
            "description": {"required": False, "allow_blank": True},
            "sort_order": {"required": False},
            "score_max": {"read_only": True},
            "scale_code": {"read_only": True},
            "unit": {"read_only": True},
        }

    def validate(self, attrs: dict) -> dict:
        """执行类型校验并写入服务端派生字段。"""
        payload = {}
        if self.instance is not None:
            for field in (
                "metric_type",
                "body_part",
                "side",
                "context",
                "movement",
                "measurement_mode",
                "score",
                "score_max",
                "scale_code",
                "unit",
                "result_code",
                "details",
                "description",
            ):
                payload[field] = getattr(self.instance, field)
        payload.update(attrs)
        try:
            normalized = validate_metric_payload(
                payload,
                require_complete=bool(self.context.get("validate_complete")),
            )
        except MetricValidationError as exc:
            raise serializers.ValidationError({exc.field: exc.message}) from exc

        # 只覆盖当前 serializer 允许写入的字段，避免把模型实例的 id 或审计
        # 时间等内部字段误传给 nested create。
        for field in ("score", "score_max", "scale_code", "unit", "details"):
            if field in normalized:
                attrs[field] = normalized[field]
        return attrs


class AssessmentSerializer(serializers.ModelSerializer):
    """评估输出，包含指标及主观情况快照。"""

    assessment_type_display = serializers.CharField(source="get_assessment_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    onset_mode_display = serializers.CharField(source="get_onset_mode_display", read_only=True)
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
            "status",
            "status_display",
            "assessment_date",
            "completed_at",
            "chief_complaint",
            "medical_history",
            "rehab_goal",
            "current_status",
            "note",
            "onset_date",
            "onset_description",
            "onset_mode",
            "onset_mode_display",
            "aggravating_factors",
            "relieving_factors",
            "prior_care",
            "surgery_history",
            "medication",
            "exercise_habits",
            "work_demands",
            "sleep_impact",
            "metrics",
            "created_at",
            "updated_at",
        ]


class AssessmentCreateSerializer(serializers.ModelSerializer):
    """评估创建/更新输入，支持嵌套指标。

    状态不在输入字段中暴露；新建评估一律从草稿开始，完成动作由独立接口
    执行完整校验后设置为 ``completed``。
    """

    status = serializers.CharField(read_only=True)
    completed_at = serializers.DateTimeField(read_only=True)
    metrics = AssessmentMetricSerializer(many=True, required=False)

    class Meta:
        model = Assessment
        fields = [
            "customer",
            "plan",
            "assessment_type",
            "status",
            "completed_at",
            "assessment_date",
            "chief_complaint",
            "medical_history",
            "rehab_goal",
            "current_status",
            "note",
            "onset_date",
            "onset_description",
            "onset_mode",
            "aggravating_factors",
            "relieving_factors",
            "prior_care",
            "surgery_history",
            "medication",
            "exercise_habits",
            "work_demands",
            "sleep_impact",
            "metrics",
        ]
        extra_kwargs = {
            "assessment_date": {"required": True},
            "chief_complaint": {"required": False, "allow_blank": True},
            "medical_history": {"required": False, "allow_blank": True},
            "rehab_goal": {"required": False, "allow_blank": True},
            "current_status": {"required": False, "allow_blank": True},
            "note": {"required": False, "allow_blank": True},
            "onset_description": {"required": False, "allow_blank": True},
            "onset_mode": {"required": False, "allow_blank": True},
            "aggravating_factors": {"required": False, "allow_blank": True},
            "relieving_factors": {"required": False, "allow_blank": True},
            "prior_care": {"required": False, "allow_blank": True},
            "surgery_history": {"required": False, "allow_blank": True},
            "medication": {"required": False, "allow_blank": True},
            "exercise_habits": {"required": False, "allow_blank": True},
            "work_demands": {"required": False, "allow_blank": True},
            "sleep_impact": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs: dict) -> dict:
        """阻止更新时改绑客户或改变首评/复评生命周期类型。"""
        if attrs.get("onset_mode", None) == "":
            attrs["onset_mode"] = "unknown"
        if self.instance is not None and "customer" in attrs:
            if attrs["customer"].id != self.instance.customer_id:
                raise serializers.ValidationError({"customer": "评估所属客户不能修改"})
        if self.instance is not None and "assessment_type" in attrs:
            if attrs["assessment_type"] != self.instance.assessment_type:
                raise serializers.ValidationError({"assessment_type": "评估类型不能修改"})
        return attrs

    def validate_onset_mode(self, value: str) -> str:
        """将草稿表单可能提交的空选项归一为“不清楚”。"""
        return value or "unknown"

    @transaction.atomic
    def create(self, validated_data: dict) -> Assessment:
        """创建评估及其指标；客户端不能直接创建已完成评估。"""
        metrics_data = validated_data.pop("metrics", [])
        # 即使调用方通过 serializer.save(status=...) 传入状态，也不能绕过
        # 独立的 complete 接口直接创建已完成评估。
        validated_data.pop("status", None)
        validated_data.pop("completed_at", None)
        assessment = Assessment.objects.create(
            status="draft",
            completed_at=None,
            **validated_data,
        )
        self._create_metrics(assessment, metrics_data)
        return assessment

    @transaction.atomic
    def update(self, instance: Assessment, validated_data: dict) -> Assessment:
        """更新评估并同步指标（按 id 差异更新，保留已有指标 id）。"""
        metrics_data = validated_data.pop("metrics", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if metrics_data is not None:
            self._sync_metrics(instance, metrics_data)
            if hasattr(instance, "_prefetched_objects_cache"):
                instance._prefetched_objects_cache.pop("metrics", None)
        return instance

    def _sync_metrics(self, assessment: Assessment, metrics_data: list) -> None:
        """按提交的指标 id 做差异同步。

        - 提交项带 ``id`` 且属于当前评估：更新已有指标，保留原 id。
        - 提交项不带 ``id``（新增指标）：创建新指标。
        - 已存在但未出现在本次提交中的指标：删除。

        相比“整体删除后重建”，能保留指标 id，避免前端按 id 做 diff 或高亮时失配。
        """
        existing_ids = set(assessment.metrics.values_list("id", flat=True))
        submitted_ids: list[int] = []
        require_complete = bool(self.context.get("validate_complete"))

        for index, item in enumerate(metrics_data):
            normalized = validate_metric_payload(item, require_complete=require_complete)
            metric_id = item.get("id")
            normalized.pop("id", None)
            normalized["sort_order"] = item.get("sort_order", index)

            if metric_id is not None and metric_id in existing_ids:
                metric = assessment.metrics.filter(pk=metric_id).first()
                if metric is None:
                    # 带了一个不属于本评估的 id：视为新增，忽略该 id。
                    metric = AssessmentMetric.objects.create(assessment=assessment, **normalized)
                else:
                    for field, value in normalized.items():
                        setattr(metric, field, value)
                    metric.save()
                submitted_ids.append(metric.id)
            else:
                metric = AssessmentMetric.objects.create(assessment=assessment, **normalized)
                submitted_ids.append(metric.id)

        if submitted_ids:
            assessment.metrics.exclude(pk__in=submitted_ids).delete()
        else:
            assessment.metrics.all().delete()

    def _create_metrics(self, assessment: Assessment, metrics_data: list) -> None:
        """批量创建评估指标，并再次应用服务端派生规则。"""
        for index, item in enumerate(metrics_data):
            normalized = validate_metric_payload(
                item,
                require_complete=bool(self.context.get("validate_complete")),
            )
            # normalized 可能包含旧客户端提交但 serializer 不应落库的字段，
            # 只保留 AssessmentMetric 的业务字段。
            normalized.pop("id", None)
            normalized["sort_order"] = item.get("sort_order", index)
            AssessmentMetric.objects.create(assessment=assessment, **normalized)
