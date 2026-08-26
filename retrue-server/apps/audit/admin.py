"""audit：审计日志模型的后台管理注册。"""

from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """审计日志后台管理，只读展示，禁止直接编辑。"""

    list_display = ("action", "actor", "object_id", "reason", "created_at")
    list_filter = ("action",)
    search_fields = ("object_id", "reason", "actor__username")
    readonly_fields = [
        "actor",
        "action",
        "content_type",
        "object_id",
        "before_data",
        "after_data",
        "reason",
        "created_at",
    ]

    def has_add_permission(self, request) -> bool:
        """审计日志不允许手工新增。"""
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        """审计日志不允许修改。"""
        return False
