"""rehab：康复计划与阶段序列化器。"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.courses.models import CoursePackage
from apps.rehab.models import (
    RehabPlan,
    RehabPlanTemplate,
    RehabPlanTemplateCourse,
    RehabStage,
)
from apps.schedules.models import CourseType


def validate_session_cost(value: Decimal) -> Decimal:
    """校验课时扣减量为大于零的 0.5 倍数。"""
    if value <= 0:
        raise serializers.ValidationError("课时扣减量必须大于 0")
    if value * 2 != int(value * 2):
        raise serializers.ValidationError("课时扣减量须为 0.5 的倍数")
    return value


class RehabPlanTemplateCourseSerializer(serializers.ModelSerializer):
    """课程计划模板中的课程组成。"""

    course_type_name = serializers.CharField(source="course_type.name", read_only=True)
    session_cost = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        required=False,
        coerce_to_string=False,
        validators=[validate_session_cost],
    )

    class Meta:
        model = RehabPlanTemplateCourse
        fields = [
            "id",
            "course_type",
            "course_type_name",
            "planned_count",
            "session_cost",
            "duration",
            "goals",
            "sort_order",
        ]

    def validate_planned_count(self, value: int) -> int:
        """计划模板中的课程次数必须大于零。"""
        if value <= 0:
            raise serializers.ValidationError("计划次数必须大于 0")
        return value


class RehabPlanTemplateSerializer(serializers.ModelSerializer):
    """课程计划模板及其课程组成的输入与输出。"""

    courses = RehabPlanTemplateCourseSerializer(many=True)
    status_display = serializers.SerializerMethodField()
    usage_count = serializers.IntegerField(source="created_plans.count", read_only=True)
    total_planned_count = serializers.SerializerMethodField()
    total_session_units = serializers.SerializerMethodField()

    class Meta:
        model = RehabPlanTemplate
        fields = [
            "id",
            "name",
            "description",
            "suggested_duration_weeks",
            "goals",
            "is_active",
            "status_display",
            "courses",
            "usage_count",
            "total_planned_count",
            "total_session_units",
            "created_at",
            "updated_at",
        ]

    def get_status_display(self, obj: RehabPlanTemplate) -> str:
        """返回模板启用状态中文名。"""
        return "启用" if obj.is_active else "停用"

    def get_total_planned_count(self, obj: RehabPlanTemplate) -> int:
        """计算模板内全部课程的计划次数。"""
        return sum(item.planned_count for item in obj.courses.all())

    def get_total_session_units(self, obj: RehabPlanTemplate) -> float:
        """计算模板的计划总课时。"""
        return float(
            sum(
                (item.session_cost * item.planned_count for item in obj.courses.all()),
                Decimal("0.0"),
            )
        )

    def validate(self, attrs: dict) -> dict:
        """校验启用模板至少包含一门课程，且课程不重复。"""
        courses = attrs.get("courses")
        is_active = attrs.get("is_active", getattr(self.instance, "is_active", True))
        if courses is None and self.instance is not None:
            courses = list(self.instance.courses.all())
        if is_active and not courses:
            raise serializers.ValidationError({"courses": "启用的课程计划模板至少需要一门课程"})
        if courses is not None:
            type_ids = [
                item.course_type_id if isinstance(item, RehabPlanTemplateCourse) else item["course_type"].id
                for item in courses
            ]
            if len(type_ids) != len(set(type_ids)):
                raise serializers.ValidationError({"courses": "同一课程模板不能重复添加"})
        return attrs


class RehabPlanCourseDraftSerializer(serializers.Serializer):
    """创建客户周期时提交的课程快照。"""

    course_type = serializers.PrimaryKeyRelatedField(queryset=CourseType.objects.all())
    package = serializers.PrimaryKeyRelatedField(
        queryset=CoursePackage.objects.all(),
        required=False,
        allow_null=True,
    )
    planned_count = serializers.IntegerField(min_value=1)
    session_cost = serializers.DecimalField(
        max_digits=4,
        decimal_places=1,
        required=False,
        coerce_to_string=False,
        validators=[validate_session_cost],
    )
    duration = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    goals = serializers.CharField(required=False, allow_blank=True, default="")


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
    """客户课程计划输出/输入。"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    stages = RehabStageSerializer(many=True, read_only=True)
    course_count = serializers.IntegerField(source="plan_courses.count", read_only=True)
    source_template_name = serializers.CharField(source="source_template.name", read_only=True, default=None)

    class Meta:
        model = RehabPlan
        fields = [
            "id",
            "customer",
            "customer_name",
            "source_template",
            "source_template_name",
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


class RehabPlanCreateSerializer(RehabPlanSerializer):
    """创建客户课程计划，可携带模板来源和预览调整后的课程快照。"""

    courses = RehabPlanCourseDraftSerializer(many=True, required=False)

    class Meta(RehabPlanSerializer.Meta):
        fields = RehabPlanSerializer.Meta.fields + ["courses"]
