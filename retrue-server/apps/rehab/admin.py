"""rehab：康复计划与阶段模型的后台管理注册。"""

from django.contrib import admin

from apps.rehab.models import RehabPlan, RehabPlanTemplate, RehabPlanTemplateCourse, RehabStage


class RehabPlanTemplateCourseInline(admin.TabularInline):
    """课程计划模板课程组成的内联管理。"""

    model = RehabPlanTemplateCourse
    extra = 0


@admin.register(RehabPlanTemplate)
class RehabPlanTemplateAdmin(admin.ModelAdmin):
    """课程计划模板后台管理。"""

    list_display = ("name", "therapist", "suggested_duration_weeks", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "therapist__username")
    inlines = [RehabPlanTemplateCourseInline]


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
