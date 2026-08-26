"""accounts：用户模型的后台管理注册。"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import User


@admin.register(User)
class RetrueUserAdmin(UserAdmin):
    """系统用户后台管理，使用 Django 默认用户管理能力。"""

    list_display = ("username", "email", "first_name", "last_name", "is_active", "is_staff")
