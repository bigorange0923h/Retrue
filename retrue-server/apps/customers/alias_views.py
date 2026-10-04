"""客户别称接口：独立客户归属检查，增改与停用，不提供物理删除。"""

from django.db import transaction
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.customers.alias_services import save_alias
from apps.customers.models import CustomerAlias
from apps.customers.serializers import CustomerAliasSerializer
from apps.customers.services import get_customer


def _owned_customer(request, customer_id: int):
    """只返回当前康复师的客户，其他账号与不存在使用相同响应。"""
    customer = get_customer(request.user, customer_id)
    if customer is None:
        raise NotFound("客户不存在或无权访问")
    return customer


class CustomerAliasListView(APIView):
    """查询全部别称（含停用）及新增。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id: int):
        """返回本人客户别称，便于核对或重新启用。"""
        customer = _owned_customer(request, customer_id)
        rows = CustomerAlias.objects.filter(therapist=request.user, customer=customer).order_by("id")
        return ApiResponse.ok(CustomerAliasSerializer(rows, many=True).data, message="查询客户别称成功")

    def post(self, request, customer_id: int):
        """创建明确指向当前客户的别称，不做自动客户匹配。"""
        customer = _owned_customer(request, customer_id)
        serializer = CustomerAliasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alias = save_alias(request.user, customer, serializer.validated_data)
        return ApiResponse.ok(CustomerAliasSerializer(alias).data, message="客户别称已创建")


class CustomerAliasDetailView(APIView):
    """编辑或停用客户别称。"""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def put(self, request, customer_id: int, alias_id: int):
        """锁定本人客户的别称，更新原文和启用状态。"""
        customer = _owned_customer(request, customer_id)
        alias = CustomerAlias.objects.select_for_update().filter(
            id=alias_id, customer=customer, therapist=request.user
        ).first()
        if alias is None:
            raise NotFound("客户别称不存在或无权访问")
        serializer = CustomerAliasSerializer(alias, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = save_alias(request.user, customer, serializer.validated_data, alias)
        return ApiResponse.ok(CustomerAliasSerializer(updated).data, message="客户别称已更新")
