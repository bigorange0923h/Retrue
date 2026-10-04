"""followups：回访/复查接口视图。"""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.followups.models import FollowUpTask
from apps.followups.serializers import FollowUpSerializer
from apps.followups.services import create_followup, update_followup


class FollowUpListView(APIView):
    """回访/复查列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询回访/复查列表（可按客户筛选）。"""
        customer_id = request.query_params.get("customer_id", "")
        queryset = FollowUpTask.objects.filter(therapist=request.user).select_related("customer")
        if customer_id:
            try:
                customer_id = int(customer_id)
                if customer_id <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValidationError("客户编号必须为正整数")
            queryset = queryset.filter(customer_id=customer_id)
        # 支持状态筛选
        status = request.query_params.get("status", "")
        if status:
            if status not in {"pending", "done", "skipped"}:
                raise ValidationError("回访状态无效")
            queryset = queryset.filter(status=status)
        return ApiResponse.ok(FollowUpSerializer(queryset, many=True).data, message="查询回访成功")

    def post(self, request):
        """创建回访/复查。"""
        serializer = FollowUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is None or customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户创建回访", 403)
        serializer.validated_data.pop("customer_name", None)
        task = create_followup(request.user, serializer.validated_data)
        return ApiResponse.ok(FollowUpSerializer(task).data, message="回访创建成功")


class FollowUpDetailView(APIView):
    """回访/复查更新接口（完成/修改状态）。"""

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, task_id: int):
        """获取属于当前康复师的待办。"""
        task = FollowUpTask.objects.filter(therapist=request.user, id=task_id).first()
        if task is None:
            return ApiResponse.error("回访不存在或无权访问", 404)
        return task

    @transaction.atomic
    def put(self, request, task_id: int):
        """更新回访状态与结果。"""
        task = FollowUpTask.objects.select_for_update().filter(therapist=request.user, id=task_id).first()
        if task is None:
            return ApiResponse.error("回访不存在或无权访问", 404)
        serializer = FollowUpSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated, next_task = update_followup(request.user, task, serializer)
        data = dict(FollowUpSerializer(updated).data)
        if next_task is not None:
            data["next_task_id"] = next_task.id
        return ApiResponse.ok(data, message="回访已更新")
