"""schedules：课程序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.schedules.models import CourseSession


class CourseSessionSerializer(serializers.ModelSerializer):
    """课程条目输出。

    字段：
        id: 课程 ID。
        customer: 客户 ID。
        customer_name: 客户姓名。
        customer_phone_masked: 客户脱敏手机号。
        date: 上课日期。
        start_time: 开始时间。
        end_time: 结束时间。
        status: 状态。
        status_display: 状态中文名。
        note: 备注。
    """

    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone_masked = serializers.CharField(source="customer.phone_masked", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CourseSession
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone_masked",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_display",
            "note",
        ]
