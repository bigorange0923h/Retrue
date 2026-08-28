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
        fields = ["customer", "course_name", "date", "start_time", "end_time", "status", "note"]


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


class CourseCalendarView(APIView):
    """课表日历接口。

    GET：按日期范围返回当前康复师的课程，供月历或周历展示。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回 start 至 end（均包含）之间的课程。"""
        start_text = request.query_params.get("start", "")
        end_text = request.query_params.get("end", "")
        try:
            start_date = date.fromisoformat(start_text)
            end_date = date.fromisoformat(end_text)
        except ValueError:
            return ApiResponse.error("开始和结束日期格式应为 YYYY-MM-DD", 400)

        if end_date < start_date:
            return ApiResponse.error("结束日期不能早于开始日期", 400)
        if (end_date - start_date).days > 62:
            return ApiResponse.error("单次最多查询 62 天课表", 400)

        sessions = (
            CourseSession.objects.filter(
                therapist=request.user,
                date__range=(start_date, end_date),
            )
            .select_related("customer")
            .order_by("date", "start_time", "id")
        )
        return ApiResponse.ok(CourseSessionSerializer(sessions, many=True).data, message="查询课表成功")


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


class CourseDetailView(APIView):
    """单节课程管理接口，支持查看与修改课程安排。"""

    permission_classes = [IsAuthenticated]

    def _get_session(self, request, course_id: int):
        """获取当前康复师的课程，避免跨账号访问。"""
        return CourseSession.objects.filter(therapist=request.user).select_related("customer").filter(id=course_id).first()

    def get(self, request, course_id: int):
        """返回课程详情。"""
        session = self._get_session(request, course_id)
        if session is None:
            return ApiResponse.error("课程不存在或无权访问", 404)
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="查询课程成功")

    def put(self, request, course_id: int):
        """更新课程的客户、时间、状态或备注。"""
        session = self._get_session(request, course_id)
        if session is None:
            return ApiResponse.error("课程不存在或无权访问", 404)
        serializer = CourseCreateSerializer(session, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is not None and customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户排课", 403)
        for field, value in serializer.validated_data.items():
            setattr(session, field, value)
        session.save()
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="课程更新成功")
