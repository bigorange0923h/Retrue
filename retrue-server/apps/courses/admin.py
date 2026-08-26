"""courses：课时模型的后台管理注册。"""

from django.contrib import admin

from apps.courses.models import CourseAdjustment, CoursePackage


@admin.register(CoursePackage)
class CoursePackageAdmin(admin.ModelAdmin):
    """课时包后台管理。"""

    list_display = ("name", "customer", "total_sessions", "used_sessions", "remaining_sessions")
    list_filter = ("therapist",)
    search_fields = ("customer__name",)


@admin.register(CourseAdjustment)
class CourseAdjustmentAdmin(admin.ModelAdmin):
    """课时调整后台管理。"""

    list_display = ("package", "delta", "reason", "created_at")
