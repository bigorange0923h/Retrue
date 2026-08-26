"""therapists：康复师模型的后台管理注册。"""

from django.contrib import admin

from apps.therapists.models import Therapist


@admin.register(Therapist)
class TherapistAdmin(admin.ModelAdmin):
    """康复师后台管理。"""

    list_display = ("name", "phone", "user", "is_active", "created_at")
    search_fields = ("name", "phone", "user__username")
    list_filter = ("is_active",)
