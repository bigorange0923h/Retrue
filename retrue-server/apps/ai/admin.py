"""ai：AI 草稿模型的后台管理注册。"""

from django.contrib import admin

from apps.ai.models import AiDraft, RiskAlert


@admin.register(AiDraft)
class AiDraftAdmin(admin.ModelAdmin):
    """AI 草稿后台管理。"""

    list_display = ("id", "therapist", "status", "customer", "created_at")
    list_filter = ("status",)
    search_fields = ("input_text", "therapist__username")


@admin.register(RiskAlert)
class RiskAlertAdmin(admin.ModelAdmin):
    """风险提醒后台管理。"""

    list_display = ("customer", "risk_level", "suggested_action", "is_confirmed", "created_at")
    list_filter = ("risk_level", "suggested_action", "is_confirmed")
    search_fields = ("customer__name", "evidence")
