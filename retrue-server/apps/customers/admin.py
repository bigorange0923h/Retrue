"""customers：客户模型的后台管理注册。"""

from django.contrib import admin

from apps.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """客户后台管理。"""

    list_display = ("name", "phone_masked", "status", "therapist", "created_at")
    search_fields = ("name", "phone")
    list_filter = ("status", "therapist")
