"""audit：审计日志查询视图。

提供审计日志的分页列表查询，可按被操作对象筛选。
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer
from apps.common.response import ApiResponse


class AuditLogListView(APIView):
    """审计日志列表查询接口。

    权限：需已登录。
    查询参数：
        content_type: ContentType id（可选）。
        object_id: 业务对象 id（可选，配合 content_type 使用）。
        page: 页码，默认 1。
        page_size: 每页条数，默认 20。
    返回：分页信封结构 {items, page, page_size, total}。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回审计日志分页列表。"""
        content_type_id = request.query_params.get("content_type")
        object_id = request.query_params.get("object_id")

        queryset = AuditLog.objects.select_related("actor").order_by("-created_at")

        if content_type_id and object_id:
            queryset = queryset.filter(content_type_id=content_type_id, object_id=object_id)

        # 解析分页参数
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
        except (TypeError, ValueError):
            page_size = 20

        total = queryset.count()
        start = (page - 1) * page_size
        items = queryset[start : start + page_size]

        data = {
            "items": AuditLogSerializer(items, many=True).data,
            "page": page,
            "page_size": page_size,
            "total": total,
        }
        return ApiResponse.ok(data, message="查询审计日志成功")


class AuditLogObjectListView(APIView):
    """按业务对象类型查询其审计历史（按模型 + 主键）。

    查询参数：
        model: 模型名，如 customer、trainingrecord。
        object_id: 对象主键。
    返回：该对象的审计日志列表（不含分页，便于前端时间线展示）。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回指定对象的审计日志列表。"""
        model_name = (request.query_params.get("model") or "").lower()
        object_id = request.query_params.get("object_id")
        if not model_name or not object_id:
            return ApiResponse.error("缺少 model 或 object_id 参数", 400)

        content_type = ContentType.objects.filter(model=model_name).first()
        if content_type is None:
            return ApiResponse.error("未知的对象类型", 400)

        logs = (
            AuditLog.objects.filter(content_type=content_type, object_id=str(object_id))
            .select_related("actor")
            .order_by("-created_at")
        )
        return ApiResponse.ok(AuditLogSerializer(logs, many=True).data, message="查询审计历史成功")
