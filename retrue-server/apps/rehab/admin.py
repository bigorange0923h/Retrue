"""rehab：康复计划与阶段模型的后台管理注册。"""

from django.contrib import admin

from apps.rehab.models import RehabPlan, RehabStage


class RehabStageInline(admin.TabularInline):
    """康复阶段内联管理。"""

    model = RehabStage
    extra = 0


@admin.register(RehabPlan)
class RehabPlanAdmin(admin.ModelAdmin):
    """康复计划后台管理。"""

    list_display = ("name", "customer", "status", "start_date")
    list_filter = ("status",)
    search_fields = ("customer__name",)
    inlines = [RehabStageInline]
