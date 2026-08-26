"""training：训练记录接口视图。

提供训练记录的列表、创建、详情、人工修订与客户时间线接口。
修订正式记录必须填写修改原因，并记录审计。
"""

from __future__ import annotations

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.customers.models import Customer
from apps.training import services
from apps.training.serializers import (
    TrainingRecordCreateSerializer,
    TrainingRecordRevisionSerializer,
    TrainingRecordSerializer,
)


class TrainingRecordListView(APIView):
    """训练记录列表与创建接口。

    权限：需已登录。
    GET：分页返回某客户（customer_id）的训练记录。
    POST：创建训练记录，客户须属于当前康复师。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """分页查询训练记录。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        page, page_size = _parse_page(request)
        result = services.list_records(request.user, int(customer_id), page=page, page_size=page_size)
        items = TrainingRecordSerializer(result["items"], many=True).data
        return ApiResponse.ok_page(items, result["page"], result["page_size"], result["total"])

    def post(self, request):
        """创建训练记录。"""
        serializer = TrainingRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = _get_own_customer(request, serializer.validated_data.get("customer"))
        if isinstance(customer, Response):
            return customer
        serializer.validated_data["therapist"] = request.user
        record = serializer.save()
        from apps.audit.models import AuditAction, write_audit_log

        write_audit_log(
            actor=request.user,
            action=AuditAction.CREATE,
            obj=record,
            after=services.record_to_dict(record),
            reason="创建训练记录",
        )
        return ApiResponse.ok(TrainingRecordSerializer(record).data, message="训练记录创建成功")


class TrainingRecordDetailView(APIView):
    """训练记录详情与人工修订接口。

    权限：需已登录，且记录属于当前康复师。
    GET：返回单条训练记录详情。
    PUT：人工修订，必须提供修改原因，记录前后快照与操作人。
    """

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, record_id: int):
        """获取属于当前康复师的训练记录。"""
        record = services.get_record(request.user, record_id)
        if record is None:
            return ApiResponse.error("训练记录不存在或无权访问", 404)
        return record

    def get(self, request, record_id: int):
        """返回训练记录详情。"""
        record = self._get_or_404(request, record_id)
        if isinstance(record, Response):
            return record
        return ApiResponse.ok(TrainingRecordSerializer(record).data, message="获取训练记录成功")

    def put(self, request, record_id: int):
        """人工修订训练记录。"""
        record = self._get_or_404(request, record_id)
        if isinstance(record, Response):
            return record

        revision_serializer = TrainingRecordRevisionSerializer(data=request.data)
        revision_serializer.is_valid(raise_exception=True)
        reason = revision_serializer.validated_data["reason"]

        data = dict(request.data)
        data.pop("reason", None)
        serializer = TrainingRecordCreateSerializer(record, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        before = services.record_to_dict(record)
        updated = serializer.save()
        services.write_revision_log(
            request.user,
            updated,
            before=before,
            after=services.record_to_dict(updated),
            reason=reason,
        )
        return ApiResponse.ok(TrainingRecordSerializer(updated).data, message="训练记录已更新")


class CustomerTimelineView(APIView):
    """客户时间线接口。

    权限：需已登录。
    说明：返回某客户按日期倒序的训练记录，用于时间线展示。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回客户时间线。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        records = services.get_customer_timeline(request.user, int(customer_id))
        return ApiResponse.ok(TrainingRecordSerializer(records, many=True).data, message="查询时间线成功")


def _get_own_customer(request, customer: Customer | None):
    """校验客户归属，返回客户或错误响应。

    参数：
        request: 请求对象。
        customer: 客户实例或 None。
    返回：
        Customer 实例或 DRF Response。
    """
    if customer is None:
        return ApiResponse.error("缺少客户信息", 400)
    if customer.therapist_id != request.user.id:
        return ApiResponse.error("无权为该客户创建记录", 403)
    return customer


def _parse_page(request) -> tuple[int, int]:
    """解析分页参数。"""
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError):
        page_size = 20
    return page, page_size
