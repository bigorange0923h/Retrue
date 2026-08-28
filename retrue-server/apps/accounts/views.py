"""accounts：认证相关视图。

提供登录、登出与当前用户信息接口，基于 Django Session + Cookie 认证。
"""

from __future__ import annotations

from django.contrib.auth import login, logout
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import (
    LoginSerializer,
    UserCreateSerializer,
    UserListSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.audit.models import AuditAction, write_audit_log
from apps.common.permissions import IsSuperUser
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


class UserAdminListView(APIView):
    """账号管理：用户列表与创建接口。

    权限：仅超级用户。
    GET：分页返回全部用户。
    POST：创建新账号。
    """

    permission_classes = [IsSuperUser]

    def get(self, request):
        """分页查询用户列表，支持 keyword 搜索。"""
        keyword = request.query_params.get("keyword", "").strip()
        page, page_size = _parse_page(request)

        queryset = User.objects.order_by("-is_superuser", "date_joined")
        if keyword:
            queryset = queryset.filter(
                models_q_username_or_display(keyword)
            )
        total = queryset.count()
        start = (page - 1) * page_size
        users = queryset[start : start + page_size]
        items = UserListSerializer(users, many=True).data
        return ApiResponse.ok_page(items, page, page_size, total, message="查询用户成功")

    def post(self, request):
        """创建账号。"""
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        write_audit_log(
            actor=request.user,
            action=AuditAction.CREATE,
            obj=user,
            after=UserListSerializer(user).data,
            reason="账号管理：创建账号",
        )
        return ApiResponse.ok(UserListSerializer(user).data, message="账号创建成功")


class UserAdminDetailView(APIView):
    """账号管理：单个用户更新接口。

    权限：仅超级用户。
    PUT：更新账号（启用/停用、后台权限、超管权限、重置密码）。
    """

    permission_classes = [IsSuperUser]

    def _get_or_404(self, user_id: int) -> User | Response:
        """获取目标用户，不存在返回 404 响应。"""
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return ApiResponse.error("用户不存在", 404)
        return user

    def put(self, request, user_id: int):
        """更新账号信息。"""
        user = self._get_or_404(user_id)
        if isinstance(user, Response):
            return user
        # 不允许修改自己的权限，避免意外把自己降级/停用后失去管理入口
        if user.id == request.user.id and (
            "is_superuser" in request.data or "is_staff" in request.data
        ):
            return ApiResponse.error("不能修改自己的权限", 400)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = UserListSerializer(user).data
        updated = serializer.save()
        after = UserListSerializer(updated).data
        write_audit_log(
            actor=request.user,
            action=AuditAction.UPDATE,
            obj=updated,
            before=before,
            after=after,
            reason="账号管理：更新账号",
        )
        return ApiResponse.ok(after, message="账号已更新")


def _parse_page(request) -> tuple[int, int]:
    """解析分页参数，带默认值与边界保护。"""
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError):
        page_size = 20
    return page, page_size


def models_q_username_or_display(keyword: str):
    """构造用户名或展示名模糊匹配查询条件。

    展示名来自关联的康复师姓名，因此对 therapists 表做 name 匹配。
    返回一个可合并到 queryset 的 Q 对象。
    """
    from django.db.models import Q

    return Q(username__icontains=keyword) | Q(therapist_profile__name__icontains=keyword)
