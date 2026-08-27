"""ai：AI 草稿接口视图。

提供训练文本解析、草稿确认、取消、列表与客户候选接口。
AI 只生成草稿，确认后才创建正式训练记录。
"""

from __future__ import annotations

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.ai.models import AiDraft
from apps.ai.serializers import (
    AiDraftSerializer,
    ConfirmDraftSerializer,
    ParseDraftSerializer,
)
from apps.ai.services import preparation, training_parser
from apps.common.response import ApiResponse


class ParseDraftView(APIView):
    """解析训练文本生成草稿接口。

    权限：需已登录。
    说明：将自然语言解析为待确认草稿，失败时草稿状态为 failed。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """生成训练草稿。"""
        serializer = ParseDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = training_parser.parse_training_draft(
            request.user,
            serializer.validated_data["input_text"],
            serializer.validated_data.get("customer_id"),
        )
        return ApiResponse.ok(AiDraftSerializer(draft).data, message="草稿生成成功")


class ConfirmDraftView(APIView):
    """确认草稿并创建正式训练记录接口。

    权限：需已登录，且草稿属于当前康复师。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, draft_id: int):
        """确认草稿。"""
        serializer = ConfirmDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            draft = training_parser.confirm_training_draft(
                request.user,
                draft_id,
                serializer.validated_data["confirmed"],
                serializer.validated_data["customer_id"],
            )
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(AiDraftSerializer(draft).data, message="已确认并创建训练记录")


class CancelDraftView(APIView):
    """取消草稿接口。

    权限：需已登录。
    说明：取消后不创建任何正式记录。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, draft_id: int):
        """取消草稿。"""
        try:
            draft = training_parser.cancel_draft(request.user, draft_id)
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(AiDraftSerializer(draft).data, message="草稿已取消")


class DraftListView(APIView):
    """当前康复师待确认草稿列表接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回待确认草稿列表。"""
        drafts = AiDraft.objects.filter(therapist=request.user, status="pending")
        return ApiResponse.ok(AiDraftSerializer(drafts, many=True).data, message="查询草稿成功")


class CustomerCandidateView(APIView):
    """客户候选查询接口。

    权限：需已登录。
    说明：按姓名提示返回客户候选，用于草稿客户识别不确定时选择。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回客户候选列表。"""
        name_hint = request.query_params.get("name", "").strip()
        candidates = training_parser.suggest_customer_candidates(request.user, name_hint)
        return ApiResponse.ok(candidates, message="查询客户候选成功")


class LessonPreparationView(APIView):
    """备课助手接口。

    权限：需已登录。
    说明：系统汇总客户历史，AI 生成备课建议。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回备课助手内容。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        try:
            result = preparation.prepare_lesson(request.user, int(customer_id))
        except Exception:
            return ApiResponse.error("备课建议生成失败", 500)
        return ApiResponse.ok(result, message="备课建议生成成功")
