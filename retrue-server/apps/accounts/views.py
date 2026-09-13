"""accounts：认证相关视图。

提供登录、登出、CSRF token 获取与当前用户信息接口，基于 Django Session + Cookie 认证。
登录请求强制 CSRF 校验（URL 层以 csrf_protect 包裹）；登录失败按账号与 IP 限流，
成功登录即清除计数。
"""

from __future__ import annotations

from django.contrib.auth import login, logout
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import HttpResponse, JsonResponse
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import login_throttle
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


def _login_csrf_view(request):  # noqa: ANN001 - 占位视图，使 CSRF 中间件判断为非豁免
    """占位回调：用于在登录视图内手动触发 CSRF 校验。"""
    return HttpResponse("ok")


def _enforce_login_csrf(request) -> HttpResponse | None:
    """对登录请求执行 Django CSRF 校验（DRF as_view 默认豁免全局中间件）。

    通过手动调用 ``CsrfViewMiddleware.process_view`` 复用统一的 token/Origin
    校验逻辑；它会尊重测试客户端的 ``_dont_enforce_csrf_checks``（未开启
    enforce 的测试仍放行），真实浏览器缺失/错误 token 时返回 403。
    校验失败响应经由 ``settings.CSRF_FAILURE_VIEW`` 输出统一 JSON。

    参数：
        request: DRF Request。
    返回：
        校验失败时返回 HttpResponse；通过返回 None。
    """
    rejected = CsrfViewMiddleware(lambda req: HttpResponse("")).process_view(
        request._request,
        _login_csrf_view,
        (),
        {},
    )
    return rejected


def _client_ip(request) -> str:
    """提取客户端 IP；优先取反向代理提供的 X-Forwarded-For 首项。"""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class CsrfTokenView(APIView):
    """获取 CSRF token 的端点。

    权限：允许匿名访问（登录前需要先取 token）。
    GET：设置 csrftoken Cookie 并返回 token，供登录/后续写请求携带。
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        """返回 csrf token，同时种下 Cookie。"""
        return ApiResponse.ok({"token": get_token(request)}, message="获取成功")


def csrf_failure_json(request, reason: str = ""):
    """CSRF 校验失败统一返回 JSON（settings.CSRF_FAILURE_VIEW）。

    返回 {code:403,message,data}，与业务接口信封一致；reason 仅用于日志，
    不直接暴露给客户端。
    """
    return JsonResponse(
        {
            "code": 403,
            "message": "请求校验失败，请刷新页面后重试",
            "data": {"error_code": "csrf_failed"},
        },
        status=403,
    )


class LoginView(APIView):
    """登录接口。

    权限：允许匿名访问。
    说明：URL 层通过 ``csrf_protect`` 强制 CSRF 校验；登录成功后写入 Django
    Session，客户端通过 Cookie 保持会话。失败次数按“用户名 + 来源 IP”双维度
    计入数据库缓存，达到阈值返回 429，窗口过期自动恢复。
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # 登录接口本身不做认证

    def post(self, request):
        """执行登录。

        参数：
            request: 含 username、password 的请求。
        返回：
            成功返回当前用户信息；失败返回 400；短期失败过多返回 429。
        """
        username = str(request.data.get("username", "") or "").strip()
        ip = _client_ip(request)

        # 登录强制 CSRF：缺失/错误 token 直接返回 403（统一 JSON），
        # 避免“登录接口豁免 CSRF”成为 Session 写接口的安全缺口。
        rejected = _enforce_login_csrf(request)
        if rejected is not None:
            return rejected

        if login_throttle.is_blocked(username, ip):
            return ApiResponse.error(
                "登录尝试过于频繁，请稍后再试",
                429,
                data={"error_code": "login_throttled"},
            )

        serializer = LoginSerializer(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            # 认证失败（含密码错误/账号停用/参数不完整）计入账号与 IP 双维度计数
            login_throttle.record_failure(username, ip)
            raise
        user = serializer.validated_data["user"]
        login_throttle.clear_failures(username)
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
