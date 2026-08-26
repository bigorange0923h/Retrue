"""followups：回访/复查模型的后台管理注册。"""

from django.contrib import admin

from apps.followups.models import FollowUpTask


@admin.register(FollowUpTask)
class FollowUpTaskAdmin(admin.ModelAdmin):
    """回访/复查后台管理。"""

    list_display = ("due_date", "customer", "followup_type", "status")
    list_filter = ("followup_type", "status")
    search_fields = ("customer__name", "content")
