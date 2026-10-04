"""客户导出与只读删除影响预览；执行删除流程尚未开放。"""

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.customers.lifecycle import deletion_preview, export_customer
from apps.customers.services import get_customer


def _customer(request, customer_id: int):
    """隐去跨账号客户的存在性，保持统一权限响应。"""
    customer = get_customer(request.user, customer_id)
    if customer is None:
        raise NotFound("客户不存在或无权访问")
    return customer


class CustomerExportView(APIView):
    """返回可下载内容及文件元数据，仍使用统一响应信封。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id: int):
        """output=json/report；当前仅提供脱敏导出，不提升完整信息权限。"""
        customer = _customer(request, customer_id)
        output = request.query_params.get("output", "json")
        if output not in {"json", "report"}:
            raise ValidationError("output 必须为 json 或 report")
        if request.query_params.get("include_sensitive", "false").lower() not in {"false", "0", ""}:
            raise ValidationError("当前仅开放手机号脱敏导出")
        response = ApiResponse.ok(export_customer(request.user, customer, output), message="客户资料导出成功")
        response["Cache-Control"] = "no-store"
        return response


class CustomerDeletionPreviewView(APIView):
    """只读计算资源范围与边界，不开放 DELETE 或写入任何生命周期标记。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, customer_id: int):
        """返回关联资源数量、派生内容与待确认策略，无写入副作用。"""
        response = ApiResponse.ok(deletion_preview(request.user, _customer(request, customer_id)), message="删除影响预览成功")
        response["Cache-Control"] = "no-store"
        return response
