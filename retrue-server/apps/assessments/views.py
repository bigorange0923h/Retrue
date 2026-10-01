"""assessments：评估接口视图。"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessments import services
from apps.assessments.metric_definitions import metric_definitions_for_api
from apps.assessments.models import AssessmentStatus, AssessmentType
from apps.assessments.serializers import AssessmentCreateSerializer, AssessmentSerializer
from apps.audit.models import AuditAction
from apps.common.response import ApiResponse
from apps.customers.models import Customer


def _validation_error_response(exc: serializers.ValidationError) -> Response:
    """返回带稳定 error_code 的评估参数错误。"""
    detail = exc.detail
    if isinstance(detail, dict) and "expected_updated_at" in detail:
        return ApiResponse.error(
            "评估已在其他窗口更新，本次内容未覆盖，请先核对最新版本", 409,
            data={"error_code": "assessment_version_conflict"}, http_status=409,
        )
    return ApiResponse.error(
        "评估参数校验失败",
        400,
        data={"error_code": _infer_validation_code(detail), "fields": detail},
    )


def _infer_validation_code(detail) -> str:
    """从 DRF 校验详情推断客户端可识别的错误类别。"""
    text = str(detail)
    if "范围" in text or "不能小于" in text or "不能大于" in text:
        return "metric_value_out_of_range"
    if "缺少" in text or "required" in text or "必填" in text:
        return "metric_required_field_missing"
    if "评估所属客户" in text:
        return "assessment_customer_immutable"
    if "评估类型不能修改" in text:
        return "assessment_type_immutable"
    return "invalid_input"


def _business_error_response(exc: services.AssessmentBusinessError) -> Response:
    """把服务层错误转换为统一响应信封。"""
    data = {"error_code": exc.code, **exc.details}
    return ApiResponse.error(
        exc.message,
        exc.http_status,
        data=data,
        http_status=exc.http_status,
    )


def _get_customer_for_user(request, customer_id: int):
    """获取属于当前康复师的客户，避免通过 customer_id 越权探测。"""
    return Customer.objects.filter(id=customer_id, therapist=request.user).first()


class MetricDefinitionsView(APIView):
    """指标定义接口，供前端渲染类型专用控件。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return ApiResponse.ok(metric_definitions_for_api(), message="获取评估指标定义成功")


class AssessmentListView(APIView):
    """评估列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询某客户评估列表。"""
        raw_customer_id = request.query_params.get("customer_id", "")
        try:
            customer_id = int(raw_customer_id)
        except (TypeError, ValueError):
            return ApiResponse.error("customer_id 参数无效", 400)
        if customer_id <= 0:
            return ApiResponse.error("customer_id 参数无效", 400)
        if _get_customer_for_user(request, customer_id) is None:
            return ApiResponse.error("客户不存在或无权访问", 404)
        assessments = services.list_assessments(request.user, customer_id)
        return ApiResponse.ok(AssessmentSerializer(assessments, many=True).data, message="查询评估成功")

    def post(self, request):
        """创建评估草稿。"""
        serializer = AssessmentCreateSerializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)

        try:
            services.validate_relationships(request.user, serializer.validated_data)
            customer = serializer.validated_data["customer"]
            assessment_type = serializer.validated_data.get("assessment_type", AssessmentType.INITIAL)
            services.ensure_initial_unique(request.user, customer.id, assessment_type)
            assessment = serializer.save(therapist=request.user)
        except services.AssessmentBusinessError as exc:
            return _business_error_response(exc)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)
        except IntegrityError:
            # 唯一约束处理并发创建首评；重新读取已存在的记录给前端继续编辑。
            existing = (
                services.list_assessments(request.user, customer.id)
                if "customer" in locals()
                else []
            )
            initial = next(
                (item for item in existing if item.assessment_type == AssessmentType.INITIAL),
                None,
            )
            if initial is not None:
                return _business_error_response(services.InitialAssessmentExistsError(initial))
            return ApiResponse.error("评估保存失败，请稍后重试", 400)

        services.log_assessment_change(
            request.user,
            assessment,
            before=None,
            after=services.assessment_to_dict(assessment),
            action=AuditAction.CREATE,
            reason="创建评估草稿",
        )
        return ApiResponse.ok(AssessmentSerializer(assessment).data, message="评估草稿创建成功")


class InitialAssessmentView(APIView):
    """首次评估直达接口。

    返回当前康复师对某客户的首评状态，供前端做“去评估 / 继续评估”引导，
    无需自行遍历列表判断。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw_customer_id = request.query_params.get("customer_id", "")
        try:
            customer_id = int(raw_customer_id)
        except (TypeError, ValueError):
            return ApiResponse.error("customer_id 参数无效", 400)
        if customer_id <= 0:
            return ApiResponse.error("customer_id 参数无效", 400)
        if _get_customer_for_user(request, customer_id) is None:
            return ApiResponse.error("客户不存在或无权访问", 404)

        initial = services.get_initial_assessment(request.user, customer_id)
        if initial is None:
            data = {"exists": False, "status": None, "assessment_id": None}
            return ApiResponse.ok(data, message="该客户尚无首次评估")
        data = {
            "exists": True,
            "status": initial.status,
            "assessment_id": initial.id,
        }
        return ApiResponse.ok(data, message="查询首次评估成功")


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

    @transaction.atomic
    def put(self, request, assessment_id: int):
        """更新评估草稿或已完成评估。"""
        assessment = services.get_assessment(request.user, assessment_id, for_update=True)
        if assessment is None:
            return ApiResponse.error("评估不存在或无权访问", 404)
        # 更新保持兼容宽松校验；只有 complete 接口才会强制全量必填，避免
        # 历史评估因新增字段为空而无法继续编辑。
        serializer = AssessmentCreateSerializer(
            assessment,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)

        try:
            services.validate_relationships(request.user, serializer.validated_data, instance=assessment)
            customer_id = assessment.customer_id
            assessment_type = serializer.validated_data.get("assessment_type", assessment.assessment_type)
            services.ensure_initial_unique(
                request.user,
                customer_id,
                assessment_type,
                exclude_id=assessment.id,
            )
            before = services.assessment_to_dict(assessment)
            updated = serializer.save()
        except services.AssessmentBusinessError as exc:
            return _business_error_response(exc)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)
        except IntegrityError:
            existing = (
                AssessmentType.INITIAL == assessment_type
                and services.list_assessments(request.user, customer_id)
            )
            initial = next(
                (item for item in existing if item.assessment_type == AssessmentType.INITIAL and item.id != assessment.id),
                None,
            ) if existing else None
            if initial is not None:
                return _business_error_response(services.InitialAssessmentExistsError(initial))
            return ApiResponse.error("评估保存失败，请稍后重试", 400)

        services.log_assessment_change(
            request.user,
            updated,
            before=before,
            after=services.assessment_to_dict(updated),
            action=AuditAction.UPDATE,
            reason="更新评估",
        )
        return ApiResponse.ok(AssessmentSerializer(updated).data, message="评估更新成功")


class AssessmentCompleteView(APIView):
    """评估完成接口。"""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, assessment_id: int):
        assessment = services.get_assessment(request.user, assessment_id, for_update=True)
        if assessment is None:
            return ApiResponse.error(
                "评估不存在或无权访问",
                404,
                data={"error_code": "assessment_not_found"},
            )

        try:
            # 允许完成请求同时提交最后一步内容；事务保证若完整校验失败，
            # 草稿不会被半更新。
            with transaction.atomic():
                working = assessment
                if request.data:
                    serializer = AssessmentCreateSerializer(
                        assessment,
                        data=request.data,
                        partial=True,
                        context={"request": request, "validate_complete": True},
                    )
                    serializer.is_valid(raise_exception=True)
                    services.validate_relationships(request.user, serializer.validated_data, instance=assessment)
                    assessment_type = serializer.validated_data.get("assessment_type", assessment.assessment_type)
                    services.ensure_initial_unique(
                        request.user,
                        assessment.customer_id,
                        assessment_type,
                        exclude_id=assessment.id,
                    )
                    before = services.assessment_to_dict(assessment)
                    working = serializer.save()
                    # 最后一步保存产生独立审计记录，完成动作另有 CONFIRM 审计。
                    services.log_assessment_change(
                        request.user,
                        working,
                        before=before,
                        after=services.assessment_to_dict(working),
                        action=AuditAction.UPDATE,
                        reason="完成评估前保存",
                    )
                completed = services.complete_assessment(request.user, working)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)
        except services.AssessmentBusinessError as exc:
            return _business_error_response(exc)
        except IntegrityError:
            return ApiResponse.error(
                "评估保存失败，请稍后重试",
                400,
                data={"error_code": "assessment_save_failed"},
            )

        return ApiResponse.ok(AssessmentSerializer(completed).data, message="评估已完成")


class AssessmentInputView(APIView):
    """当前评估的自然语言整理与未采用候选恢复，不创建或完成评估。"""

    permission_classes = [IsAuthenticated]

    def _context(self, request, data):
        """通过 DRF 校验上下文参数，再由图验证数据库归属。"""
        class ContextSerializer(serializers.Serializer):
            customer_id = serializers.IntegerField(min_value=1)
            assessment_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
            assessment_type = serializers.ChoiceField(choices=["initial", "reassessment"], default="initial")
            input_text = serializers.CharField(max_length=8000, required=request.method == "POST", trim_whitespace=True)

        serializer = ContextSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return {"therapist": request.user, **serializer.validated_data}

    def post(self, request):
        """用户主动提交本次文字给模型，返回有原文依据的持久候选。"""
        from apps.ai.orchestration.assessment_input import organize_assessment_input

        try:
            draft = organize_assessment_input(**self._context(request, request.data))
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)
        except Exception:
            # 不把 provider 异常中的提示词、客户原文或密钥回传给用户/日志。
            return ApiResponse.error("暂时无法整理，输入仍在当前页面，可重试或按项目填写", 502, http_status=502)
        return ApiResponse.ok(self._result(draft), message="已整理为候选，请复核后采用")

    def put(self, request):
        """只保存描述文字供恢复，不发送模型、不修改评估字段。"""
        from apps.ai.models import AiDraft, AiDraftStatus, AiDraftType
        from apps.ai.orchestration.assessment_input import authorize

        try:
            context = self._context(request, request.data)
            if not context.get("input_text"):
                return ApiResponse.error("描述不能为空", 400, http_status=400)
            authorize(context)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)
        existing_id = request.data.get("source_draft_id")
        if existing_id is not None:
            if isinstance(existing_id, bool) or not isinstance(existing_id, int):
                return ApiResponse.error("描述候选参数无效", 400, http_status=400)
            with transaction.atomic():
                existing = AiDraft.objects.select_for_update().filter(
                    id=existing_id, therapist=request.user, customer_id=context["customer_id"],
                    draft_type=AiDraftType.ASSESSMENT, status=AiDraftStatus.PENDING,
                    ai_result__input_version=1, ai_result__assessment_type=context["assessment_type"],
                ).first()
                if existing is None or existing.input_text != context["input_text"] or existing.assessment_id not in (None, context.get("assessment_id")):
                    return ApiResponse.error("描述候选已变化，请重新保存本次文字", 409, http_status=409)
                existing.assessment_id = context.get("assessment_id")
                existing.save(update_fields=["assessment", "updated_at"])
                return ApiResponse.ok(self._result(existing), message="描述候选已关联当前草稿")
        result = {"input_version": 1, "assessment_type": context["assessment_type"], "source_only": True, "fields": [], "metrics": [], "warnings": []}
        draft = AiDraft.objects.create(
            therapist=request.user, customer_id=context["customer_id"], assessment_id=context.get("assessment_id"),
            draft_type=AiDraftType.ASSESSMENT, status=AiDraftStatus.PENDING,
            input_text=context["input_text"], ai_result=result,
        )
        return ApiResponse.ok(self._result(draft), message="描述已保存，尚未发送 AI 或采用到评估")

    def get(self, request):
        """刷新后恢复同客户、同评估类型和同目标的最新未采用候选。"""
        from apps.ai.models import AiDraft, AiDraftStatus, AiDraftType
        from apps.ai.orchestration.assessment_input import authorize

        try:
            context = self._context(request, request.query_params)
            authorize(context)
        except serializers.ValidationError as exc:
            return _validation_error_response(exc)
        draft = AiDraft.objects.filter(
            therapist=request.user, customer_id=context["customer_id"],
            assessment_id=context.get("assessment_id"), draft_type=AiDraftType.ASSESSMENT,
            status=AiDraftStatus.PENDING, ai_result__input_version=1,
            ai_result__assessment_type=context["assessment_type"],
        ).order_by("-id").first()
        return ApiResponse.ok(self._result(draft) if draft else None, message="查询录入候选成功")

    def _result(self, draft):
        """输出当前用户可复核的候选与原文；不返回其他业务上下文。"""
        return {"id": draft.id, "input_text": draft.input_text, **draft.ai_result}
