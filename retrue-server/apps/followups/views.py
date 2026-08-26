"""followups：回访/复查接口视图。"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.followups.models import FollowUpTask
from apps.followups.serializers import FollowUpSerializer


class FollowUpListView(APIView):
    """回访/复查列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询回访/复查列表（可按客户筛选）。"""
        customer_id = request.query_params.get("customer_id", "")
        queryset = FollowUpTask.objects.filter(therapist=request.user).select_related("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        # 支持状态筛选
        status = request.query_params.get("status", "")
        if status:
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
        task = FollowUpTask.objects.create(therapist=request.user, **serializer.validated_data)
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

    def put(self, request, task_id: int):
        """更新回访状态与结果。"""
        task = self._get_or_404(request, task_id)
        if isinstance(task, Response):
            return task
        serializer = FollowUpSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("customer", None)
        updated = serializer.save()
        return ApiResponse.ok(FollowUpSerializer(updated).data, message="回访已更新")
