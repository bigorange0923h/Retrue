"""ai：AI 草稿接口视图。

提供训练文本解析、草稿确认、取消、列表与客户候选接口。
AI 只生成草稿，确认后才创建正式训练记录。
"""

from __future__ import annotations

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.models import AiDraft, AiDraftType, RiskAlert
from apps.ai.serializers import (
    AiDraftSerializer,
    ConfirmDraftSerializer,
    ParseDraftSerializer,
    RiskAlertSerializer,
)
from apps.ai.services import domain_drafts, preparation, progress, qa, risk, training_parser
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
        try:
            draft = training_parser.parse_training_draft(
                request.user,
                serializer.validated_data["input_text"],
                serializer.validated_data.get("customer_id"),
                serializer.validated_data.get("assistant_task_id"),
                serializer.validated_data.get("course_session_id"),
                serializer.validated_data.get("client_request_id")
                or request.headers.get("Idempotency-Key", ""),
            )
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(AiDraftSerializer(draft).data, message="草稿生成成功")


class ConfirmDraftView(APIView):
    """确认草稿并写入正式记录接口。

    按草稿类型分派：训练补记走训练确认；评估/训练修订/随访走领域草稿确认。
    权限：需已登录，且草稿属于当前康复师。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, draft_id: int):
        """确认草稿。"""
        serializer = ConfirmDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = (
            serializer.validated_data.get("idempotency_key")
            or request.headers.get("Idempotency-Key", "")
        )
        draft_obj = AiDraft.objects.filter(therapist=request.user, id=draft_id).first()
        if draft_obj is None:
            return ApiResponse.error("草稿不存在或无权访问", 400)

        confirmed = serializer.validated_data["confirmed"]
        customer_id = serializer.validated_data["customer_id"]
        try:
            if draft_obj.draft_type == AiDraftType.ASSESSMENT:
                draft = domain_drafts.confirm_assessment_draft(
                    request.user, draft_id, confirmed, customer_id, idempotency_key
                )
            elif draft_obj.draft_type == AiDraftType.TRAINING_REVISION:
                draft = domain_drafts.confirm_training_revision_draft(
                    request.user, draft_id, confirmed, customer_id, idempotency_key
                )
            elif draft_obj.draft_type == AiDraftType.FOLLOWUP:
                draft = domain_drafts.confirm_followup_draft(
                    request.user, draft_id, confirmed, customer_id, idempotency_key
                )
            else:
                draft = training_parser.confirm_training_draft(
                    request.user,
                    draft_id,
                    confirmed,
                    customer_id,
                    serializer.validated_data.get("course_session_id"),
                    idempotency_key,
                )
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(AiDraftSerializer(draft).data, message="已确认并写入正式记录")


class CancelDraftView(APIView):
    """取消草稿接口。

    权限：需已登录。
    说明：取消后不创建任何正式记录。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, draft_id: int):
        """取消草稿。"""
        try:
            draft_obj = AiDraft.objects.filter(therapist=request.user, id=draft_id).first()
            if draft_obj is None:
                return ApiResponse.error("草稿不存在或无权访问", 400)
            if draft_obj.draft_type == AiDraftType.TRAINING_RECORD:
                draft = training_parser.cancel_draft(request.user, draft_id)
            else:
                draft = domain_drafts.cancel_domain_draft(request.user, draft_id)
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


class RiskAlertListView(APIView):
    """风险提醒列表接口。

    权限：需已登录。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询风险提醒列表（可按客户筛选）。"""
        customer_id = request.query_params.get("customer_id", "")
        queryset = RiskAlert.objects.filter(therapist=request.user).select_related("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        return ApiResponse.ok(RiskAlertSerializer(queryset, many=True).data, message="查询风险提醒成功")


class RiskDetectView(APIView):
    """风险检测接口。

    权限：需已登录。
    说明：从客户最近训练记录检测风险并保存提醒。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """执行风险检测。"""
        customer_id = request.data.get("customer_id", "")
        record_id = request.data.get("training_record_id")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        record = None
        if record_id:
            from apps.training.models import TrainingRecord

            record = TrainingRecord.objects.filter(therapist=request.user, id=record_id).first()
        alert = risk.detect_risk(request.user, int(customer_id), record)
        if alert is None:
            return ApiResponse.ok(None, message="未检测到风险")
        return ApiResponse.ok(RiskAlertSerializer(alert).data, message="检测到风险")


class RiskAlertUpdateView(APIView):
    """风险提醒确认与处理结果更新接口。"""

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, alert_id: int):
        """获取属于当前康复师的风险提醒。"""
        alert = RiskAlert.objects.filter(therapist=request.user, id=alert_id).first()
        if alert is None:
            return ApiResponse.error("风险提醒不存在或无权访问", 404)
        return alert

    def put(self, request, alert_id: int):
        """更新风险确认状态与处理结果。"""
        alert = self._get_or_404(request, alert_id)
        if isinstance(alert, Response):
            return alert
        alert.is_confirmed = request.data.get("is_confirmed", alert.is_confirmed)
        alert.outcome = request.data.get("outcome", alert.outcome)
        alert.save()
        return ApiResponse.ok(RiskAlertSerializer(alert).data, message="风险提醒已更新")


class ProgressAnalysisView(APIView):
    """阶段进展参考接口。

    权限：需已登录。
    说明：AI 分析客户历史记录生成阶段进展参考，不自动修改康复阶段。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回阶段进展参考。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        result = progress.analyze_progress(request.user, int(customer_id))
        return ApiResponse.ok(result, message="阶段进展分析成功")


class QaView(APIView):
    """专业问答接口。

    权限：需已登录。
    说明：基于内部知识库（动作库）回答康复专业问题，不替代诊断。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """回答专业问题。"""
        question = request.data.get("question", "").strip()
        if not question:
            return ApiResponse.error("缺少问题内容", 400)
        result = qa.answer_question(request.user, question)
        return ApiResponse.ok(result, message="回答成功")
