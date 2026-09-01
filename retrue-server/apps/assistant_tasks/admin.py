"""AssistantTask 后台管理注册。"""

from django.contrib import admin

from apps.assistant_tasks.models import AssistantRun, AssistantTask, TaskEvent, ToolExecution


@admin.register(AssistantTask)
class AssistantTaskAdmin(admin.ModelAdmin):
    """助手任务后台列表配置。"""

    list_display = ("id", "therapist", "customer", "task_type", "status", "version", "updated_at")
    list_filter = ("status", "invocation_mode", "origin")
    search_fields = ("skill_code", "task_type", "business_key", "client_request_id")


@admin.register(AssistantRun)
class AssistantRunAdmin(admin.ModelAdmin):
    """助手执行后台列表配置。"""

    list_display = ("id", "task", "attempt", "status", "provider", "model", "created_at")
    list_filter = ("status", "provider")


@admin.register(ToolExecution)
class ToolExecutionAdmin(admin.ModelAdmin):
    """工具调用后台列表配置。"""

    list_display = ("id", "task", "run", "tool_name", "status", "is_write", "requires_confirmation")
    list_filter = ("status", "is_write", "requires_confirmation")


@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    """任务事件后台列表配置。"""

    list_display = ("id", "task", "event_type", "from_status", "to_status", "created_at")
    list_filter = ("event_type", "from_status", "to_status")
    readonly_fields = ("task", "run", "actor", "event_type", "from_status", "to_status", "event_data", "created_at")

