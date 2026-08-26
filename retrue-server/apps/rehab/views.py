"""rehab：康复计划与阶段接口视图。"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.customers.models import Customer
from apps.rehab import services
from apps.rehab.serializers import RehabPlanSerializer, RehabStageSerializer


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
        """创建康复计划。"""
        serializer = RehabPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = _get_own_customer(request, serializer.validated_data.get("customer"))
        if isinstance(customer, Response):
            return customer
        serializer.validated_data.pop("stages", None)
        plan = services.create_plan(request.user, serializer.validated_data)
        return ApiResponse.ok(RehabPlanSerializer(plan).data, message="康复计划创建成功")


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
        serializer = RehabStageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = _get_own_customer(request, serializer.validated_data.get("customer"))
        if isinstance(customer, Response):
            return customer
        stage = services.set_stage(request.user, serializer.validated_data)
        return ApiResponse.ok(RehabStageSerializer(stage).data, message="康复阶段已更新")


def _get_own_customer(request, customer):
    """校验客户归属。"""
    if customer is None:
        return ApiResponse.error("缺少客户信息", 400)
    if customer.therapist_id != request.user.id:
        return ApiResponse.error("无权为该客户操作", 403)
    return customer
