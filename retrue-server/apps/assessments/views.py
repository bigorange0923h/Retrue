"""assessments：评估接口视图。"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessments import services
from apps.assessments.serializers import AssessmentCreateSerializer, AssessmentSerializer
from apps.audit.models import AuditAction
from apps.common.response import ApiResponse


class AssessmentListView(APIView):
    """评估列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询某客户评估列表。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        assessments = services.list_assessments(request.user, int(customer_id))
        return ApiResponse.ok(AssessmentSerializer(assessments, many=True).data, message="查询评估成功")

    def post(self, request):
        """创建评估。"""
        serializer = AssessmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is None or customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户创建评估", 403)
        serializer.validated_data["therapist"] = request.user
        assessment = serializer.save()
        services.log_assessment_change(
            request.user, assessment, before=None, after=services.assessment_to_dict(assessment),
            action=AuditAction.CREATE, reason="创建评估",
        )
        return ApiResponse.ok(AssessmentSerializer(assessment).data, message="评估创建成功")


class AssessmentDetailView(APIView):
    """评估详情与更新接口。"""

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, assessment_id: int):
        """获取属于当前康复师的评估。"""
        assessment = services.get_assessment(request.user, assessment_id)
        if assessment is None:
            return ApiResponse.error("评估不存在或无权访问", 404)
        return assessment

    def get(self, request, assessment_id: int):
        """返回评估详情。"""
        assessment = self._get_or_404(request, assessment_id)
        if isinstance(assessment, Response):
            return assessment
        return ApiResponse.ok(AssessmentSerializer(assessment).data, message="获取评估成功")

    def put(self, request, assessment_id: int):
        """更新评估。"""
        assessment = self._get_or_404(request, assessment_id)
        if isinstance(assessment, Response):
            return assessment
        serializer = AssessmentCreateSerializer(assessment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = services.assessment_to_dict(assessment)
        updated = serializer.save()
        services.log_assessment_change(
            request.user, updated, before=before, after=services.assessment_to_dict(updated),
            action=AuditAction.UPDATE, reason="更新评估",
        )
        return ApiResponse.ok(AssessmentSerializer(updated).data, message="评估更新成功")
