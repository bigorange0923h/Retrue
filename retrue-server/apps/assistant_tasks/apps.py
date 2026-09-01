"""AssistantTask 应用配置。"""

from django.apps import AppConfig


class AssistantTasksConfig(AppConfig):
    """统一助手任务应用配置。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant_tasks"
    verbose_name = "助手任务"
