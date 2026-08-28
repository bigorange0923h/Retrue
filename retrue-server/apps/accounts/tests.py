"""accounts：认证接口单元测试。

覆盖登录、登出、当前用户、未登录权限控制与统一响应格式。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

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
