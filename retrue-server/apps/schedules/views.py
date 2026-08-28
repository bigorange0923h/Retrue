"""schedules：课程/日程/疗程接口视图。

提供今日课程、课表日历、课程类型与客户疗程的管理接口。
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
    CustomerCourse,
    CustomerCourseStatus,
)
from apps.schedules.serializers import (
    CourseSessionSerializer,
    CourseTypeSerializer,
    CustomerCourseSerializer,
)


class CourseCreateSerializer(serializers.ModelSerializer):
    """课程创建/更新输入校验。"""

    class Meta:
        model = CourseSession
        fields = [
            "customer",
            "customer_course",
            "session_topic",
            "session_count",
            "date",
            "start_time",
            "end_time",
            "status",
            "note",
        ]


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
            "customer", "customer_course__course_type"
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
            .select_related("customer", "customer_course__course_type")
            .order_by("date", "start_time", "id")
        )
        return ApiResponse.ok(CourseSessionSerializer(sessions, many=True).data, message="查询课表成功")


class CourseCreateView(APIView):
    """创建课程接口。

    权限：需已登录。
    说明：创建课程条目，customer 必须属于当前康复师；若关联客户疗程，
    疗程的客户必须与排期客户一致，且疗程属于当前康复师。
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

        customer_course = serializer.validated_data.get("customer_course")
        if customer_course is not None:
            check = _validate_session_course(request, customer_course, customer)
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
            .select_related("customer", "customer_course__course_type")
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

        当课程状态被改为"已完成"且关联的疗程有课时包时，自动扣减课时。
        """
        session = self._get_session(request, course_id)
        if session is None:
            return ApiResponse.error("课程不存在或无权访问", 404)
        serializer = CourseCreateSerializer(session, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is not None and customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户排课", 403)
        customer_course = serializer.validated_data.get("customer_course")
        if customer_course is not None:
            check = _validate_session_course(request, customer_course, customer or session.customer)
            if check is not None:
                return check

        # 记录旧状态，用于判断是否触发自动扣课时
        old_status = session.status
        for field, value in serializer.validated_data.items():
            setattr(session, field, value)

        becoming_completed = (
            session.status == CourseSessionStatus.COMPLETED
            and old_status != CourseSessionStatus.COMPLETED
        )
        if becoming_completed:
            session = _apply_session_consumption(request.user, session)

        session.save()
        return ApiResponse.ok(CourseSessionSerializer(session).data, message="课程更新成功")


def _validate_session_course(request, customer_course: CustomerCourse, customer):
    """校验客户疗程归属与客户一致性。返回错误响应或 None。"""
    if customer_course.therapist_id != request.user.id:
        return ApiResponse.error("无权使用该客户疗程", 403)
    if customer_course.customer_id != customer.id:
        return ApiResponse.error("客户疗程的客户与排期客户不一致", 400)
    if customer_course.status != CustomerCourseStatus.ACTIVE:
        return ApiResponse.error("只能为进行中的客户疗程排课", 400)
    return None


def _apply_session_consumption(therapist, session: CourseSession) -> CourseSession:
    """课程完成时自动扣减课时（幂等）。

    仅当：课程关联了客户疗程、疗程关联课时包、且该课程尚未扣减过。
    扣减成功后将 session_consumed 标记为 True，避免重复扣减。
    """
    if session.session_consumed:
        return session
    course = session.customer_course
    if course is None or course.package_id is None:
        return session
    from apps.courses.services import consume_for_session

    try:
        consume_for_session(therapist, session)
        session.session_consumed = True
    except ValueError:
        # 课时不足等场景：不阻断课程完成，仅不标记已扣，交由人工处理
        pass
    return session


class CourseTypeListView(APIView):
    """课程类型管理：列表与创建。"""

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
        """更新课程类型；已被疗程引用的类型可编辑，但不能取消启用。"""
        course_type = self._get_type(request, type_id)
        if course_type is None:
            return ApiResponse.error("课程类型不存在或无权访问", 404)
        serializer = CourseTypeSerializer(course_type, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # 已被客户疗程引用且要停用：拒绝
        if course_type.customer_courses.exists() and serializer.validated_data.get("is_active") is False:
            return ApiResponse.error("已被客户疗程引用的课程类型不能停用", 400)
        for field, value in serializer.validated_data.items():
            setattr(course_type, field, value)
        course_type.save()
        return ApiResponse.ok(CourseTypeSerializer(course_type).data, message="课程类型已更新")


class CustomerCourseListView(APIView):
    """客户疗程管理：列表与创建。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回当前康复师的客户疗程列表，可按客户或状态筛选。"""
        customer_id = request.query_params.get("customer", "")
        status = request.query_params.get("status", "")
        queryset = CustomerCourse.objects.filter(therapist=request.user).select_related(
            "customer", "course_type", "package"
        )
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        if status:
            queryset = queryset.filter(status=status)
        queryset = queryset.order_by("-created_at")
        return ApiResponse.ok(CustomerCourseSerializer(queryset, many=True).data, message="查询客户疗程成功")

    def post(self, request):
        """创建客户疗程。"""
        serializer = CustomerCourseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data["customer"]
        if customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户创建疗程", 403)
        course_type = serializer.validated_data["course_type"]
        if course_type.therapist_id != request.user.id:
            return ApiResponse.error("无权使用该课程类型", 403)
        # 快照：创建时复制课程类型的默认时长/消耗量，避免后续编辑类型漂移
        data = dict(serializer.validated_data)
        data.setdefault("session_cost", course_type.default_session_cost)
        data.setdefault("duration", course_type.default_duration)
        customer_course = CustomerCourse.objects.create(therapist=request.user, **data)
        return ApiResponse.ok(CustomerCourseSerializer(customer_course).data, message="客户疗程创建成功")


class CustomerCourseDetailView(APIView):
    """客户疗程详情：查看、更新、状态流转。"""

    permission_classes = [IsAuthenticated]

    def _get_course(self, request, course_id: int):
        """获取当前康复师的客户疗程。"""
        return (
            CustomerCourse.objects.filter(therapist=request.user)
            .select_related("customer", "course_type", "package")
            .filter(id=course_id)
            .first()
        )

    def get(self, request, course_id: int):
        """返回客户疗程详情。"""
        customer_course = self._get_course(request, course_id)
        if customer_course is None:
            return ApiResponse.error("客户疗程不存在或无权访问", 404)
        return ApiResponse.ok(CustomerCourseSerializer(customer_course).data, message="查询客户疗程成功")

    def put(self, request, course_id: int):
        """更新客户疗程信息与状态。"""
        customer_course = self._get_course(request, course_id)
        if customer_course is None:
            return ApiResponse.error("客户疗程不存在或无权访问", 404)
        serializer = CustomerCourseSerializer(customer_course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(customer_course, field, value)
        customer_course.save()
        return ApiResponse.ok(CustomerCourseSerializer(customer_course).data, message="客户疗程已更新")
