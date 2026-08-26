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
