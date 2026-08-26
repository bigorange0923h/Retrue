"""courses：课时序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.courses.models import CoursePackage


class CoursePackageSerializer(serializers.ModelSerializer):
    """课时包输出/输入。"""

    remaining_sessions = serializers.IntegerField(read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

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
            "note",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"total_sessions": {"required": True}}
