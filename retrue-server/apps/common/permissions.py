"""common：通用权限类。

提供面向业务接口的细粒度权限控制。默认接口仅要求已登录
（REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES），需要更高级别
权限的接口通过 permission_classes 显式指定。
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    """仅超级用户可访问。

    用于账号管理等敏感管理接口。后端强制校验权限，
    仅隐藏前端入口不足以保护该页面。
    """

    message = "需要超级用户权限"

    def has_permission(self, request, view) -> bool:
        """判断当前用户是否为超级用户。"""
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
