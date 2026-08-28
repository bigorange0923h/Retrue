"""schedules：课程/疗程序列化器。"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.schedules.models import CourseSession, CourseType, CustomerCourse


class CourseSessionSerializer(serializers.ModelSerializer):
    """课程条目输出。

    字段：
        id: 课程 ID。
        customer: 客户 ID。
        customer_name: 客户姓名。
        customer_phone_masked: 客户脱敏手机号。
        customer_course: 客户疗程 ID。
        customer_course_name: 客户疗程名称。
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
    customer_course_name = serializers.CharField(
        source="customer_course.course_type.name", read_only=True, default=None
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CourseSession
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone_masked",
            "customer_course",
            "customer_course_name",
            "session_topic",
            "session_count",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_display",
            "note",
        ]


class CourseTypeSerializer(serializers.ModelSerializer):
    """课程类型输出/输入。

    课程类型由康复师维护，可复用、可停用。已被客户疗程引用的类型不得物理删除，只能停用。
    """

    status_display = serializers.SerializerMethodField()
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = CourseType
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "default_duration",
            "default_session_cost",
            "default_stage",
            "default_goals",
            "default_notes",
            "status_display",
            "course_count",
            "created_at",
        ]

    def get_status_display(self, obj: CourseType) -> str:
        """返回启用状态中文名。"""
        return "启用" if obj.is_active else "停用"

    def get_course_count(self, obj: CourseType) -> int:
        """返回引用该类型的客户疗程数量。"""
        return obj.customer_courses.count()


class CustomerCourseSerializer(serializers.ModelSerializer):
    """客户疗程输出/输入。

    疗程将课程类型分配给客户，含个体化快照与状态机。课程类型后续被编辑时不影响已开设疗程快照。
    """

    customer_name = serializers.CharField(source="customer.name", read_only=True)
    course_type_name = serializers.CharField(source="course_type.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CustomerCourse
        fields = [
            "id",
            "customer",
            "customer_name",
            "course_type",
            "course_type_name",
            "plan",
            "stage_type",
            "package",
            "package_name",
            "start_date",
            "end_date",
            "status",
            "status_display",
            "individual_goals",
            "planned_sessions",
            "session_cost",
            "duration",
            "created_at",
        ]

    def validate_session_cost(self, value: Decimal) -> Decimal:
        """校验课时消耗量为 0.5 的倍数且大于 0。"""
        if value <= 0:
            raise serializers.ValidationError("课时消耗量必须大于 0")
        if value * 2 != int(value * 2):
            raise serializers.ValidationError("课时消耗量须为 0.5 的倍数")
        return value
