"""common app 配置。"""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """公共工具模块配置，仅提供工具函数，不含数据模型。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "公共工具"
