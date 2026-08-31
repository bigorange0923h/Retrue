"""rehab：康复计划与阶段接口视图。"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Prefetch
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.customers.models import Customer
from apps.rehab import services
from apps.rehab.models import RehabPlan, RehabStageType
from apps.rehab.serializers import (
    RehabPlanCreateSerializer,
    RehabPlanSerializer,
    RehabPlanTemplateSerializer,
    RehabStageSerializer,
)
from apps.schedules.models import CourseSession, RehabPlanCourse
from apps.schedules.serializers import RehabPlanCourseSerializer
from apps.schedules.services import (
    adjust_plan_course_count,
    ensure_plan_course_status_change_allowed,
)


class RehabPlanListView(APIView):
    """康复计划列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询某客户康复计划。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        plans = services.list_plans(request.user, int(customer_id))
        return ApiResponse.ok(RehabPlanSerializer(plans, many=True).data, message="查询康复计划成功")

    def post(self, request):
        """创建客户课程计划，可从计划模板复制并提交个性化课程快照。"""
        serializer = RehabPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = _get_own_customer(request, serializer.validated_data.get("customer"))
        if isinstance(customer, Response):
            return customer
        try:
            plan = services.create_plan(request.user, serializer.validated_data)
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(RehabPlanSerializer(plan).data, message="康复计划创建成功")


class RehabPlanDetailView(APIView):
    """客户课程计划详情与更新接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, plan_id: int):
        """返回一条客户课程计划。"""
        plan = services.get_plan(request.user, plan_id)
        if plan is None:
            return ApiResponse.error("课程计划不存在或无权访问", 404)
        return ApiResponse.ok(RehabPlanSerializer(plan).data, message="查询课程计划成功")

    def put(self, request, plan_id: int):
        """更新课程计划的日期、目标或状态。"""
        plan = services.get_plan(request.user, plan_id)
        if plan is None:
            return ApiResponse.error("课程计划不存在或无权访问", 404)
        serializer = RehabPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("customer", None)
        data.pop("source_template", None)
        try:
            updated = services.update_plan(request.user, plan, data)
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(RehabPlanSerializer(updated).data, message="课程计划已更新")


class RehabPlanTemplateListView(APIView):
    """当前康复师的课程计划模板列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """按关键词和启用状态查询课程计划模板。"""
        templates = services.list_plan_templates(
            request.user,
            keyword=request.query_params.get("keyword", "").strip(),
            active_only=request.query_params.get("active_only") == "1",
        )
        return ApiResponse.ok(
            RehabPlanTemplateSerializer(templates, many=True).data,
            message="查询课程计划模板成功",
        )

    def post(self, request):
        """创建包含多种课程及默认次数的课程计划模板。"""
        serializer = RehabPlanTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            template = services.create_plan_template(request.user, dict(serializer.validated_data))
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(
            RehabPlanTemplateSerializer(template).data,
            message="课程计划模板创建成功",
        )


class RehabPlanTemplateDetailView(APIView):
    """课程计划模板详情与更新接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, template_id: int):
        """返回一条属于当前康复师的课程计划模板。"""
        template = services.get_plan_template(request.user, template_id)
        if template is None:
            return ApiResponse.error("课程计划模板不存在或无权访问", 404)
        return ApiResponse.ok(
            RehabPlanTemplateSerializer(template).data,
            message="查询课程计划模板成功",
        )

    def put(self, request, template_id: int):
        """更新课程计划模板；既有客户计划不随模板变化。"""
        template = services.get_plan_template(request.user, template_id)
        if template is None:
            return ApiResponse.error("课程计划模板不存在或无权访问", 404)
        serializer = RehabPlanTemplateSerializer(
            template,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.update_plan_template(
                request.user,
                template,
                dict(serializer.validated_data),
            )
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(
            RehabPlanTemplateSerializer(updated).data,
            message="课程计划模板已更新",
        )


class RehabPlanCourseListView(APIView):
    """客户课程计划内课程的列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """按计划或客户查询计划内课程。"""
        plan_id = request.query_params.get("plan_id", "")
        customer_id = request.query_params.get("customer_id", "")
        status = request.query_params.get("status", "")
        if not plan_id and not customer_id:
            return ApiResponse.error("缺少 plan_id 或 customer_id 参数", 400)
        queryset = RehabPlanCourse.objects.filter(
            rehab_plan__therapist=request.user
        ).select_related(
            "rehab_plan__customer", "course_type", "package"
        ).prefetch_related(
            "adjustments__therapist",
            Prefetch(
                "sessions",
                queryset=CourseSession.objects.select_related(
                    "customer", "plan_course__course_type", "plan_course__rehab_plan"
                ).prefetch_related("training_records"),
                to_attr="_integration_sessions",
            ),
        )
        if plan_id:
            queryset = queryset.filter(rehab_plan_id=plan_id)
        if customer_id:
            queryset = queryset.filter(rehab_plan__customer_id=customer_id)
        if status:
            queryset = queryset.filter(status=status)
        return ApiResponse.ok(
            RehabPlanCourseSerializer(queryset, many=True).data,
            message="查询计划内课程成功",
        )

    def post(self, request):
        """在一个进行中的客户课程计划内新增课程。"""
        serializer = RehabPlanCourseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        plan = data["rehab_plan"]
        course_type = data["course_type"]
        package = data.get("package")
        if plan.therapist_id != request.user.id:
            return ApiResponse.error("无权操作该课程计划", 403)
        if plan.status != "active":
            return ApiResponse.error("只能为进行中的课程计划添加课程", 400)
        if course_type.therapist_id != request.user.id:
            return ApiResponse.error("无权使用该课程模板", 403)
        if not course_type.is_active:
            return ApiResponse.error("该课程模板已停用", 400)
        if data.get("status") == "completed":
            return ApiResponse.error("新建计划内课程不能直接设为已完成", 400)
        if package is not None and (
            package.therapist_id != request.user.id or package.customer_id != plan.customer_id
        ):
            return ApiResponse.error("课时包与课程计划客户不一致", 400)
        data.setdefault("session_cost", course_type.default_session_cost)
        data.setdefault("duration", course_type.default_duration)
        data.setdefault("goals", course_type.default_goals)
        plan_course = RehabPlanCourse.objects.create(**data)
        return ApiResponse.ok(
            RehabPlanCourseSerializer(plan_course).data,
            message="计划内课程创建成功",
        )


class RehabPlanCourseDetailView(APIView):
    """单个计划内课程的查看与更新接口。"""

    permission_classes = [IsAuthenticated]

    def _get_course(self, request, course_id: int):
        """获取属于当前康复师的计划内课程。"""
        return (
            RehabPlanCourse.objects.filter(
                rehab_plan__therapist=request.user, id=course_id
            )
            .select_related("rehab_plan__customer", "course_type", "package")
            .prefetch_related(
                "adjustments__therapist",
                Prefetch(
                    "sessions",
                    queryset=CourseSession.objects.select_related(
                        "customer", "plan_course__course_type", "plan_course__rehab_plan"
                    ).prefetch_related("training_records"),
                    to_attr="_integration_sessions",
                ),
            )
            .first()
        )

    def get(self, request, course_id: int):
        """返回计划内课程详情。"""
        plan_course = self._get_course(request, course_id)
        if plan_course is None:
            return ApiResponse.error("计划内课程不存在或无权访问", 404)
        return ApiResponse.ok(RehabPlanCourseSerializer(plan_course).data, message="查询计划内课程成功")

    def put(self, request, course_id: int):
        """更新课程目标、时长、课时消耗、课时包或状态。"""
        plan_course = self._get_course(request, course_id)
        if plan_course is None:
            return ApiResponse.error("计划内课程不存在或无权访问", 404)
        if plan_course.rehab_plan.status != "active":
            return ApiResponse.error("已结束的课程计划不能修改课程", 400)
        serializer = RehabPlanCourseSerializer(plan_course, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.get("planned_count", plan_course.planned_count) != plan_course.planned_count:
            return ApiResponse.error("请使用“调整次数”功能增减计划次数并填写原因", 400)
        changes_identity = (
            data.get("rehab_plan", plan_course.rehab_plan).id != plan_course.rehab_plan_id
            or data.get("course_type", plan_course.course_type).id != plan_course.course_type_id
        )
        if changes_identity:
            return ApiResponse.error("所属计划和课程模板创建后不能更换；请新增计划内课程", 400)
        effective_plan = data.get("rehab_plan", plan_course.rehab_plan)
        package = data.get("package", plan_course.package)
        if effective_plan.therapist_id != request.user.id:
            return ApiResponse.error("无权操作该课程计划", 403)
        if package is not None and (
            package.therapist_id != request.user.id
            or package.customer_id != effective_plan.customer_id
        ):
            return ApiResponse.error("课时包与课程计划客户不一致", 400)
        package_id = getattr(package, "id", None)
        if (
            plan_course.sessions.filter(session_consumed=True).exists()
            and package_id != plan_course.package_id
        ):
            return ApiResponse.error("已有扣课记录后不能更换课时包", 400)
        if data.get("status") == "completed" and plan_course.status != "completed":
            completed_count = plan_course.sessions.filter(
                status="completed", training_records__isnull=False
            ).distinct().count()
            if completed_count < plan_course.planned_count:
                return ApiResponse.error("计划次数尚未完成；如需提前结束，请先调整计划次数", 400)
        try:
            with transaction.atomic():
                locked = (
                    RehabPlanCourse.objects.select_for_update()
                    # package 可空，不能随 select_for_update 做外连接（PostgreSQL 会拒绝）。
                    .select_related("rehab_plan__customer", "course_type")
                    .get(id=plan_course.id)
                )
                requested_status = data.get("status", locked.status)
                if requested_status != locked.status:
                    ensure_plan_course_status_change_allowed(locked, requested_status)
                for field, value in data.items():
                    setattr(locked, field, value)
                locked.save()
                plan_course = locked
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(RehabPlanCourseSerializer(plan_course).data, message="计划内课程已更新")


class PlanCourseAdjustmentInputSerializer(serializers.Serializer):
    """计划内课程次数调整输入。"""

    delta_count = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    assessment = serializers.IntegerField(required=False, allow_null=True)


class RehabPlanCourseAdjustView(APIView):
    """调整计划内课程的计划次数。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, course_id: int):
        """增减计划次数并保存调整原因。"""
        plan_course = RehabPlanCourse.objects.filter(
            rehab_plan__therapist=request.user, id=course_id
        ).select_related("rehab_plan__customer").first()
        if plan_course is None:
            return ApiResponse.error("计划内课程不存在或无权访问", 404)
        if plan_course.rehab_plan.status != "active":
            return ApiResponse.error("已结束的课程计划不能调整课程次数", 400)
        if plan_course.status == "cancelled":
            return ApiResponse.error("已取消的计划内课程不能调整次数；请先恢复课程状态", 400)
        serializer = PlanCourseAdjustmentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assessment = None
        assessment_id = serializer.validated_data.get("assessment")
        if assessment_id:
            from apps.assessments.models import Assessment

            assessment = Assessment.objects.filter(
                id=assessment_id,
                therapist=request.user,
                customer=plan_course.rehab_plan.customer,
                status="completed",
            ).first()
            if assessment is None:
                return ApiResponse.error("关联复评不存在、尚未完成或不属于该客户", 400)
        try:
            updated = adjust_plan_course_count(
                request.user,
                plan_course,
                serializer.validated_data["delta_count"],
                serializer.validated_data["reason"],
                assessment,
            )
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(RehabPlanCourseSerializer(updated).data, message="课程次数调整成功")


class RehabStageInputSerializer(serializers.Serializer):
    """康复阶段设置输入，周期未传时按客户解析当前进行中周期。"""

    customer = serializers.IntegerField()
    plan = serializers.IntegerField(required=False, allow_null=True)
    stage_type = serializers.ChoiceField(choices=RehabStageType.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        """校验阶段日期顺序。"""
        if attrs.get("end_date") and attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "结束日期不能早于进入日期"})
        return attrs


class RehabStageView(APIView):
    """康复阶段设置与当前阶段查询接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询客户当前阶段。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        stage = services.get_current_stage(request.user, int(customer_id))
        return ApiResponse.ok(RehabStageSerializer(stage).data if stage else None, message="查询当前阶段成功")

    def post(self, request):
        """为客户设置康复阶段（手动调整）。"""
        serializer = RehabStageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = Customer.objects.filter(
            id=serializer.validated_data["customer"], therapist=request.user
        ).first()
        if customer is None:
            return ApiResponse.error("客户不存在或无权访问", 404)
        plan_id = serializer.validated_data.get("plan")
        plans = RehabPlan.objects.filter(
            therapist=request.user,
            customer=customer,
            status="active",
        )
        plan = plans.filter(id=plan_id).first() if plan_id else plans.first()
        if plan is None:
            return ApiResponse.error("请先为客户创建进行中的课程计划", 400)
        data = dict(serializer.validated_data)
        data.pop("customer", None)
        data["plan"] = plan
        try:
            stage = services.set_stage(request.user, data)
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(RehabStageSerializer(stage).data, message="康复阶段已更新")


def _get_own_customer(request, customer):
    """校验客户归属。"""
    if customer is None:
        return ApiResponse.error("缺少客户信息", 400)
    if customer.therapist_id != request.user.id:
        return ApiResponse.error("无权为该客户操作", 403)
    return customer
