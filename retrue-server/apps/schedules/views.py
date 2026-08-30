"""schedules：课程模板与课程排期接口视图。

提供今日课程、课表日历与课程模板管理接口。
数据隔离：所有查询均限定当前康复师本人数据。
"""

from __future__ import annotations

from datetime import date

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.schedules.models import (
    CourseSession,
    CourseType,
    CourseSessionStatus,
    PlanCourseStatus,
    RehabPlanCourse,
)
from apps.schedules.serializers import (
    CourseSessionSerializer,
    CourseTypeSerializer,
)


class CourseCreateSerializer(serializers.ModelSerializer):
    """课程创建/更新输入校验。"""

    class Meta:
        model = CourseSession
        fields = [
            "customer",
            "plan_course",
            "session_topic",
            "session_count",
            "date",
            "start_time",
            "end_time",
            "status",
            "note",
        ]

    def validate(self, attrs: dict) -> dict:
        """校验时间顺序，并禁止绕过正式训练记录直接新建已完成课程。"""
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if bool(start_time) != bool(end_time):
            raise serializers.ValidationError("开始时间和结束时间必须同时填写")
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "结束时间必须晚于开始时间"})
        if self.instance is None and attrs.get("status") == CourseSessionStatus.COMPLETED:
            raise serializers.ValidationError({"status": "已完成状态只能由正式训练记录触发"})
        return attrs


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
            "customer", "plan_course__course_type", "plan_course__rehab_plan"
        ).prefetch_related("training_records")
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
            .select_related("customer", "plan_course__course_type", "plan_course__rehab_plan")
            .prefetch_related("training_records")
            .order_by("date", "start_time", "id")
        )
        return ApiResponse.ok(CourseSessionSerializer(sessions, many=True).data, message="查询课表成功")


class CourseCreateView(APIView):
    """创建课程接口。

    权限：需已登录。
    说明：创建课程条目，customer 必须属于当前康复师；若关联周期课程，
    周期的客户必须与排期客户一致，且周期属于当前康复师。
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

        plan_course = serializer.validated_data.get("plan_course")
        if plan_course is not None:
            check = _validate_session_plan_course(request, plan_course, customer)
            if check is not None:
                return check

        session = CourseSession.objects.create(therapist=request.user, **serializer.validated_data)
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="课程创建成功")


class CourseDetailView(APIView):
    """单节课程管理接口，支持查看与修改课程安排。"""

    permission_classes = [IsAuthenticated]

    def _get_session(self, request, course_id: int):
        """获取当前康复师的课程，避免跨账号访问。"""
        return (
            CourseSession.objects.filter(therapist=request.user)
            .select_related("customer", "plan_course__course_type", "plan_course__rehab_plan")
            .prefetch_related("training_records")
            .filter(id=course_id)
            .first()
        )

    def get(self, request, course_id: int):
        """返回课程详情。"""
        session = self._get_session(request, course_id)
        if session is None:
            return ApiResponse.error("课程不存在或无权访问", 404)
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="查询课程成功")

    def put(self, request, course_id: int):
        """更新课程的客户、时间、状态或备注。

        “已完成”状态只能由已确认训练记录触发；页面不能绕过记录直接完成课程。
        """
        session = self._get_session(request, course_id)
        if session is None:
            return ApiResponse.error("课程不存在或无权访问", 404)
        serializer = CourseCreateSerializer(session, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is not None and customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户排课", 403)
        effective_customer = customer or session.customer
        plan_course = serializer.validated_data.get("plan_course", session.plan_course)
        if plan_course is not None:
            check = _validate_session_plan_course(
                request,
                plan_course,
                effective_customer,
                allow_existing_id=session.plan_course_id,
            )
            if check is not None:
                return check
        requested_status = serializer.validated_data.get("status", session.status)
        has_formal_record = session.training_records.exists()
        if has_formal_record and (
            requested_status != CourseSessionStatus.COMPLETED
            or serializer.validated_data.get("customer", session.customer).id != session.customer_id
            or getattr(
                serializer.validated_data.get("plan_course", session.plan_course), "id", None
            ) != session.plan_course_id
            or serializer.validated_data.get("session_count", session.session_count)
            != session.session_count
        ):
            return ApiResponse.error("课程已有确认训练记录，不能更换客户、周期课程、课时或完成状态", 400)
        if requested_status == CourseSessionStatus.COMPLETED and not has_formal_record:
            return ApiResponse.error("请先填写并确认本次训练记录，再完成课程", 400)
        for field, value in serializer.validated_data.items():
            setattr(session, field, value)
        session.save()
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="课程更新成功")


def _validate_session_plan_course(
    request,
    plan_course: RehabPlanCourse,
    customer,
    allow_existing_id: int | None = None,
):
    """校验周期课程归属、客户一致性与可排课状态。"""
    if plan_course.rehab_plan.therapist_id != request.user.id:
        return ApiResponse.error("无权使用该周期课程", 403)
    if plan_course.rehab_plan.customer_id != customer.id:
        return ApiResponse.error("周期课程的客户与排期客户不一致", 400)
    if plan_course.id != allow_existing_id:
        if plan_course.rehab_plan.status != "active":
            return ApiResponse.error("已结束的康复周期不能继续排课", 400)
        if plan_course.status != PlanCourseStatus.ACTIVE:
            return ApiResponse.error("只能为进行中的周期课程排课", 400)
    return None


class CourseTypeListView(APIView):
    """课程模板管理：列表与创建。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回当前康复师的课程类型列表，支持 keyword 搜索。"""
        keyword = request.query_params.get("keyword", "").strip()
        queryset = CourseType.objects.filter(therapist=request.user)
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)
        queryset = queryset.order_by("-is_active", "name")
        return ApiResponse.ok(CourseTypeSerializer(queryset, many=True).data, message="查询课程类型成功")

    def post(self, request):
        """创建课程类型。"""
        serializer = CourseTypeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course_type = CourseType.objects.create(therapist=request.user, **serializer.validated_data)
        return ApiResponse.ok(CourseTypeSerializer(course_type).data, message="课程类型创建成功")


class CourseTypeDetailView(APIView):
    """课程类型详情：查看、更新、停用。"""

    permission_classes = [IsAuthenticated]

    def _get_type(self, request, type_id: int):
        """获取当前康复师的课程类型。"""
        return CourseType.objects.filter(therapist=request.user, id=type_id).first()

    def get(self, request, type_id: int):
        """返回课程类型详情。"""
        course_type = self._get_type(request, type_id)
        if course_type is None:
            return ApiResponse.error("课程类型不存在或无权访问", 404)
        return ApiResponse.ok(CourseTypeSerializer(course_type).data, message="查询课程类型成功")

    def put(self, request, type_id: int):
        """更新课程模板；停用只影响后续新增，不改变历史周期课程。"""
        course_type = self._get_type(request, type_id)
        if course_type is None:
            return ApiResponse.error("课程类型不存在或无权访问", 404)
        serializer = CourseTypeSerializer(course_type, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(course_type, field, value)
        course_type.save()
        return ApiResponse.ok(CourseTypeSerializer(course_type).data, message="课程类型已更新")
