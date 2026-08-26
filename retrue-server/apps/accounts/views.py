"""accounts：认证相关视图。

提供登录、登出与当前用户信息接口，基于 Django Session + Cookie 认证。
"""

from __future__ import annotations

from django.contrib.auth import login, logout
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.serializers import LoginSerializer, UserSerializer
from apps.audit.models import AuditAction, write_audit_log
from apps.common.response import ApiResponse


class LoginView(APIView):
    """登录接口。

    权限：允许匿名访问。
    说明：登录成功后写入 Django Session，客户端通过 Cookie 保持会话。
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # 登录接口本身不做认证

    def post(self, request):
        """执行登录。

        参数：
            request: 含 username、password 的请求。
        返回：
            成功返回当前用户信息；失败返回 400。
        """
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        write_audit_log(actor=user, action=AuditAction.LOGIN)
        return ApiResponse.ok(UserSerializer(user).data, message="登录成功")


class LogoutView(APIView):
    """登出接口。

    权限：需已登录。
    说明：清除当前会话与 Session 数据。
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """执行登出。

        参数：
            request: 当前请求。
        返回：
            成功返回空数据与成功消息。
        """
        user = request.user
        logout(request)
        write_audit_log(actor=user, action=AuditAction.LOGOUT)
        return ApiResponse.ok(message="已退出登录")


class CurrentUserView(APIView):
    """当前登录用户信息接口。

    权限：需已登录。
    返回：当前用户的 id、username、display_name、therapist_id。
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回当前用户信息。"""
        return ApiResponse.ok(UserSerializer(request.user).data, message="获取当前用户成功")
