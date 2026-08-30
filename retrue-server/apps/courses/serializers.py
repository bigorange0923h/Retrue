"""courses：课时序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.courses.models import CourseAdjustment, CoursePackage


class CourseAdjustmentSerializer(serializers.ModelSerializer):
    """课时流水输出。"""

    adjustment_type_display = serializers.CharField(
        source="get_adjustment_type_display", read_only=True
    )
    therapist_name = serializers.CharField(source="therapist.username", read_only=True)
    course_session_topic = serializers.CharField(
        source="course_session.session_topic", read_only=True
    )
    delta = serializers.DecimalField(
        max_digits=6, decimal_places=1, coerce_to_string=False, read_only=True
    )

    class Meta:
        model = CourseAdjustment
        fields = [
            "id",
            "adjustment_type",
            "adjustment_type_display",
            "delta",
            "reason",
            "course_session",
            "course_session_topic",
            "therapist_name",
            "created_at",
        ]


class CoursePackageSerializer(serializers.ModelSerializer):
    """课时包输出/输入。"""

    total_sessions = serializers.DecimalField(
        max_digits=8, decimal_places=1, coerce_to_string=False
    )
    used_sessions = serializers.DecimalField(
        max_digits=8, decimal_places=1, read_only=True, coerce_to_string=False
    )
    remaining_sessions = serializers.DecimalField(
        max_digits=8, decimal_places=1, read_only=True, coerce_to_string=False
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    adjustments = CourseAdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = CoursePackage
        fields = [
            "id",
            "customer",
            "customer_name",
            "name",
            "total_sessions",
            "used_sessions",
            "remaining_sessions",
            "adjustments",
            "note",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"total_sessions": {"required": True}}
