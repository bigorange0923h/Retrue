"""assessments：评估模型的后台管理注册。"""

from django.contrib import admin

from apps.assessments.models import Assessment, AssessmentMetric


class AssessmentMetricInline(admin.TabularInline):
    """评估指标内联管理。"""

    model = AssessmentMetric
    extra = 0


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    """评估后台管理。"""

    list_display = ("assessment_date", "customer", "assessment_type", "therapist")
    list_filter = ("assessment_type",)
    search_fields = ("customer__name", "chief_complaint")
    inlines = [AssessmentMetricInline]
