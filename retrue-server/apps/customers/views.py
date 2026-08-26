"""customers：客户接口视图。

提供客户列表（脱敏）、详情、创建、更新接口，所有操作强制数据隔离。
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.customers import services
from apps.customers.serializers import (
    CustomerCreateSerializer,
    CustomerDetailSerializer,
    CustomerListSerializer,
)


class CustomerListView(APIView):
    """客户列表与创建接口。

    权限：需已登录。
    GET：分页返回当前康复师的客户（脱敏手机号），支持 keyword 与 status 筛选。
    POST：创建客户。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """分页查询客户列表。"""
        keyword = request.query_params.get("keyword", "").strip()
        status = request.query_params.get("status", "").strip()
        page, page_size = _parse_page(request)

        result = services.list_customers(
            request.user,
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size,
        )
        items = CustomerListSerializer(result["items"], many=True).data
        return ApiResponse.ok_page(items, result["page"], result["page_size"], result["total"])

    def post(self, request):
        """创建客户。"""
        serializer = CustomerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = services.create_customer(request.user, serializer.validated_data)
        return ApiResponse.ok(CustomerDetailSerializer(customer).data, message="客户创建成功")


class CustomerDetailView(APIView):
    """客户详情与更新接口。

    权限：需已登录，且客户须属于当前康复师。
    GET：返回客户详情（含完整手机号，供资料编辑）。
    PUT：更新客户资料。
    """

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, customer_id: int):
        """获取属于当前康复师的客户，否则返回统一 404 响应。

        参数：
            request: 请求对象。
            customer_id: 客户主键。
        返回：
            Customer 实例；不存在或无权访问时返回 DRF Response。
        """
        customer = services.get_customer(request.user, customer_id)
        if customer is None:
            return ApiResponse.error("客户不存在或无权访问", 404)
        return customer

    def get(self, request, customer_id: int):
        """返回客户详情。"""
        customer = self._get_or_404(request, customer_id)
        if isinstance(customer, Response):
            return customer
        return ApiResponse.ok(CustomerDetailSerializer(customer).data, message="获取客户详情成功")

    def put(self, request, customer_id: int):
        """更新客户资料。"""
        customer = self._get_or_404(request, customer_id)
        if isinstance(customer, Response):
            return customer
        serializer = CustomerCreateSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_customer(request.user, customer, serializer.validated_data)
        return ApiResponse.ok(CustomerDetailSerializer(updated).data, message="客户更新成功")


def _parse_page(request) -> tuple[int, int]:
    """解析分页参数，带默认值与边界保护。

    参数：
        request: 请求对象。
    返回：
        (page, page_size) 元组。
    """
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError):
        page_size = 20
    return page, page_size
