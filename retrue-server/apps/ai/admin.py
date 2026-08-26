"""ai：AI 草稿模型的后台管理注册。"""

from django.contrib import admin

from apps.ai.models import AiDraft


@admin.register(AiDraft)
class AiDraftAdmin(admin.ModelAdmin):
    """AI 草稿后台管理。"""

    list_display = ("id", "therapist", "status", "customer", "created_at")
    list_filter = ("status",)
    search_fields = ("input_text", "therapist__username")
