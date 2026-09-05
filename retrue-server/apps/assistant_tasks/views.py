"""AssistantTask 统一任务接口视图。"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.assistant_tasks import services
from apps.assistant_tasks.models import AssistantTask
from apps.assistant_tasks.serializers import (
    AssistantResumeSerializer,
    AssistantTaskSerializer,
    AssistantTurnSerializer,
    CancelTaskSerializer,
    CustomerNameLookupSerializer,
    CustomerSelectionSerializer,
    ToolExecuteSerializer,
)
from apps.common.response import ApiResponse
from apps.assistant_tasks import tools


def _business_error_response(exc: services.TaskBusinessError):
    """将任务领域错误转换为统一 API 响应。"""
    return ApiResponse.error(
        str(exc),
        code=exc.http_status,
        data={"error_code": exc.code},
    )


def _parse_bool(value: Any) -> bool | None:
    """解析查询参数中的布尔值，无法识别时返回 None。"""
    if value is None or value == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("resumable 参数必须是 true 或 false")


class AssistantTaskListCreateView(APIView):
    """当前康复师的助手任务列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """按客户、状态和可恢复条件查询当前康复师的任务。"""
        services.recover_stale_running_tasks(request.user)
        customer = request.query_params.get("customer", request.query_params.get("customer_id"))
        if customer == "":
            customer = None
        try:
            resumable = _parse_bool(request.query_params.get("resumable"))
            queryset = services.list_owned_tasks(
                request.user,
                customer=customer,
                status=request.query_params.get("status") or None,
                resumable=resumable,
            )
        except services.TaskBusinessError as exc:
            return _business_error_response(exc)
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400, data={"error_code": "query_invalid"})

        # 列表同样返回统一任务结构，预取关系避免每条任务重复访问数据库。
        queryset = queryset.prefetch_related("runs", "tool_executions", "events")[:100]
        return ApiResponse.ok(
            AssistantTaskSerializer(queryset, many=True).data,
            message="查询助手任务成功",
        )

    def post(self, request):
        """创建助手任务，支持客户端请求幂等和业务键复用。"""
        serializer = AssistantTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        if not validated_data.get("client_request_id"):
            # 同时支持标准 Idempotency-Key 请求头，方便移动端和重试中间件
            # 不必把幂等标识重复放入业务 JSON。
            header_key = request.headers.get("Idempotency-Key", "").strip()
            if header_key:
                validated_data["client_request_id"] = header_key
        try:
            task = services.create_task(request.user, **validated_data)
        except services.TaskBusinessError as exc:
            return _business_error_response(exc)
        return ApiResponse.ok(
            AssistantTaskSerializer(task).data,
            message="助手任务已创建",
        )


class AssistantTaskDetailView(APIView):
    """单条助手任务详情和安全恢复数据更新接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, task_id: int):
        """仅返回当前康复师拥有的任务详情。"""
        services.recover_stale_running_tasks(request.user, task_id)
        task = services.get_owned_task(request.user, task_id)
        if task is None:
            return ApiResponse.error("助手任务不存在或无权访问", 404)
        task = (
            AssistantTask.objects.filter(pk=task.pk)
            .select_related("customer", "conversation")
            .prefetch_related("runs", "tool_executions", "events")
            .first()
        )
        if task is None:
            return ApiResponse.error("助手任务不存在或无权访问", 404)
        return ApiResponse.ok(AssistantTaskSerializer(task).data, message="查询助手任务成功")

    def patch(self, request, task_id: int):
        """使用 version 乐观锁保存安全的任务恢复数据。

        仅允许更新 current_step、missing_fields、state_data、customer 和
        conversation；任务状态、完成/取消时间及结果引用必须由后端服务变更。
        """
        task = services.get_owned_task(request.user, task_id)
        if task is None:
            return ApiResponse.error("助手任务不存在或无权访问", 404)
        payload = dict(request.data)
        allowed = {"version", "current_step", "missing_fields", "state_data", "customer", "conversation"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            return ApiResponse.error(
                "任务只允许保存恢复字段",
                400,
                data={"error_code": "task_patch_field_not_allowed", "fields": unknown},
            )
        if "version" not in payload:
            return ApiResponse.error("缺少 version 参数", 400, data={"error_code": "task_version_required"})

        # 对关系字段使用与创建相同的主键序列化，再把校验后的对象交给 service。
        input_serializer = AssistantTaskSerializer(
            task,
            data={key: value for key, value in payload.items() if key != "version"},
            partial=True,
        )
        input_serializer.is_valid(raise_exception=True)
        attrs = input_serializer.validated_data
        update_kwargs = {
            key: attrs[key]
            for key in ("current_step", "missing_fields", "state_data", "customer", "conversation")
            if key in attrs
        }
        try:
            updated = services.update_task_state(task, payload["version"], **update_kwargs)
        except services.TaskBusinessError as exc:
            return _business_error_response(exc)
        return ApiResponse.ok(AssistantTaskSerializer(updated).data, message="助手任务已保存")


class AssistantTaskCancelView(APIView):
    """助手任务取消接口。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int):
        """取消当前康复师拥有的未结束任务。"""
        task = services.get_owned_task(request.user, task_id)
        if task is None:
            return ApiResponse.error("助手任务不存在或无权访问", 404)
        serializer = CancelTaskSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            cancelled = services.cancel_task(task, serializer.validated_data.get("reason", ""))
        except services.TaskBusinessError as exc:
            return _business_error_response(exc)
        return ApiResponse.ok(
            AssistantTaskSerializer(cancelled).data,
            message="助手任务已取消",
        )


class AssistantCustomerNameLookupView(APIView):
    """按姓名返回当前康复师名下客户候选，供聊天页处理同名歧义。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """只返回当前登录康复师的精确同名客户列表。"""
        serializer = CustomerNameLookupSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            matches = tools.lookup_current_therapist_customers_by_name(
                request.user,
                serializer.validated_data["name"],
            )
        except tools.ToolBusinessError as exc:
            return _business_error_response(exc)
        return ApiResponse.ok(matches, message="查询客户候选成功")


class AssistantTaskToolExecuteView(APIView):
    """执行当前康复师任务上的受控只读 Tool。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int):
        """仅为当前康复师自己的任务执行固定白名单中的只读查询。"""
        task = services.get_owned_task(request.user, task_id)
        if task is None:
            return ApiResponse.error("助手任务不存在或无权访问", 404)

        serializer = ToolExecuteSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        if not validated.get("client_request_id"):
            request_id = request.headers.get("Idempotency-Key", "").strip()
            if request_id:
                validated["client_request_id"] = request_id
        try:
            execution_result = tools.execute_tool(
                task,
                validated["tool_name"],
                validated.get("arguments", {}),
                client_request_id=validated.get("client_request_id", ""),
            )
        except services.TaskBusinessError as exc:
            return _business_error_response(exc)
        except tools.ToolBusinessError as exc:
            return _business_error_response(exc)

        # 业务结果可供当前编排器继续生成草稿；Run/Tool 只返回 ID 与脱敏摘要。
        return ApiResponse.ok(
            {
                "tool_name": execution_result.tool_execution.tool_name,
                "result": dict(execution_result),
                "run_id": execution_result.run.id,
                "tool_execution_id": execution_result.tool_execution.id,
                "run": {
                    "id": execution_result.run.id,
                    "status": execution_result.run.status,
                    "input_summary": execution_result.run.input_summary,
                    "output_summary": execution_result.run.output_summary,
                },
                "tool_execution": {
                    "id": execution_result.tool_execution.id,
                    "status": execution_result.tool_execution.status,
                    "input_summary": execution_result.tool_execution.input_summary,
                    "output_summary": execution_result.tool_execution.output_summary,
                    "is_write": execution_result.tool_execution.is_write,
                    "requires_confirmation": execution_result.tool_execution.requires_confirmation,
                },
            },
            message="助手查询工具执行成功",
        )


logger = logging.getLogger(__name__)


def _orchestration_error_response(exc: Exception):
    """把编排层错误转换为统一 API 响应。

    无法识别的异常返回通用 500，但先记录完整 traceback，便于排查
    （不向客户端泄露堆栈）。
    """
    from apps.ai.orchestration import OrchestrationDisabledError, NodeLimitError

    if isinstance(exc, OrchestrationDisabledError):
        return ApiResponse.error(str(exc), 503, data={"error_code": "orchestration_disabled"})
    if isinstance(exc, NodeLimitError):
        return ApiResponse.error(str(exc), 400, data={"error_code": exc.error_code})
    if isinstance(exc, services.TaskBusinessError):
        return _business_error_response(exc)
    logger.exception("编排处理异常: %s", exc)
    return ApiResponse.error("AI 助理暂时无法处理该请求，请稍后重试", 500, data={"error_code": "orchestration_failed"})


class AssistantTurnView(APIView):
    """统一回合入口：把一次用户输入送入受控图流程。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AssistantTurnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        client_request_id = validated.get("client_request_id", "")
        if not client_request_id:
            client_request_id = request.headers.get("Idempotency-Key", "").strip()
        try:
            from apps.ai.orchestration import service as orchestration

            result = orchestration.handle_turn(
                request.user,
                message=validated["message"],
                conversation_id=validated.get("conversation_id"),
                customer_id=validated.get("customer_id"),
                customer_name=validated.get("customer_name", ""),
                client_request_id=client_request_id,
            )
        except Exception as exc:  # noqa: BLE001 - 编排错误统一转为安全响应
            return _orchestration_error_response(exc)
        return ApiResponse.ok(result, message="对话处理完成")


class AssistantTurnStreamView(APIView):
    """单次 POST 推送真实阶段与最终结果；认证及 CSRF 沿用统一会话接口。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """开流前校验输入和数据归属，流内仍复用原受控编排服务。"""
        from apps.ai.orchestration import service as orchestration
        from apps.assistant_tasks.streaming import turn_stream_response

        serializer = AssistantTurnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        therapist = request.user
        validated["client_request_id"] = validated.get("client_request_id") or request.headers.get("Idempotency-Key", "").strip()
        try:
            orchestration._ensure_enabled()
            orchestration._resolve_effective_customer_id(
                therapist,
                conversation_id=validated.get("conversation_id"),
                requested_customer_id=validated.get("customer_id"),
            )
        except Exception as exc:
            return _orchestration_error_response(exc)
        return turn_stream_response(
            request,
            lambda: orchestration.handle_turn(therapist, **validated),
            _orchestration_error_response,
        )


class AssistantTurnResumeView(APIView):
    """恢复未完成任务：只接收允许继续的信息，不接受客户端伪造节点/状态。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int):
        serializer = AssistantResumeSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            from apps.ai.orchestration import service as orchestration

            result = orchestration.resume_task(
                request.user,
                task_id,
                message=serializer.validated_data.get("message", ""),
            )
        except Exception as exc:  # noqa: BLE001
            return _orchestration_error_response(exc)
        return ApiResponse.ok(result, message="任务已恢复")


class AssistantCustomerSelectionView(APIView):
    """提交同名客户选择：重新校验归属后从中断节点继续。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int):
        serializer = CustomerSelectionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            from apps.ai.orchestration import service as orchestration

            result = orchestration.submit_customer_selection(
                request.user,
                task_id,
                serializer.validated_data["customer_id"],
            )
        except Exception as exc:  # noqa: BLE001
            return _orchestration_error_response(exc)
        return ApiResponse.ok(result, message="客户已确认")


def _batch_error_response(exc: Exception):
    """把批量补记领域错误转换为统一 API 响应。"""
    if isinstance(exc, services.TaskBusinessError):
        return _business_error_response(exc)
    return ApiResponse.error(str(exc), 400, data={"error_code": "batch_error"})


class BatchTaskDetailView(APIView):
    """多客户批量训练补记的任务概览。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, task_id: int):
        from apps.training import batch_service

        try:
            result = batch_service.get_batch_state(request.user, task_id)
        except ValueError as exc:
            return _batch_error_response(exc)
        return ApiResponse.ok(result, message="批量任务概览")


class BatchItemCustomerSearchView(APIView):
    """子项客户搜索：按客户姓名提示查询当前康复师名下客户。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int, item_id: int):
        from apps.training import batch_service

        try:
            candidates = batch_service.search_item_customer(request.user, task_id, item_id)
        except ValueError as exc:
            return _batch_error_response(exc)
        return ApiResponse.ok({"candidates": candidates}, message="客户查询成功")


class BatchItemCustomerSelectionView(APIView):
    """子项客户确认：确认后生成草稿进入等待草稿确认。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int, item_id: int):
        serializer = CustomerSelectionSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        from apps.training import batch_service

        try:
            item = batch_service.confirm_item_customer(
                request.user,
                task_id,
                item_id,
                serializer.validated_data["customer_id"],
            )
        except ValueError as exc:
            return _batch_error_response(exc)
        draft = item.ai_draft
        return ApiResponse.ok(
            {
                "item_id": item.id,
                "status": item.status,
                "draft_id": item.ai_draft_id,
                "customer_id": item.customer_id,
                "customer_name": item.customer.name if item.customer_id else "",
                "ai_result": draft.ai_result if draft else None,
            },
            message="客户已确认",
        )


class BatchItemDraftView(APIView):
    """子项草稿保存（自动保存，不写入正式记录）。"""

    permission_classes = [IsAuthenticated]

    def patch(self, request, task_id: int, item_id: int):
        from apps.training import batch_service

        try:
            draft = batch_service.update_item_draft(
                request.user,
                task_id,
                item_id,
                dict(request.data or {}),
            )
        except ValueError as exc:
            return _batch_error_response(exc)
        return ApiResponse.ok({"draft_id": draft.id, "ai_result": draft.ai_result}, message="草稿已保存")


class BatchItemConfirmView(APIView):
    """子项正式确认：创建正式训练记录并推进到下一子项。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int, item_id: int):
        from apps.training import batch_service

        confirmed = dict(request.data.get("confirmed", {}) if isinstance(request.data, dict) else {})
        idempotency_key = (
            request.data.get("idempotency_key", "")
            if isinstance(request.data, dict)
            else ""
        ) or request.headers.get("Idempotency-Key", "").strip()
        try:
            item = batch_service.confirm_item_record(
                request.user,
                task_id,
                item_id,
                confirmed,
                idempotency_key,
            )
        except ValueError as exc:
            return _batch_error_response(exc)
        summary = batch_service.build_batch_summary(request.user, task_id)
        # 当前客户保存后立即准备下一位客户的候选，前端无需回到概览卡再次
        # 点击“开始”。所有客户仍只按 sequence 严格逐项处理。
        next_payload = batch_service.prepare_current_item(request.user, task_id)
        next_item = next_payload.get("item")
        return ApiResponse.ok(
            {
                "item_id": item.id,
                "status": item.status,
                "training_record_id": item.training_record_id,
                "summary": summary,
                "next_item": (
                    {
                        "id": next_item.id,
                        "sequence": next_item.sequence,
                        "customer_name_hint": next_item.customer_name_hint,
                        "status": next_item.status,
                        "draft_id": next_item.ai_draft_id,
                    }
                    if next_item is not None
                    else None
                ),
                "next_candidates": next_payload.get("candidates", []),
            },
            message="已保存此客户并继续",
        )


class BatchItemSkipView(APIView):
    """跳过子项并推进到下一项。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, task_id: int, item_id: int):
        from apps.training import batch_service

        try:
            item = batch_service.skip_item(request.user, task_id, item_id)
        except ValueError as exc:
            return _batch_error_response(exc)
        summary = batch_service.build_batch_summary(request.user, task_id)
        next_payload = batch_service.prepare_current_item(request.user, task_id)
        next_item = next_payload.get("item")
        return ApiResponse.ok(
            {
                "item_id": item.id,
                "status": item.status,
                "summary": summary,
                "next_item": (
                    {
                        "id": next_item.id,
                        "sequence": next_item.sequence,
                        "customer_name_hint": next_item.customer_name_hint,
                        "status": next_item.status,
                        "draft_id": next_item.ai_draft_id,
                    }
                    if next_item is not None
                    else None
                ),
                "next_candidates": next_payload.get("candidates", []),
            },
            message="已跳过此项",
        )
