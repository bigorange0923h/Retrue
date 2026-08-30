"""schedules：课程模型的后台管理注册。"""

from django.contrib import admin

from apps.schedules.models import CourseSession, CourseType, PlanCourseAdjustment, RehabPlanCourse


@admin.register(CourseSession)
class CourseSessionAdmin(admin.ModelAdmin):
    """课程后台管理。"""

    list_display = ("date", "customer", "status", "therapist", "start_time")
    list_filter = ("status", "date")
    search_fields = ("customer__name",)


@admin.register(CourseType)
class CourseTypeAdmin(admin.ModelAdmin):
    """课程模板后台管理。"""

    list_display = ("name", "therapist", "is_active", "default_duration")
    list_filter = ("is_active",)


@admin.register(RehabPlanCourse)
class RehabPlanCourseAdmin(admin.ModelAdmin):
    """计划内课程后台管理。"""

    list_display = ("rehab_plan", "course_type", "planned_count", "status", "package")
    list_filter = ("status",)


@admin.register(PlanCourseAdjustment)
class PlanCourseAdjustmentAdmin(admin.ModelAdmin):
    """计划内课程次数调整后台管理。"""

    list_display = ("plan_course", "delta_count", "before_count", "after_count", "therapist")
