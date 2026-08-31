"""统一 AI 会话应用配置。"""

from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    """注册 AI 会话业务域。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.conversations"
    verbose_name = "AI 会话"
