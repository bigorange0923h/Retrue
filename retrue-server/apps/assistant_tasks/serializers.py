"""AssistantTask API 输入与输出序列化器。"""

from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers

from apps.assistant_tasks.models import AssistantRun, AssistantTask, TaskEvent, ToolExecution
from apps.customers.models import Customer
from apps.conversations.models import Conversation


class AssistantRunSerializer(serializers.ModelSerializer):
    """输出一次助手执行的状态和脱敏摘要。"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    run_number = serializers.IntegerField(source="attempt", read_only=True)

    class Meta:
        model = AssistantRun
        fields = [
            "id",
            "task",
            "client_request_id",
            "attempt",
            "run_number",
            "status",
            "status_display",
            "trigger_message",
            "provider",
            "model",
            "input_summary",
            "output_summary",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ToolExecutionSerializer(serializers.ModelSerializer):
    """输出工具调用状态、确认信息和脱敏摘要。"""

    task = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ToolExecution
        fields = [
            "id",
            "task",
            "run",
            "sequence",
            "tool_name",
            "status",
            "status_display",
            "input_summary",
            "output_summary",
            "is_write",
            "requires_confirmation",
            "confirmed_by",
            "confirmed_at",
            "result_resource_type",
            "result_resource_id",
            "error_code",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "task", "created_at", "updated_at"]

    def get_task(self, obj):
        """优先使用直接任务引用，缺失时从所属运行反查任务。"""
        return obj.task_id or getattr(obj.run, "task_id", None)


class TaskEventSerializer(serializers.ModelSerializer):
    """输出任务不可变事件。"""

    class Meta:
        model = TaskEvent
        fields = [
            "id",
            "task",
            "run",
            "actor",
            "event_type",
            "from_status",
            "to_status",
            "event_data",
            "created_at",
        ]
        read_only_fields = fields


class AssistantTaskSerializer(serializers.ModelSerializer):
    """助手任务创建输入及详情输出。

    客户端不能指定 therapist、任务状态、版本和生命周期时间；状态只能经
    service 状态机或取消接口变更。详情中的执行、工具和事件仅用于审阅。
    """

    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    conversation = serializers.PrimaryKeyRelatedField(
        queryset=Conversation.objects.all(), required=False, allow_null=True
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_resumable = serializers.BooleanField(read_only=True)
    runs = AssistantRunSerializer(many=True, read_only=True)
    tool_executions = serializers.SerializerMethodField()
    events = TaskEventSerializer(many=True, read_only=True)

    class Meta:
        model = AssistantTask
        fields = [
            "id",
            "customer",
            "customer_name",
            "conversation",
            "skill_code",
            "task_type",
            "invocation_mode",
            "origin",
            "context_resource_type",
            "context_resource_id",
            "business_key",
            "client_request_id",
            "status",
            "status_display",
            "current_step",
            "missing_fields",
            "state_data",
            "draft_resource_type",
            "draft_resource_id",
            "result_resource_type",
            "result_resource_id",
            "version",
            "is_resumable",
            "last_activity_at",
            "expires_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "runs",
            "tool_executions",
            "events",
        ]
        read_only_fields = [
            "id",
            "status",
            "status_display",
            "version",
            "is_resumable",
            "last_activity_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "runs",
            "tool_executions",
            "events",
            "draft_resource_type",
            "draft_resource_id",
            "result_resource_type",
            "result_resource_id",
            "expires_at",
        ]
        extra_kwargs = {
            "skill_code": {"required": False, "allow_blank": True},
            "task_type": {"required": False, "allow_blank": True},
            "invocation_mode": {"required": False, "allow_blank": True},
            "origin": {"required": False, "allow_blank": True},
            "context_resource_type": {"required": False, "allow_blank": True},
            "context_resource_id": {"required": False, "allow_blank": True},
            "business_key": {"required": False, "allow_blank": True},
            "client_request_id": {"required": False, "allow_blank": True},
            "current_step": {"required": False, "allow_blank": True},
            "missing_fields": {"required": False},
            "state_data": {"required": False},
            "draft_resource_type": {"required": False, "allow_blank": True},
            "draft_resource_id": {"required": False, "allow_blank": True},
            "result_resource_type": {"required": False, "allow_blank": True},
            "result_resource_id": {"required": False, "allow_blank": True},
            "expires_at": {"required": False, "allow_null": True},
        }

    def validate_missing_fields(self, value):
        """确保待补充字段以数组保存，方便客户端恢复任务。"""
        if not isinstance(value, list):
            raise serializers.ValidationError("missing_fields 必须是数组")
        return value

    def validate_state_data(self, value):
        """确保任务状态数据以对象保存，不接受任意标量。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("state_data 必须是对象")
        return value

    def get_tool_executions(self, obj):
        """返回任务直接关联或经执行记录反查到的全部工具调用。"""
        executions = (
            ToolExecution.objects.filter(Q(task=obj) | Q(run__task=obj))
            .select_related("task", "run", "confirmed_by")
            .order_by("run_id", "sequence", "id")
            .distinct()
        )
        return ToolExecutionSerializer(executions, many=True).data


class CancelTaskSerializer(serializers.Serializer):
    """取消任务请求输入。"""

    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, trim_whitespace=True)


class CustomerNameLookupSerializer(serializers.Serializer):
    """聊天上下文按姓名查询客户候选的请求参数。"""

    name = serializers.CharField(max_length=64, allow_blank=False, trim_whitespace=True)


class ToolExecuteSerializer(serializers.Serializer):
    """受控只读 Tool API 请求输入。

    ``tool_name`` 是服务端注册表中的精确名称；``arguments`` 必须是对象，
    具体字段白名单、日期范围和数量上限由 ``apps.assistant_tasks.tools``
    再次校验。客户端不能提交 Python 函数路径或康复师标识。
    """

    tool_name = serializers.CharField(required=False, allow_blank=False, max_length=128)
    # tool 是兼容短字段，同样会在 validate 中归一化为 tool_name。
    tool = serializers.CharField(required=False, allow_blank=False, max_length=128, write_only=True)
    arguments = serializers.JSONField(required=False, default=dict)
    client_request_id = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def validate(self, attrs):
        """校验工具名唯一且参数为 JSON 对象。"""
        tool_name = attrs.get("tool_name")
        short_name = attrs.get("tool")
        if tool_name and short_name and tool_name != short_name:
            raise serializers.ValidationError("tool_name 与 tool 不能同时指定不同工具")
        normalized_name = tool_name or short_name
        if not normalized_name:
            raise serializers.ValidationError("缺少 tool_name")
        arguments = attrs.get("arguments", {})
        if not isinstance(arguments, dict):
            raise serializers.ValidationError("arguments 必须是对象")
        attrs["tool_name"] = normalized_name
        attrs["arguments"] = arguments
        attrs.pop("tool", None)
        return attrs


# 便于内部调用方按“请求”语义导入；两个名称指向同一严格 serializer。
ToolExecutionRequestSerializer = ToolExecuteSerializer


class AssistantTurnSerializer(serializers.Serializer):
    """统一回合请求输入。

    接收当前会话、可选客户、业务入口和用户消息；客户端不能指定任务状态、
    图节点、模型意图或康复师标识。业务入口仍须由服务端复核资源归属和状态。
    """

    message = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)
    conversation_id = serializers.IntegerField(required=False, allow_null=True)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=64, trim_whitespace=True)
    client_request_id = serializers.CharField(required=False, allow_blank=True, max_length=128)
    entry_action = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        choices=("", "fill_course_training_record"),
    )
    course_session_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs):
        """课程标识只能与受支持的业务入口一起提交，避免伪造通用对话上下文。"""
        entry_action = attrs.get("entry_action", "")
        course_session_id = attrs.get("course_session_id")
        if entry_action == "fill_course_training_record" and course_session_id is None:
            raise serializers.ValidationError({"course_session_id": "课程回填入口必须指定具体排课"})
        if course_session_id is not None and entry_action != "fill_course_training_record":
            raise serializers.ValidationError({"entry_action": "指定排课时必须使用课程训练回填入口"})
        return attrs


class AssistantResumeSerializer(serializers.Serializer):
    """恢复未完成任务请求输入。"""

    message = serializers.CharField(required=False, allow_blank=True, max_length=4000, trim_whitespace=True)


class CustomerSelectionSerializer(serializers.Serializer):
    """提交同名客户选择请求输入。"""

    customer_id = serializers.IntegerField(min_value=1)
