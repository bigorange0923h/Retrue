"""schedules：课程/今日日程接口视图。

提供今日课程查询与课程创建接口，用于今日工作台展示。
"""

from __future__ import annotations

from datetime import date

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.schedules.models import CourseSession
from apps.schedules.serializers import CourseSessionSerializer


class CourseCreateSerializer(serializers.ModelSerializer):
    """课程创建输入校验。"""

    class Meta:
        model = CourseSession
        fields = ["customer", "date", "start_time", "end_time", "status", "note"]


class TodayCoursesView(APIView):
    """今日课程接口。

    权限：需已登录。
    说明：返回当前康复师指定日期的课程列表，用于今日工作台展示今日客户。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回指定日期的课程列表。"""
        day = request.query_params.get("date", "")
        try:
            target = date.fromisoformat(day) if day else date.today()
        except ValueError:
            return ApiResponse.error("日期格式错误，应为 YYYY-MM-DD", 400)

        sessions = CourseSession.objects.filter(therapist=request.user, date=target).select_related(
            "customer"
        )
        return ApiResponse.ok(CourseSessionSerializer(sessions, many=True).data, message="查询今日课程成功")


class CourseCreateView(APIView):
    """创建课程接口。

    权限：需已登录。
    说明：创建课程条目，customer 必须属于当前康复师。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """创建课程。"""
        serializer = CourseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = serializer.validated_data["customer"]
        # 数据隔离：只能为本人客户排课
        if customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户排课", 403)

        session = CourseSession.objects.create(therapist=request.user, **serializer.validated_data)
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="课程创建成功")
