"""training：家庭训练计划接口视图。"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.training.models import HomeTrainingPlan
from apps.training.serializers import HomeTrainingPlanCreateSerializer, HomeTrainingPlanSerializer
from apps.training.views import _parse_customer_id


class HomeTrainingPlanListView(APIView):
    """家庭训练计划列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询某客户家庭训练计划。"""
        customer_id = _parse_customer_id(request)
        if isinstance(customer_id, Response):
            return customer_id
        plans = HomeTrainingPlan.objects.filter(therapist=request.user, customer_id=customer_id).prefetch_related(
            "exercises"
        )
        return ApiResponse.ok(HomeTrainingPlanSerializer(plans, many=True).data, message="查询家庭训练成功")

    def post(self, request):
        """创建家庭训练计划。"""
        serializer = HomeTrainingPlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is None or customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户创建家庭训练", 403)
        serializer.validated_data["therapist"] = request.user
        plan = serializer.save()
        return ApiResponse.ok(HomeTrainingPlanSerializer(plan).data, message="家庭训练创建成功")


class HomeTrainingPlanDetailView(APIView):
    """家庭训练计划详情与更新接口。"""

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, plan_id: int):
        """获取属于当前康复师的计划。"""
        plan = HomeTrainingPlan.objects.filter(therapist=request.user, id=plan_id).prefetch_related("exercises").first()
        if plan is None:
            return ApiResponse.error("家庭训练计划不存在或无权访问", 404)
        return plan

    def get(self, request, plan_id: int):
        """返回计划详情。"""
        plan = self._get_or_404(request, plan_id)
        if isinstance(plan, Response):
            return plan
        return ApiResponse.ok(HomeTrainingPlanSerializer(plan).data, message="获取家庭训练成功")

    def put(self, request, plan_id: int):
        """更新计划。

        家庭训练创建后不允许更换关联客户：提交与原来相同的客户值保持兼容，
        提交不同客户一律拒绝，避免计划被改绑到其他康复师客户。
        """
        plan = self._get_or_404(request, plan_id)
        if isinstance(plan, Response):
            return plan
        serializer = HomeTrainingPlanCreateSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        requested_customer = serializer.validated_data.get("customer")
        if requested_customer is not None and requested_customer.id != plan.customer_id:
            return ApiResponse.error("家庭训练计划不能更换客户；如需纠正请走受控流程", 400)
        serializer.validated_data.pop("customer", None)
        updated = serializer.save()
        return ApiResponse.ok(HomeTrainingPlanSerializer(updated).data, message="家庭训练已更新")
