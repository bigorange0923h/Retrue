"""accounts：认证接口单元测试。

覆盖登录、登出、当前用户、未登录权限控制与统一响应格式。
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts import login_throttle
from apps.audit.models import AuditLog
from apps.therapists.models import Therapist

User = get_user_model()


class AuthApiTests(APITestCase):
    """认证接口测试。"""

    def setUp(self) -> None:
        """准备测试账号。"""
        self.user = User.objects.create_user(username="tester", password="test12345")
        Therapist.objects.create(user=self.user, name="测试康复师", phone="13800000001")

    def test_login_success_returns_unified_response(self) -> None:
        """登录成功返回统一信封结构与用户信息。"""
        resp = self.client.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["code"], 200)
        self.assertEqual(resp.data["data"]["username"], "tester")
        self.assertEqual(resp.data["data"]["display_name"], "测试康复师")
        self.assertEqual(resp.data["data"]["therapist_id"], self.user.therapist_profile.id)

    def test_login_wrong_password_returns_400(self) -> None:
        """错误密码登录返回 400 与统一消息。"""
        resp = self.client.post(
            reverse("login"),
            {"username": "tester", "password": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["code"], 400)
        self.assertIn("错误", resp.data["message"])

    def test_unauthenticated_me_returns_401(self) -> None:
        """未登录访问当前用户接口返回 401。"""
        resp = self.client.get(reverse("current-user"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data["code"], 401)

    def test_logout_clears_session(self) -> None:
        """登出后再次访问受保护接口返回 401。"""
        self.client.login(username="tester", password="test12345")
        logout_resp = self.client.post(reverse("logout"))
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)
        me_resp = self.client.get(reverse("current-user"))
        self.assertEqual(me_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_writes_audit_log(self) -> None:
        """登录成功会写入审计日志。"""
        self.client.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
        )
        self.assertTrue(AuditLog.objects.filter(action="login", actor=self.user).exists())

    def test_csrf_token_endpoint_sets_cookie_and_returns_token(self) -> None:
        """GET /csrf/ 返回 token 并种下 csrftoken Cookie。"""
        resp = self.client.get(reverse("csrf-token"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["data"]["token"])
        self.assertIn("csrftoken", resp.cookies)

    def test_login_requires_csrf_token_when_enforced(self) -> None:
        """启用 enforce_csrf_checks 时，缺失/错误 token 的登录被拒（F05）。"""
        enforced = APIClient(enforce_csrf_checks=True)

        # 未先获取 token → 403
        resp = enforced.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 先 GET csrf 端点种下 Cookie，再带正确 token → 成功
        enforced.get(reverse("csrf-token"))
        token = enforced.cookies.get("csrftoken").value
        ok = enforced.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    @override_settings(LOGIN_THROTTLE_MAX_FAILURES=3, LOGIN_THROTTLE_IP_MAX_FAILURES=3)
    def test_login_throttle_blocks_after_repeated_failures(self) -> None:
        """短期连续登录失败返回 429，窗口恢复后可再次登录（F05）。"""
        for _ in range(3):
            resp = self.client.post(
                reverse("login"),
                {"username": "tester", "password": "wrongpass"},
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        blocked = self.client.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
        )
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(blocked.data["data"]["error_code"], "login_throttled")

        # 显式清除测试缓存，模拟账号与 IP 两个窗口均已过期。
        login_throttle.clear_failures("tester")
        cache.delete("login_fail:ip:127.0.0.1")
        ok = self.client.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_successful_login_does_not_clear_shared_ip_throttle(self) -> None:
        """一个账号成功登录不能重置同一出口下其他账号的失败记录。"""
        ip = "127.0.0.1"
        login_throttle.record_failure("another-user", ip)

        resp = self.client.post(
            reverse("login"),
            {"username": "tester", "password": "test12345"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(login_throttle.user_failures("tester"), 0)
        self.assertEqual(login_throttle.ip_failures(ip), 1)

    def test_csrf_failure_returns_unified_json(self) -> None:
        """CSRF 失败返回统一 JSON 信封（settings.CSRF_FAILURE_VIEW）。"""
        enforced = APIClient(enforce_csrf_checks=True)
        resp = enforced.post(reverse("login"), {"username": "x", "password": "y"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.json()["code"], 403)
        self.assertEqual(resp.json()["data"]["error_code"], "csrf_failed")


class UserAdminApiTests(APITestCase):
    """账号管理接口测试。"""

    def setUp(self) -> None:
        """准备超管、普通康复师账号。"""
        self.admin = User.objects.create_superuser(username="admin", password="admin12345")
        self.staff = User.objects.create_user(username="tester", password="test12345")
        Therapist.objects.create(user=self.staff, name="测试康复师", phone="13800000001")

    def _login(self, user) -> None:
        """登录指定用户。"""
        self.client.force_login(user)

    def test_regular_user_cannot_list_users(self) -> None:
        """普通用户访问用户列表返回 403。"""
        self._login(self.staff)
        resp = self.client.get(reverse("user-admin-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], 403)

    def test_admin_can_list_users(self) -> None:
        """超级用户可查看用户列表。"""
        self._login(self.admin)
        resp = self.client.get(reverse("user-admin-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["code"], 200)
        usernames = [item["username"] for item in resp.data["data"]["items"]]
        self.assertIn("admin", usernames)
        self.assertIn("tester", usernames)

    def test_admin_can_create_user(self) -> None:
        """超级用户可创建新账号。"""
        self._login(self.admin)
        resp = self.client.post(
            reverse("user-admin-list"),
            {"username": "newuser", "password": "newpass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_create_duplicate_username_returns_400(self) -> None:
        """创建重复用户名返回 400。"""
        self._login(self.admin)
        resp = self.client.post(
            reverse("user-admin-list"),
            {"username": "tester", "password": "newpass123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_weak_password(self) -> None:
        """创建账号时复用 Django 密码验证器：弱密码被拒（F05）。"""
        self._login(self.admin)
        weak_passwords = ["12345678", "password", "test1234"]  # 纯数字 / 常见弱口令 / 与用户名相近
        for weak in weak_passwords:
            resp = self.client.post(
                reverse("user-admin-list"),
                {"username": f"weakuser_{weak}", "password": weak},
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, f"{weak} 不应通过")
        self.assertFalse(User.objects.filter(username__startswith="weakuser_").exists())

    def test_reset_rejects_weak_password(self) -> None:
        """重置密码同样复用密码验证器：弱密码被拒（F05）。"""
        self._login(self.admin)
        target = User.objects.create_user(username="weakreset", password="StrongPass1")
        resp = self.client.put(
            reverse("user-admin-detail", args=[target.id]),
            {"password": "12345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        target.refresh_from_db()
        self.assertTrue(target.check_password("StrongPass1"))

    def test_admin_can_disable_user(self) -> None:
        """超级用户可停用普通用户。"""
        self._login(self.admin)
        resp = self.client.put(
            reverse("user-admin-detail", args=[self.staff.id]),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

    def test_cannot_disable_last_active_superuser(self) -> None:
        """不能停用最后一个可用超级用户。"""
        self._login(self.admin)
        resp = self.client.put(
            reverse("user-admin-detail", args=[self.admin.id]),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_cannot_edit_own_permission(self) -> None:
        """不能修改自己的权限，避免意外失去管理入口。"""
        self._login(self.admin)
        resp = self.client.put(
            reverse("user-admin-detail", args=[self.admin.id]),
            {"is_superuser": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_current_user_includes_permission_fields(self) -> None:
        """当前用户信息包含 is_superuser / is_active / is_staff。"""
        self._login(self.admin)
        resp = self.client.get(reverse("current-user"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertTrue(data["is_superuser"])
        self.assertTrue(data["is_active"])
        self.assertTrue(data["is_staff"])
