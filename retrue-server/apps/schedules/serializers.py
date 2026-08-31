"""schedules：课程模板、计划内课程与排期序列化器。"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from django.utils import timezone

from rest_framework import serializers

from apps.customers.models import Customer
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
        plan_course: 计划内课程 ID。
        plan_course_name: 计划内课程名称。
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
    arrangement_type_display = serializers.CharField(
        source="get_arrangement_type_display", read_only=True
    )
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
            "arrangement_type",
            "arrangement_type_display",
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

    课程类型由康复师维护，可复用、可停用。已被计划内课程引用的类型不得物理删除。
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
        """返回引用该类型的计划内课程数量。"""
        return obj.plan_courses.count()


class PlanCourseAdjustmentSerializer(serializers.ModelSerializer):
    """计划内课程次数调整记录输出。"""

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
    """客户课程计划内课程的输入与输出。"""

    rehab_plan_name = serializers.CharField(source="rehab_plan.name", read_only=True)
    rehab_plan_status = serializers.CharField(source="rehab_plan.status", read_only=True)
    customer = serializers.IntegerField(source="rehab_plan.customer_id", read_only=True)
    customer_name = serializers.CharField(source="rehab_plan.customer.name", read_only=True)
    course_type_name = serializers.CharField(source="course_type.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    completed_count = serializers.SerializerMethodField()
    scheduled_count = serializers.SerializerMethodField()
    unscheduled_count = serializers.SerializerMethodField()
    overdue_count = serializers.SerializerMethodField()
    next_session = serializers.SerializerMethodField()
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
            "scheduled_count",
            "unscheduled_count",
            "overdue_count",
            "next_session",
            "remaining_count",
            "session_cost",
            "duration",
            "adjustments",
            "created_at",
        ]

    def _sessions(self, obj: RehabPlanCourse) -> list[CourseSession]:
        """读取带预取的排课，未预取时兼容单条详情查询。"""
        prefetched = getattr(obj, "_integration_sessions", None)
        if prefetched is not None:
            return list(prefetched)
        return list(obj.sessions.all().prefetch_related("training_records"))

    def _counts(self, obj: RehabPlanCourse) -> tuple[int, int, int]:
        """返回（已上、已安排、逾期待上）三项次数。"""
        completed = 0
        scheduled = 0
        overdue = 0
        today = timezone.localdate()
        for session in self._sessions(obj):
            prefetched_records = getattr(session, "_prefetched_objects_cache", {}).get(
                "training_records"
            )
            if prefetched_records is not None:
                has_record = bool(prefetched_records)
            else:
                has_record = session.training_records.exists()
            if session.status == "completed" and has_record:
                completed += 1
            elif session.status == "scheduled":
                scheduled += 1
                if session.date < today:
                    overdue += 1
        return completed, scheduled, overdue

    def get_completed_count(self, obj: RehabPlanCourse) -> int:
        """统计已完成且已有确认记录的实际课程次数。"""
        return self._counts(obj)[0]

    def get_scheduled_count(self, obj: RehabPlanCourse) -> int:
        """统计有效的待上课排课；逾期但未处理仍算已安排。"""
        return self._counts(obj)[1]

    def get_unscheduled_count(self, obj: RehabPlanCourse) -> int:
        """返回尚未安排的次数，不会因逾期排课而重复安排。"""
        completed, scheduled, _ = self._counts(obj)
        return max(obj.planned_count - completed - scheduled, 0)

    def get_overdue_count(self, obj: RehabPlanCourse) -> int:
        """统计日期已过但仍处于待上课状态的排课。"""
        return self._counts(obj)[2]

    def get_next_session(self, obj: RehabPlanCourse):
        """返回最近一节尚未取消/请假的待上课课程。"""
        today = timezone.localdate()
        sessions = [
            session
            for session in self._sessions(obj)
            if session.status == "scheduled" and session.date >= today
        ]
        sessions.sort(key=lambda item: (item.date, item.start_time or time.max, item.id))
        if not sessions:
            return None
        return CourseSessionSerializer(sessions[0], context=self.context).data

    def get_remaining_count(self, obj: RehabPlanCourse) -> int:
        """兼容旧客户端的字段，含义与待安排次数一致。"""
        return self.get_unscheduled_count(obj)

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
            raise serializers.ValidationError("新建计划内课程的计划次数必须大于 0")
        return value


class BatchScheduleInputSerializer(serializers.Serializer):
    """批量安排课程向导的输入。

    ``weekdays`` 对外使用日历常见的约定：0 表示周日，1 至 6 表示周一至
    周六。``weekly_count`` 是前端业务文案，服务层同时兼容 ``frequency``。
    """

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
    )
    plan_course = serializers.PrimaryKeyRelatedField(
        queryset=RehabPlanCourse.objects.all(), required=False
    )
    start_date = serializers.DateField()
    frequency = serializers.IntegerField(min_value=1, max_value=7, required=False)
    weekly_count = serializers.IntegerField(min_value=1, max_value=7, required=False, write_only=True)
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=7),
        required=False,
        allow_empty=False,
    )
    start_time = serializers.TimeField(required=True)
    end_time = serializers.TimeField(required=False, allow_null=True)
    session_topic = serializers.CharField(required=False, allow_blank=True)
    session_count = serializers.DecimalField(
        max_digits=4, decimal_places=1, required=False, min_value=Decimal("0.1")
    )

    def validate(self, attrs: dict) -> dict:
        """校验每周次数与所选星期一致。"""
        weekly_count = attrs.pop("weekly_count", None)
        frequency = attrs.get("frequency", weekly_count)
        weekdays = attrs.get("weekdays")
        if frequency is None:
            frequency = len(weekdays) if weekdays else 1
        if weekdays and len(set(weekdays)) != len(weekdays):
            raise serializers.ValidationError({"weekdays": "上课星期不能重复"})
        if weekdays and len(weekdays) != frequency:
            raise serializers.ValidationError("每周上课次数应与选择的星期数量一致")
        if not weekdays and frequency > 1:
            raise serializers.ValidationError("每周上课多次时，请选择对应的上课星期")
        attrs["frequency"] = frequency
        return attrs
