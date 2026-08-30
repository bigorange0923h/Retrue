"""schedules：课程模板、周期课程与排期序列化器。"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.schedules.models import (
    CourseSession,
    CourseType,
    PlanCourseAdjustment,
    RehabPlanCourse,
)


class CourseSessionSerializer(serializers.ModelSerializer):
    """课程条目输出。

    字段：
        id: 课程 ID。
        customer: 客户 ID。
        customer_name: 客户姓名。
        customer_phone_masked: 客户脱敏手机号。
        plan_course: 周期课程 ID。
        plan_course_name: 周期课程名称。
        session_topic: 本节训练主题。
        session_count: 课时单位（半课 0.5 / 全课 1.0）。
        date: 上课日期。
        start_time: 开始时间。
        end_time: 结束时间。
        status: 状态。
        status_display: 状态中文名。
        note: 备注。
    """

    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone_masked = serializers.CharField(source="customer.phone_masked", read_only=True)
    plan_course_name = serializers.CharField(
        source="plan_course.course_type.name", read_only=True, default=None
    )
    rehab_plan_name = serializers.CharField(
        source="plan_course.rehab_plan.name", read_only=True, default=None
    )
    training_record_id = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    session_count = serializers.DecimalField(
        max_digits=4, decimal_places=1, coerce_to_string=False
    )

    class Meta:
        model = CourseSession
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone_masked",
            "plan_course",
            "plan_course_name",
            "rehab_plan_name",
            "session_topic",
            "session_count",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_display",
            "session_consumed",
            "training_record_id",
            "note",
        ]

    def get_training_record_id(self, obj: CourseSession) -> int | None:
        """返回该排期已确认训练记录的 ID。"""
        record = obj.training_records.order_by("id").first()
        return record.id if record else None


class CourseTypeSerializer(serializers.ModelSerializer):
    """课程类型输出/输入。

    课程类型由康复师维护，可复用、可停用。已被周期课程引用的类型不得物理删除。
    """

    status_display = serializers.SerializerMethodField()
    course_count = serializers.SerializerMethodField()
    default_session_cost = serializers.DecimalField(
        max_digits=4, decimal_places=1, required=False, coerce_to_string=False
    )

    class Meta:
        model = CourseType
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "default_duration",
            "default_session_cost",
            "default_goals",
            "status_display",
            "course_count",
            "created_at",
        ]

    def get_status_display(self, obj: CourseType) -> str:
        """返回启用状态中文名。"""
        return "启用" if obj.is_active else "停用"

    def get_course_count(self, obj: CourseType) -> int:
        """返回引用该类型的周期课程数量。"""
        return obj.plan_courses.count()


class PlanCourseAdjustmentSerializer(serializers.ModelSerializer):
    """周期课程次数调整记录输出。"""

    therapist_name = serializers.CharField(source="therapist.username", read_only=True)

    class Meta:
        model = PlanCourseAdjustment
        fields = [
            "id",
            "delta_count",
            "before_count",
            "after_count",
            "reason",
            "assessment",
            "therapist_name",
            "created_at",
        ]


class RehabPlanCourseSerializer(serializers.ModelSerializer):
    """康复周期内课程的输入与输出。"""

    rehab_plan_name = serializers.CharField(source="rehab_plan.name", read_only=True)
    rehab_plan_status = serializers.CharField(source="rehab_plan.status", read_only=True)
    customer = serializers.IntegerField(source="rehab_plan.customer_id", read_only=True)
    customer_name = serializers.CharField(source="rehab_plan.customer.name", read_only=True)
    course_type_name = serializers.CharField(source="course_type.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    completed_count = serializers.SerializerMethodField()
    remaining_count = serializers.SerializerMethodField()
    adjustments = PlanCourseAdjustmentSerializer(many=True, read_only=True)
    session_cost = serializers.DecimalField(
        max_digits=4, decimal_places=1, required=False, coerce_to_string=False
    )

    class Meta:
        model = RehabPlanCourse
        fields = [
            "id",
            "rehab_plan",
            "rehab_plan_name",
            "rehab_plan_status",
            "customer",
            "customer_name",
            "course_type",
            "course_type_name",
            "package",
            "package_name",
            "status",
            "status_display",
            "goals",
            "planned_count",
            "completed_count",
            "remaining_count",
            "session_cost",
            "duration",
            "adjustments",
            "created_at",
        ]

    def get_completed_count(self, obj: RehabPlanCourse) -> int:
        """统计已完成且已有确认记录的实际课程次数。"""
        return obj.sessions.filter(
            status="completed", training_records__isnull=False
        ).distinct().count()

    def get_remaining_count(self, obj: RehabPlanCourse) -> int:
        """返回当前计划剩余次数。"""
        return max(obj.planned_count - self.get_completed_count(obj), 0)

    def validate_session_cost(self, value: Decimal) -> Decimal:
        """校验课时消耗量为 0.5 的倍数且大于 0。"""
        if value <= 0:
            raise serializers.ValidationError("课时消耗量必须大于 0")
        if value * 2 != int(value * 2):
            raise serializers.ValidationError("课时消耗量须为 0.5 的倍数")
        return value

    def validate_planned_count(self, value: int) -> int:
        """计划次数允许调整为零，但不能为负数。"""
        if value < 0:
            raise serializers.ValidationError("计划次数不能小于 0")
        if self.instance is None and value == 0:
            raise serializers.ValidationError("新建周期课程的计划次数必须大于 0")
        return value
