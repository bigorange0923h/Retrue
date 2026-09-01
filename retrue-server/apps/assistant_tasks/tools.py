"""统一助手的受控只读 Tool 注册与执行服务。

本模块是 AssistantTask 与客户业务数据之间的唯一只读工具边界。AI 或调用方
只能传入注册表中的精确工具名，不能根据任意字符串查找并调用 Python 函数。
每次调用都会创建一条 ``AssistantRun`` 和一条 ``ToolExecution``，日志字段仅
保存参数/结果的脱敏摘要；具体业务结果只在当前调用返回，不写入任务状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping

from django.db import IntegrityError
from django.db.models import Count, Max, Prefetch, Q
from django.utils import timezone

from apps.assistant_tasks import services
from apps.assistant_tasks.models import (
    AssistantRun,
    AssistantRunStatus,
    AssistantTask,
    ToolExecution,
    ToolExecutionStatus,
)


# Tool 输入上限是服务端约束，不由模型或客户端自行放宽。
DEFAULT_TOOL_LIMIT = 20
MAX_TOOL_LIMIT = 50
MAX_TOOL_DATE_RANGE_DAYS = 366
MAX_TOOL_TEXT_LENGTH = 80
MAX_TOOL_ARGUMENT_BYTES = 16 * 1024

# 兼容调用方可能使用的常量名称；值只有一个权威来源。
TOOL_DEFAULT_LIMIT = DEFAULT_TOOL_LIMIT
TOOL_MAX_LIMIT = MAX_TOOL_LIMIT
TOOL_MAX_DATE_RANGE_DAYS = MAX_TOOL_DATE_RANGE_DAYS


class ToolBusinessError(services.TaskBusinessError):
    """Tool 参数、权限或执行失败的可安全返回错误。"""

    code = "tool_invalid"


class ToolNotAllowedError(ToolBusinessError):
    """请求的工具不在服务端固定白名单中。"""

    code = "tool_not_allowed"


class ToolInputError(ToolBusinessError):
    """Tool 参数不符合服务端 schema 或数量/日期上限。"""

    code = "tool_input_invalid"


class ToolPermissionError(ToolBusinessError):
    """Tool 要访问的资源不属于任务康复师。"""

    code = "tool_forbidden"
    http_status = 403


class ToolContextMismatchError(ToolBusinessError):
    """请求客户/资源与任务客户上下文不一致。"""

    code = "tool_customer_mismatch"


class ToolExecutionFailedError(ToolBusinessError):
    """Tool 运行时发生不可安全暴露给调用方的错误。"""

    code = "tool_execution_failed"
    http_status = 500


@dataclass(frozen=True)
class ToolDefinition:
    """一个受控 Tool 的注册定义。

    参数：
        name: 仅允许通过注册表精确匹配的工具名。
        description: 面向编排器的工具用途说明。
        input_schema: 允许的输入字段及其约束描述；实际校验仍由服务端完成。
        handler: 已在本模块静态注册的处理器，不接受客户端传入函数名。
        read_only: 是否只读；写工具即使被内部注册，也不能经本执行入口调用。
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[["_ToolContext", dict[str, Any]], dict[str, Any]]
    read_only: bool = True

    @property
    def is_write(self) -> bool:
        """返回是否为写工具，供 API 层做二次拒绝。"""
        return not self.read_only

    @property
    def requires_confirmation(self) -> bool:
        """写工具默认需要康复师确认；只读工具不需要确认。"""
        return self.is_write


@dataclass
class _ToolContext:
    """一次执行的可信上下文，仅由任务数据库行派生。"""

    task: AssistantTask
    therapist_id: int
    customer_id: int | None


class ToolResult(dict):
    """兼容字典读取并携带执行日志对象的 Tool 返回值。

    ``ToolResult`` 仍是普通字典，内部 service 可直接读取业务结果；``run``
    和 ``tool_execution`` 仅用于 API 返回日志 ID，不会进入客户业务数据。
    """

    run: AssistantRun
    tool_execution: ToolExecution

    def __init__(
        self,
        value: Mapping[str, Any],
        *,
        run: AssistantRun,
        tool_execution: ToolExecution,
    ) -> None:
        super().__init__(value)
        self.run = run
        self.tool_execution = tool_execution


def _tool_schema(*, customer: bool = False, dates: bool = False, limit: bool = False) -> dict[str, Any]:
    """生成工具 schema 的公共字段，避免不同工具的上限描述漂移。"""
    properties: dict[str, Any] = {}
    if customer:
        properties["customer_id"] = {
            "type": "integer",
            "minimum": 1,
            "description": "可选客户 ID；省略时使用任务客户",
        }
    if dates:
        properties.update(
            {
                "from_date": {
                    "type": "string",
                    "format": "date",
                    "description": f"起始日期，范围最多 {MAX_TOOL_DATE_RANGE_DAYS} 天",
                },
                "to_date": {
                    "type": "string",
                    "format": "date",
                    "description": f"结束日期，范围最多 {MAX_TOOL_DATE_RANGE_DAYS} 天",
                },
            }
        )
    if limit:
        properties["limit"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TOOL_LIMIT,
            "default": DEFAULT_TOOL_LIMIT,
        }
    return {"type": "object", "properties": properties, "additionalProperties": False}


def _search_schema() -> dict[str, Any]:
    """返回客户搜索工具 schema。"""
    return {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "integer",
                "minimum": 1,
                "description": "可选客户 ID；任务已有客户时必须一致",
            },
            "keyword": {
                "type": "string",
                "maxLength": MAX_TOOL_TEXT_LENGTH,
                "description": "按客户姓名搜索；不会在执行日志保存原文",
            },
            # query 是明确登记的兼容字段，不是任意函数参数。
            "query": {
                "type": "string",
                "maxLength": MAX_TOOL_TEXT_LENGTH,
                "description": "keyword 的兼容名称",
            },
            "status": {
                "type": "string",
                "enum": ["active", "paused", "closed"],
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_TOOL_LIMIT,
                "default": DEFAULT_TOOL_LIMIT,
            },
        },
        "additionalProperties": False,
    }


def _session_schema() -> dict[str, Any]:
    """返回课程查询工具 schema。"""
    schema = _tool_schema(customer=True, dates=True, limit=True)
    schema["properties"].update(
        {
            "course_session_id": {"type": "integer", "minimum": 1},
            "start_date": {
                "type": "string",
                "format": "date",
                "description": "from_date 的兼容名称",
            },
            "end_date": {
                "type": "string",
                "format": "date",
                "description": "to_date 的兼容名称",
            },
        }
    )
    return schema


def _training_schema() -> dict[str, Any]:
    """返回训练记录查询工具 schema。"""
    schema = _tool_schema(customer=True, dates=True, limit=True)
    schema["properties"].update(
        {
            "days": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_TOOL_DATE_RANGE_DAYS,
                "description": "从今天向前查询的天数",
            },
            "training_record_id": {"type": "integer", "minimum": 1},
            "record_id": {
                "type": "integer",
                "minimum": 1,
                "description": "training_record_id 的兼容名称",
            },
        }
    )
    return schema


# 固定白名单。该映射是本模块唯一的函数分派入口；execute_tool 不使用 getattr、
# eval、importlib 或客户端传入的函数路径。
TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    "search_customers": ToolDefinition(
        name="search_customers",
        description="搜索当前任务康复师名下的客户，返回脱敏客户列表。",
        input_schema=_search_schema(),
        handler=lambda context, arguments: _search_customers(context, arguments),
    ),
    "get_customer_context": ToolDefinition(
        name="get_customer_context",
        description="读取任务客户的基础资料、首次评估状态和当前康复计划摘要。",
        input_schema=_tool_schema(customer=True),
        handler=lambda context, arguments: _get_customer_context(context, arguments),
    ),
    "list_customer_course_sessions": ToolDefinition(
        name="list_customer_course_sessions",
        description="读取任务客户的课程排期及单节课程状态。",
        input_schema=_session_schema(),
        handler=lambda context, arguments: _list_customer_course_sessions(context, arguments),
    ),
    "list_recent_training_records": ToolDefinition(
        name="list_recent_training_records",
        description="读取任务客户近期训练记录摘要。",
        input_schema=_training_schema(),
        handler=lambda context, arguments: _list_recent_training_records(context, arguments),
    ),
    "get_initial_assessment_status": ToolDefinition(
        name="get_initial_assessment_status",
        description="读取任务客户首次评估是否存在、完成状态和指标数量。",
        input_schema=_tool_schema(customer=True),
        handler=lambda context, arguments: _get_initial_assessment_status(context, arguments),
    ),
}

# 公开 allowlist 供编排器在生成 Tool schema 时使用；frozenset 避免调用方原地追加
# 任意函数名。注册表仍由服务端代码维护，客户端不能提交替代注册表。
TOOL_ALLOWLIST = frozenset(TOOL_DEFINITIONS)
READ_ONLY_TOOL_ALLOWLIST = frozenset(
    name for name, definition in TOOL_DEFINITIONS.items() if definition.read_only
)


def get_tool_definition(tool_name: str) -> ToolDefinition:
    """按精确工具名取得注册定义。

    参数：
        tool_name: 客户端或模型提出的工具名。
    返回：
        固定注册表中的 ToolDefinition。
    异常：
        ToolNotAllowedError: 工具名缺失、未知或不是字符串。
    """
    if not isinstance(tool_name, str) or tool_name not in TOOL_DEFINITIONS:
        raise ToolNotAllowedError("请求的工具不在允许列表中")
    return TOOL_DEFINITIONS[tool_name]


def list_tool_definitions() -> list[dict[str, Any]]:
    """返回可供模型编排使用的安全 Tool 描述，不暴露 Python 处理器。"""
    return [
        {
            "name": definition.name,
            "description": definition.description,
            "input_schema": definition.input_schema,
            "read_only": definition.read_only,
        }
        for definition in TOOL_DEFINITIONS.values()
    ]


def _positive_int(value: Any, field_name: str, *, maximum: int | None = None) -> int:
    """解析正整数并应用可选上限。"""
    if isinstance(value, bool):
        raise ToolInputError(f"{field_name} 必须是正整数", error_code="tool_parameter_invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolInputError(f"{field_name} 必须是正整数", error_code="tool_parameter_invalid") from exc
    if parsed < 1:
        raise ToolInputError(f"{field_name} 必须是正整数", error_code="tool_parameter_invalid")
    if maximum is not None and parsed > maximum:
        raise ToolInputError(
            f"{field_name} 不能超过 {maximum}",
            error_code="tool_parameter_limit_exceeded",
        )
    return parsed


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    """解析可空正整数。"""
    if value in (None, ""):
        return None
    return _positive_int(value, field_name)


def _parse_date(value: Any, field_name: str) -> date | None:
    """解析 ISO 日期，拒绝超长或带时间的字符串。"""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        raise ToolInputError(f"{field_name} 必须是 YYYY-MM-DD 日期", error_code="tool_date_invalid")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) > 10:
        raise ToolInputError(f"{field_name} 必须是 YYYY-MM-DD 日期", error_code="tool_date_invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ToolInputError(f"{field_name} 必须是 YYYY-MM-DD 日期", error_code="tool_date_invalid") from exc


def _date_window(
    arguments: Mapping[str, Any],
    *,
    allow_days: bool = False,
) -> tuple[date | None, date | None]:
    """解析日期范围并限制最大跨度。

    ``start_date/end_date`` 是已登记的兼容字段；一旦同时传入同义字段则拒绝，
    避免客户端以两个字段表达互相矛盾的查询条件。
    """
    from_value = arguments.get("from_date")
    start_value = arguments.get("start_date")
    to_value = arguments.get("to_date")
    end_value = arguments.get("end_date")
    if from_value not in (None, "") and start_value not in (None, ""):
        raise ToolInputError("from_date 与 start_date 不能同时提供", error_code="tool_date_invalid")
    if to_value not in (None, "") and end_value not in (None, ""):
        raise ToolInputError("to_date 与 end_date 不能同时提供", error_code="tool_date_invalid")
    from_date = _parse_date(from_value if from_value not in (None, "") else start_value, "from_date")
    to_date = _parse_date(to_value if to_value not in (None, "") else end_value, "to_date")

    days_value = arguments.get("days")
    if days_value not in (None, ""):
        if not allow_days:
            raise ToolInputError("当前工具不支持 days 参数", error_code="tool_parameter_not_allowed")
        if from_date is not None or to_date is not None:
            raise ToolInputError("days 不能与日期范围同时提供", error_code="tool_date_invalid")
        days = _positive_int(days_value, "days", maximum=MAX_TOOL_DATE_RANGE_DAYS)
        to_date = timezone.localdate()
        from_date = to_date - timedelta(days=days - 1)

    if from_date is None and to_date is None:
        return None, None
    if from_date is None:
        from_date = to_date - timedelta(days=MAX_TOOL_DATE_RANGE_DAYS)
    if to_date is None:
        to_date = timezone.localdate()
    if from_date > to_date:
        raise ToolInputError("起始日期不能晚于结束日期", error_code="tool_date_invalid")
    if (to_date - from_date).days > MAX_TOOL_DATE_RANGE_DAYS:
        raise ToolInputError(
            f"日期范围不能超过 {MAX_TOOL_DATE_RANGE_DAYS} 天",
            error_code="tool_parameter_limit_exceeded",
        )
    return from_date, to_date


def _limit(arguments: Mapping[str, Any]) -> int:
    """解析所有列表 Tool 共用的 limit。"""
    return _positive_int(
        arguments.get("limit", DEFAULT_TOOL_LIMIT),
        "limit",
        maximum=MAX_TOOL_LIMIT,
    )


def _validate_arguments(definition: ToolDefinition, arguments: Any) -> dict[str, Any]:
    """校验参数对象、字段白名单和总长度，不保留参数原文。"""
    if arguments is None:
        normalized: dict[str, Any] = {}
    elif isinstance(arguments, Mapping):
        normalized = dict(arguments)
    else:
        raise ToolInputError("工具 arguments 必须是对象", error_code="tool_arguments_invalid")
    allowed = set(definition.input_schema.get("properties", {}))
    unknown = sorted(set(normalized) - allowed)
    if unknown:
        raise ToolInputError(
            "工具包含未允许的参数",
            error_code="tool_parameter_not_allowed",
        )
    # 仅用于拒绝异常大请求；不把序列化后的内容写入日志。
    try:
        encoded_length = len(repr(normalized).encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ToolInputError("工具参数编码无效", error_code="tool_arguments_invalid") from exc
    if encoded_length > MAX_TOOL_ARGUMENT_BYTES:
        raise ToolInputError(
            f"工具参数不能超过 {MAX_TOOL_ARGUMENT_BYTES} 字节",
            error_code="tool_parameter_limit_exceeded",
        )
    return normalized


def _resolve_customer(context: _ToolContext, arguments: Mapping[str, Any], *, required: bool = True):
    """解析客户并确保客户属于任务康复师及任务客户上下文。"""
    from apps.customers.models import Customer

    requested_id = _optional_positive_int(arguments.get("customer_id"), "customer_id")
    if context.customer_id is not None:
        if requested_id is not None and requested_id != context.customer_id:
            raise ToolContextMismatchError("请求客户与任务客户不一致")
        requested_id = context.customer_id
    if requested_id is None:
        if required:
            raise ToolInputError("工具需要客户上下文", error_code="tool_customer_required")
        return None
    customer = Customer.objects.filter(id=requested_id, therapist_id=context.therapist_id).first()
    if customer is None:
        # 不区分不存在和其他康复师拥有，防止枚举数据；业务上统一按无权处理。
        raise ToolPermissionError("客户不存在或无权访问", error_code="customer_forbidden")
    return customer


def _check_optional_resource(
    context: _ToolContext,
    *,
    resource_type: str,
    resource_id: Any,
    customer_id: int,
) -> Any:
    """校验工具参数中的业务资源和任务上下文。"""
    resource_pk = _optional_positive_int(resource_id, f"{resource_type}_id")
    if resource_pk is None:
        return None
    # 任务若绑定同类资源，工具不能静默切换到另一资源；其他类型资源仍可查询
    # 同一客户的只读上下文，但都会通过 customer_id 归属校验。
    task_resource_type = str(getattr(context.task, "context_resource_type", "") or "").strip().lower()
    task_resource_id = str(getattr(context.task, "context_resource_id", "") or "").strip()
    canonical_task_type = services.RESOURCE_TYPE_ALIASES.get(task_resource_type, task_resource_type)
    if canonical_task_type == resource_type and task_resource_id and task_resource_id != str(resource_pk):
        raise ToolContextMismatchError("请求资源与任务资源不一致", error_code="tool_resource_mismatch")
    try:
        return services.validate_resource_ownership(
            context.therapist_id,
            resource_type,
            resource_pk,
            customer_id,
        )
    except services.ResourceOwnershipError as exc:
        raise ToolPermissionError("资源不存在或无权访问", error_code="resource_forbidden") from exc
    except services.ResourceValidationError as exc:
        if exc.code == "resource_customer_mismatch":
            raise ToolContextMismatchError(str(exc), error_code="tool_customer_mismatch") from exc
        raise ToolInputError(str(exc), error_code=exc.code) from exc


def _task_context(task: AssistantTask) -> _ToolContext:
    """从数据库任务行派生可信康复师和客户上下文。"""
    task_id = getattr(task, "pk", None)
    if task_id is None:
        raise ToolPermissionError("助手任务无效", error_code="task_invalid")
    therapist_id = getattr(task, "therapist_id", None)
    try:
        therapist_id = int(therapist_id)
    except (TypeError, ValueError) as exc:
        raise ToolPermissionError("助手任务康复师无效", error_code="therapist_invalid") from exc

    # 重新读取任务，避免调用方传入已被其他请求修改的陈旧关系对象；康复师仍
    # 只从 task 的持久化 therapist_id 派生，绝不接受 execute_tool 的外部 therapist。
    persisted = (
        AssistantTask.objects.filter(pk=task_id, therapist_id=therapist_id)
        .select_related("customer")
        .first()
    )
    if persisted is None:
        raise ToolPermissionError("助手任务不存在或无权访问", error_code="task_forbidden")

    bound_customer_id = persisted.customer_id
    if bound_customer_id is not None:
        from apps.customers.models import Customer

        customer_exists = Customer.objects.filter(
            id=bound_customer_id,
            therapist_id=therapist_id,
        ).exists()
        if not customer_exists:
            raise ToolPermissionError("任务客户不存在或无权访问", error_code="customer_forbidden")

    # 任务上下文资源也必须每次执行时复核，防止无物理外键的数据漂移或恶意
    # 直接构造任务绕过领域 service。
    context_type = str(persisted.context_resource_type or "").strip()
    context_id = str(persisted.context_resource_id or "").strip()
    if bool(context_type) != bool(context_id):
        raise ToolInputError("任务上下文资源引用不完整", error_code="resource_reference_incomplete")
    if context_type and context_id:
        try:
            resource = services.validate_resource_ownership(
                therapist_id,
                context_type,
                context_id,
                bound_customer_id,
            )
        except services.ResourceOwnershipError:
            raise
        except services.ResourceValidationError:
            raise
        if bound_customer_id is None:
            canonical_type = services.RESOURCE_TYPE_ALIASES.get(context_type.lower(), context_type.lower())
            if canonical_type == "customer":
                bound_customer_id = getattr(resource, "id", None)
            else:
                bound_customer_id = getattr(resource, "customer_id", None)
            if bound_customer_id is not None:
                from apps.customers.models import Customer

                if not Customer.objects.filter(
                    id=bound_customer_id,
                    therapist_id=therapist_id,
                ).exists():
                    raise ToolPermissionError("任务资源客户不存在或无权访问", error_code="customer_forbidden")

    # 返回数据库对象而非调用方对象，保证后续资源约束全部基于同一任务行。
    return _ToolContext(
        task=persisted,
        therapist_id=therapist_id,
        customer_id=int(bound_customer_id) if bound_customer_id is not None else None,
    )


def _safe_text(value: Any, *, maximum: int = 1000) -> str:
    """截断业务文本，避免 Tool 结果或日志携带无界原文。"""
    text = str(value or "")
    if len(text) <= maximum:
        return text
    return text[:maximum] + "…"


def _customer_to_result(customer: Any) -> dict[str, Any]:
    """将客户转为工具可见的脱敏资料。"""
    from apps.customers.models import mask_phone

    masked_phone = mask_phone(customer.phone)
    if not masked_phone and "****" in str(customer.phone_masked or ""):
        # 仅接受已经包含掩码的历史值，杜绝把异常的完整号码透传给 Tool。
        masked_phone = str(customer.phone_masked)
    return {
        "id": customer.id,
        "name": _safe_text(customer.name, maximum=64),
        "phone_masked": masked_phone,
        "gender": customer.gender,
        "status": customer.status,
        "status_display": customer.get_status_display(),
        "main_issue": _safe_text(customer.main_issue, maximum=255),
        "first_visit_date": customer.first_visit_date.isoformat() if customer.first_visit_date else None,
    }


def lookup_current_therapist_customers_by_name(therapist: Any, name: str) -> list[dict[str, Any]]:
    """按精确姓名返回当前康复师名下客户候选，用于聊天前确认同名客户。

    这是手工选择上下文的只读 Tool 接口，不依赖已有任务，因此聊天尚未绑定
    客户时也可以安全调用。返回值仅含列表场景允许展示的脱敏资料。
    """
    from apps.customers.models import Customer

    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ToolInputError("客户姓名不能为空", error_code="customer_name_required")
    if len(normalized_name) > 64:
        raise ToolInputError("客户姓名不能超过 64 个字符", error_code="customer_name_too_long")
    therapist_id = services._owner_id(therapist)
    customers = Customer.objects.filter(
        therapist_id=therapist_id,
        name=normalized_name,
    ).order_by("status", "id")[:MAX_TOOL_LIMIT]
    return [_customer_to_result(customer) for customer in customers]


def _initial_assessment_summary(assessment: Any | None) -> dict[str, Any]:
    """生成首次评估状态摘要，不返回病史或整段主诉原文。"""
    if assessment is None:
        return {
            "exists": False,
            "assessment_id": None,
            "status": "missing",
            "assessment_date": None,
            "completed_at": None,
            "metric_count": 0,
        }
    metric_count = getattr(assessment, "metric_count", None)
    if metric_count is None:
        metric_count = assessment.metrics.count()
    return {
        "exists": True,
        "assessment_id": assessment.id,
        "status": assessment.status,
        "status_display": assessment.get_status_display(),
        "assessment_date": assessment.assessment_date.isoformat() if assessment.assessment_date else None,
        "completed_at": assessment.completed_at.isoformat() if assessment.completed_at else None,
        "metric_count": metric_count,
    }


def _search_customers(context: _ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """执行当前康复师范围内的客户搜索。"""
    from apps.customers.models import Customer

    # 未绑定客户的任务可用于客户选择；已有客户的任务只能继续查看该客户，
    # 防止把一个客户的上下文扩展为同一康复师的全部客户。
    customer = _resolve_customer(context, arguments, required=False)
    keyword = arguments.get("keyword")
    query = arguments.get("query")
    if keyword not in (None, "") and query not in (None, ""):
        raise ToolInputError("keyword 与 query 不能同时提供", error_code="tool_parameter_invalid")
    keyword = keyword if keyword not in (None, "") else query
    if keyword is not None:
        if not isinstance(keyword, str) or len(keyword) > MAX_TOOL_TEXT_LENGTH:
            raise ToolInputError(
                f"keyword 不能超过 {MAX_TOOL_TEXT_LENGTH} 个字符",
                error_code="tool_parameter_limit_exceeded",
            )
        keyword = keyword.strip()
    status = arguments.get("status", "")
    if status not in ("", None, "active", "paused", "closed"):
        raise ToolInputError("status 参数无效", error_code="tool_parameter_invalid")
    limit = _limit(arguments)
    queryset = Customer.objects.filter(therapist_id=context.therapist_id)
    if customer is not None:
        queryset = queryset.filter(id=customer.id)
    if keyword:
        # 搜索手机号时只按脱敏值/后四位匹配，不在结果和日志暴露完整号码。
        keyword_query = Q(name__icontains=keyword)
        if keyword.isdigit():
            keyword_query |= Q(phone_masked__icontains=keyword)
            keyword_query |= Q(phone__endswith=keyword[-4:])
        queryset = queryset.filter(keyword_query)
    if status:
        queryset = queryset.filter(status=status)
    total = queryset.count()
    customers = queryset.order_by("name", "id")[:limit]
    return {
        "items": [_customer_to_result(customer) for customer in customers],
        "total": total,
        "limit": limit,
    }


def _get_customer_context(context: _ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """读取客户基础资料、首次评估和当前计划摘要。"""
    from apps.assessments.models import Assessment, AssessmentType
    from apps.customers.models import Customer
    from apps.rehab.models import RehabPlan, RehabStage
    from apps.training.models import TrainingRecord

    customer = _resolve_customer(context, arguments)
    initial = (
        Assessment.objects.filter(
            therapist_id=context.therapist_id,
            customer_id=customer.id,
            assessment_type=AssessmentType.INITIAL,
        )
        .annotate(metric_count=Count("metrics"))
        .order_by("assessment_date", "created_at", "id")
        .first()
    )
    active_plan = (
        RehabPlan.objects.filter(
            therapist_id=context.therapist_id,
            customer_id=customer.id,
            status="active",
        )
        .order_by("-created_at", "-id")
        .first()
    )
    plan_result: dict[str, Any] | None = None
    stage_result: dict[str, Any] | None = None
    if active_plan is not None:
        plan_result = {
            "id": active_plan.id,
            "name": _safe_text(active_plan.name, maximum=128),
            "start_date": active_plan.start_date.isoformat() if active_plan.start_date else None,
            "end_date": active_plan.end_date.isoformat() if active_plan.end_date else None,
            "status": active_plan.status,
            "goals": _safe_text(active_plan.goals, maximum=500),
        }
        current_stage = (
            RehabStage.objects.filter(plan_id=active_plan.id, end_date__isnull=True)
            .order_by("-start_date", "-id")
            .first()
        )
        if current_stage is not None:
            stage_result = {
                "id": current_stage.id,
                "stage_type": current_stage.stage_type,
                "stage_type_display": current_stage.get_stage_type_display(),
                "start_date": current_stage.start_date.isoformat(),
                "note": _safe_text(current_stage.note, maximum=300),
            }

    return {
        "customer_id": customer.id,
        "customer": _customer_to_result(customer),
        "initial_assessment": _initial_assessment_summary(initial),
        "active_plan": plan_result,
        "current_stage": stage_result,
        "recent_training_count": TrainingRecord.objects.filter(
            therapist_id=context.therapist_id,
            customer_id=customer.id,
        ).count(),
    }


def _list_customer_course_sessions(context: _ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """查询当前康复师客户的课程排期。"""
    from apps.schedules.models import CourseSession
    from apps.training.models import TrainingRecord

    customer = _resolve_customer(context, arguments)
    from_date, to_date = _date_window(arguments)
    limit = _limit(arguments)
    course_session = _check_optional_resource(
        context,
        resource_type="course_session",
        resource_id=arguments.get("course_session_id"),
        customer_id=customer.id,
    )
    queryset = (
        CourseSession.objects.filter(
            therapist_id=context.therapist_id,
            customer_id=customer.id,
        )
        .select_related("plan_course__course_type", "plan_course__rehab_plan")
        .prefetch_related(
            Prefetch(
                "training_records",
                queryset=TrainingRecord.objects.filter(
                    therapist_id=context.therapist_id,
                    customer_id=customer.id,
                ).only("id", "course_session_id"),
                to_attr="_tool_training_records",
            )
        )
    )
    if course_session is not None:
        queryset = queryset.filter(id=course_session.id)
    if from_date is not None:
        queryset = queryset.filter(date__gte=from_date)
    if to_date is not None:
        queryset = queryset.filter(date__lte=to_date)
    total = queryset.count()
    sessions = queryset.order_by("date", "start_time", "id")[:limit]
    items: list[dict[str, Any]] = []
    for session in sessions:
        plan_course = getattr(session, "plan_course", None)
        training_records = getattr(session, "_tool_training_records", [])
        items.append(
            {
                "id": session.id,
                "customer_id": session.customer_id,
                "date": session.date.isoformat(),
                "start_time": session.start_time.isoformat() if session.start_time else None,
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "status": session.status,
                "status_display": session.get_status_display(),
                "arrangement_type": session.arrangement_type,
                "arrangement_type_display": session.get_arrangement_type_display(),
                "session_topic": _safe_text(session.session_topic, maximum=128),
                "session_count": str(session.session_count) if session.session_count is not None else None,
                "session_consumed": session.session_consumed,
                "plan_course_id": session.plan_course_id,
                "plan_course_name": (
                    _safe_text(plan_course.course_type.name, maximum=128)
                    if plan_course is not None and getattr(plan_course, "course_type", None) is not None
                    else None
                ),
                "rehab_plan_name": (
                    _safe_text(plan_course.rehab_plan.name, maximum=128)
                    if plan_course is not None and getattr(plan_course, "rehab_plan", None) is not None
                    else None
                ),
                "training_record_id": training_records[0].id if training_records else None,
            }
        )
    return {"customer_id": customer.id, "items": items, "total": total, "limit": limit}


def _training_record_to_result(record: Any) -> dict[str, Any]:
    """将训练记录转换为有限长度的上下文结果。"""
    course_session = getattr(record, "course_session", None)
    return {
        "id": record.id,
        "customer_id": record.customer_id,
        "course_session_id": record.course_session_id,
        "course_date": course_session.date.isoformat() if course_session is not None else None,
        "training_date": record.training_date.isoformat() if record.training_date else None,
        "customer_feedback": _safe_text(record.customer_feedback),
        "therapist_observation": _safe_text(record.therapist_observation),
        "next_plan": _safe_text(record.next_plan),
        "note": _safe_text(record.note),
        "exercises": [
            {
                "id": exercise.id,
                "exercise_name": _safe_text(exercise.exercise_name, maximum=128),
                "sets": exercise.sets,
                "reps": exercise.reps,
                "weight": _safe_text(exercise.weight, maximum=32),
                "duration_seconds": exercise.duration_seconds,
            }
            for exercise in record.exercises.all()[:MAX_TOOL_LIMIT]
        ],
    }


def _list_recent_training_records(context: _ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """查询当前康复师客户近期训练记录。"""
    from apps.training.models import TrainingRecord

    customer = _resolve_customer(context, arguments)
    from_date, to_date = _date_window(arguments, allow_days=True)
    limit = _limit(arguments)
    record_id = arguments.get("training_record_id")
    legacy_record_id = arguments.get("record_id")
    if record_id not in (None, "") and legacy_record_id not in (None, ""):
        raise ToolInputError(
            "training_record_id 与 record_id 不能同时提供",
            error_code="tool_parameter_invalid",
        )
    record_id = record_id if record_id not in (None, "") else legacy_record_id
    selected_record = _check_optional_resource(
        context,
        resource_type="training_record",
        resource_id=record_id,
        customer_id=customer.id,
    )
    queryset = (
        TrainingRecord.objects.filter(
            therapist_id=context.therapist_id,
            customer_id=customer.id,
        )
        .select_related("course_session")
        .prefetch_related("exercises")
    )
    if selected_record is not None:
        queryset = queryset.filter(id=selected_record.id)
    if from_date is not None:
        queryset = queryset.filter(training_date__gte=from_date)
    if to_date is not None:
        queryset = queryset.filter(training_date__lte=to_date)
    total = queryset.count()
    records = queryset.order_by("-training_date", "-created_at", "-id")[:limit]
    return {
        "customer_id": customer.id,
        "items": [_training_record_to_result(record) for record in records],
        "total": total,
        "limit": limit,
    }


def _get_initial_assessment_status(context: _ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """查询当前康复师客户的首次评估状态。"""
    from apps.assessments.models import Assessment, AssessmentType

    customer = _resolve_customer(context, arguments)
    assessment = (
        Assessment.objects.filter(
            therapist_id=context.therapist_id,
            customer_id=customer.id,
            assessment_type=AssessmentType.INITIAL,
        )
        .annotate(metric_count=Count("metrics"))
        .order_by("assessment_date", "created_at", "id")
        .first()
    )
    summary = _initial_assessment_summary(assessment)
    return {
        "customer_id": customer.id,
        "exists": summary["exists"],
        "has_initial_assessment": summary["exists"],
        "assessment": summary if summary["exists"] else None,
        # 保留常用扁平字段，便于编排器无需猜测嵌套结构。
        "assessment_id": summary["assessment_id"],
        "status": summary["status"],
        "assessment_date": summary["assessment_date"],
        "completed_at": summary["completed_at"],
        "metric_count": summary["metric_count"],
    }


def _input_summary(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """生成不含参数原文的执行输入摘要。"""
    summary: dict[str, Any] = {
        "tool_name": tool_name,
        "argument_keys": sorted(str(key) for key in arguments.keys()),
    }
    for field in ("customer_id", "course_session_id", "training_record_id", "record_id", "limit", "days"):
        value = arguments.get(field)
        if value not in (None, ""):
            try:
                summary[field] = int(value)
            except (TypeError, ValueError):
                summary[f"{field}_provided"] = True
    for field in ("from_date", "to_date", "start_date", "end_date"):
        value = arguments.get(field)
        if value not in (None, ""):
            parsed = _parse_date(value, field)
            summary[field] = parsed.isoformat() if parsed else None
    for field in ("keyword", "query"):
        value = arguments.get(field)
        if value not in (None, ""):
            # 只保留长度和是否存在，手机号/姓名/病史原文不进入日志。
            summary[f"{field}_length"] = len(str(value))
            summary[f"{field}_provided"] = True
    return summary


def _output_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """生成不含手机号、病史和原始文本的执行输出摘要。"""
    summary: dict[str, Any] = {"result_type": "object"}
    for key in (
        "customer_id",
        "total",
        "limit",
        "assessment_id",
        "status",
        "exists",
        "has_initial_assessment",
        "metric_count",
        "recent_training_count",
    ):
        value = result.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
    items = result.get("items")
    if isinstance(items, (list, tuple)):
        summary["item_count"] = len(items)
        summary["count"] = len(items)
        summary["item_ids"] = [item.get("id") for item in items if isinstance(item, Mapping) and item.get("id")]
    assessment = result.get("assessment")
    if isinstance(assessment, Mapping):
        summary["assessment_id"] = assessment.get("assessment_id")
        summary["status"] = assessment.get("status")
    return summary


def _safe_tool_error(exc: Exception) -> tuple[str, str, int]:
    """将预期错误压缩为可持久化的错误代码、短消息和 HTTP 码。"""
    if isinstance(exc, services.TaskBusinessError):
        return str(getattr(exc, "code", "tool_invalid"))[:64], str(exc)[:500], exc.http_status
    return "tool_execution_failed", "工具执行失败", 500


def _start_execution(
    task: AssistantTask,
    definition: ToolDefinition,
    input_summary: dict[str, Any],
    *,
    client_request_id: str = "",
    run: AssistantRun | None = None,
    sequence: int | None = None,
) -> tuple[AssistantRun, ToolExecution]:
    """创建运行与工具记录，状态先置为 running。"""
    task_id = getattr(task, "pk", None)
    if task_id is None:
        raise ToolPermissionError("助手任务无效", error_code="task_invalid")
    if run is not None:
        if run.task_id != task_id:
            raise ToolPermissionError("执行记录与任务不一致", error_code="run_task_mismatch")
        run_instance = run
        if sequence is None:
            sequence = (
                ToolExecution.objects.filter(run_id=run.pk).aggregate(max_sequence=Max("sequence"))["max_sequence"]
                or -1
            ) + 1
    else:
        attempt = (
            AssistantRun.objects.filter(task_id=task_id).aggregate(max_attempt=Max("attempt"))["max_attempt"]
            or 0
        ) + 1
        now = timezone.now()
        try:
            run_instance = AssistantRun.objects.create(
                task_id=task_id,
                client_request_id=str(client_request_id or "").strip()[:128],
                attempt=attempt,
                status=AssistantRunStatus.RUNNING,
                started_at=now,
                input_summary=input_summary,
            )
        except IntegrityError:
            # 同一请求号重试时复用已有运行；结果摘要仍不包含业务原文。
            request_id = str(client_request_id or "").strip()
            if not request_id:
                raise
            run_instance = AssistantRun.objects.filter(
                task_id=task_id,
                client_request_id=request_id[:128],
            ).first()
            if run_instance is None:
                raise
            if run_instance.status == AssistantRunStatus.SUCCEEDED:
                raise ToolBusinessError("该工具请求已执行，请使用原执行结果", error_code="tool_request_replayed")
            run_instance.status = AssistantRunStatus.RUNNING
            run_instance.started_at = run_instance.started_at or timezone.now()
            run_instance.input_summary = input_summary
            run_instance.save(update_fields=["status", "started_at", "input_summary", "updated_at"])
        sequence = 0 if sequence is None else sequence
    now = timezone.now()
    execution = ToolExecution.objects.create(
        run=run_instance,
        task_id=task_id,
        sequence=sequence or 0,
        tool_name=definition.name,
        status=ToolExecutionStatus.RUNNING,
        input_summary=input_summary,
        is_write=definition.is_write,
        requires_confirmation=definition.requires_confirmation,
        started_at=now,
    )
    return run_instance, execution


def _finish_execution(
    run: AssistantRun,
    execution: ToolExecution,
    *,
    result: Mapping[str, Any] | None = None,
    error: Exception | None = None,
) -> None:
    """将 Tool 与 Run 更新为成功/失败并只写输出摘要。"""
    now = timezone.now()
    output_summary = _output_summary(result or {}) if error is None else {}
    if error is None:
        execution.status = ToolExecutionStatus.SUCCEEDED
        run.status = AssistantRunStatus.SUCCEEDED
        error_code = ""
        error_message = ""
    else:
        error_code, error_message, _status = _safe_tool_error(error)
        execution.status = ToolExecutionStatus.FAILED
        run.status = AssistantRunStatus.FAILED
    execution.output_summary = output_summary
    execution.error_code = error_code
    execution.error_message = error_message
    execution.finished_at = now
    execution.save(
        update_fields=[
            "status",
            "output_summary",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )
    run.output_summary = output_summary
    run.error_code = error_code
    run.error_message = error_message
    run.finished_at = now
    run.save(
        update_fields=[
            "status",
            "output_summary",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )


def execute_tool(
    task: AssistantTask,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
    *,
    client_request_id: str = "",
    run: AssistantRun | None = None,
    sequence: int | None = None,
) -> ToolResult:
    """执行一个固定白名单中的 Tool，并记录脱敏运行日志。

    参数：
        task: 已由调用方取得的助手任务；康复师从 ``task.therapist_id`` 派生。
        tool_name: 必须是 ``TOOL_ALLOWLIST`` 中的精确名称。
        arguments: 受 schema 限制的工具参数对象。
        client_request_id: 可选的本次执行幂等键。
        run/sequence: 内部编排器复用同一 Run 时使用，普通调用无需提供。
    返回：
        可按字典读取的 ToolResult，并附带 ``run``/``tool_execution`` 日志对象。
    异常：
        ToolBusinessError: 白名单、权限、客户上下文、参数或执行错误。
    """
    definition: ToolDefinition | None = None
    try:
        definition = get_tool_definition(tool_name)
    except ToolBusinessError as exc:
        # 未知工具也尽力留痕，但绝不把客户端未知函数名当作可调用目标。
        try:
            raw_summary = {
                "tool_name": str(tool_name)[:128],
                "argument_keys": sorted(str(key) for key in arguments.keys())
                if isinstance(arguments, Mapping)
                else [],
            }
            unknown_definition = ToolDefinition(
                name=str(tool_name)[:128] or "unknown",
                description="未知工具（仅用于失败日志）",
                input_schema={"type": "object", "properties": {}},
                handler=lambda _context, _arguments: {},
                read_only=True,
            )
            log_task = getattr(task, "pk", None)
            if log_task is not None:
                run_instance, execution = _start_execution(
                    task,
                    unknown_definition,
                    raw_summary,
                    client_request_id=client_request_id,
                    run=run,
                    sequence=sequence,
                )
                _finish_execution(run_instance, execution, error=exc)
        except Exception:
            # 原始白名单错误优先返回；日志失败不能将未知函数变成成功。
            pass
        raise

    try:
        normalized_arguments = _validate_arguments(definition, arguments)
        input_summary = _input_summary(definition.name, normalized_arguments)
    except ToolBusinessError as exc:
        # 参数错误尚未有上下文，但仍需为有效任务创建失败日志。
        try:
            raw_arguments = arguments if isinstance(arguments, Mapping) else {}
            fallback_summary = {
                "tool_name": definition.name,
                "argument_keys": sorted(str(key) for key in raw_arguments.keys()),
            }
            run_instance, execution = _start_execution(
                task,
                definition,
                fallback_summary,
                client_request_id=client_request_id,
                run=run,
                sequence=sequence,
            )
            _finish_execution(run_instance, execution, error=exc)
        except Exception:
            pass
        raise

    run_instance, execution = _start_execution(
        task,
        definition,
        input_summary,
        client_request_id=client_request_id,
        run=run,
        sequence=sequence,
    )

    if not definition.read_only:
        error = ToolNotAllowedError("写工具不能通过只读执行入口调用", error_code="tool_write_not_allowed")
        _finish_execution(run_instance, execution, error=error)
        raise error

    try:
        context = _task_context(task)
        result = definition.handler(context, normalized_arguments)
        if not isinstance(result, Mapping):
            raise ToolExecutionFailedError("工具返回格式无效")
    except ToolBusinessError as exc:
        _finish_execution(run_instance, execution, error=exc)
        raise
    except Exception as exc:  # pragma: no cover - 具体业务查询错误由上层异常覆盖
        _finish_execution(run_instance, execution, error=exc)
        raise ToolExecutionFailedError("工具执行失败") from exc

    _finish_execution(run_instance, execution, result=result)
    return ToolResult(result, run=run_instance, tool_execution=execution)


def execute_read_only_tool(
    task: AssistantTask,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> ToolResult:
    """只读 Tool 的语义化内部 service 入口。"""
    return execute_tool(task, tool_name, arguments, **kwargs)


def run_tool(
    task: AssistantTask,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> ToolResult:
    """兼容编排器的 Tool 执行别名，仍使用同一固定白名单。"""
    return execute_tool(task, tool_name, arguments, **kwargs)


__all__ = [
    "DEFAULT_TOOL_LIMIT",
    "MAX_TOOL_LIMIT",
    "MAX_TOOL_DATE_RANGE_DAYS",
    "ToolDefinition",
    "ToolBusinessError",
    "ToolNotAllowedError",
    "ToolInputError",
    "ToolPermissionError",
    "ToolContextMismatchError",
    "ToolExecutionFailedError",
    "ToolResult",
    "TOOL_DEFINITIONS",
    "TOOL_ALLOWLIST",
    "READ_ONLY_TOOL_ALLOWLIST",
    "get_tool_definition",
    "list_tool_definitions",
    "execute_tool",
    "execute_read_only_tool",
    "lookup_current_therapist_customers_by_name",
    "run_tool",
]
