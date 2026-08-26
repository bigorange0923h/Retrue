"""schedules：课程模型的后台管理注册。"""

from django.contrib import admin

from apps.schedules.models import CourseSession


@admin.register(CourseSession)
class CourseSessionAdmin(admin.ModelAdmin):
    """课程后台管理。"""

    list_display = ("date", "customer", "status", "therapist", "start_time")
    list_filter = ("status", "date")
    search_fields = ("customer__name",)
