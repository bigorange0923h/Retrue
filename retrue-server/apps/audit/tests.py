"""audit：审计接口单元测试。

覆盖审计日志分页查询与按对象查询。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditAction, AuditLog, write_audit_log

User = get_user_model()


class AuditApiTests(APITestCase):
    """审计日志接口测试。"""

    def setUp(self) -> None:
        """准备测试用户与审计记录。"""
        self.user = User.objects.create_user(username="tester", password="test12345")
        self.client.login(username="tester", password="test12345")
        write_audit_log(
            actor=self.user,
            action=AuditAction.LOGIN,
            reason="登录",
            after={"hello": "world"},
        )

    def test_list_requires_auth(self) -> None:
        """未登录访问审计列表返回 401。"""
        self.client.logout()
        resp = self.client.get(reverse("audit-list"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_page(self) -> None:
        """登录后可分页查询审计日志。"""
        resp = self.client.get(reverse("audit-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["code"], 200)
        self.assertEqual(resp.data["data"]["total"], 1)
        item = resp.data["data"]["items"][0]
        self.assertEqual(item["action"], "login")
        self.assertEqual(item["actor_name"], "tester")
        self.assertEqual(item["after_data"], {"hello": "world"})

    def test_object_list_by_model(self) -> None:
        """按对象类型查询审计历史：为业务对象写入审计后可按其查询。"""
        from django.contrib.contenttypes.models import ContentType

        # 给用户对象写一条关联审计
        write_audit_log(actor=self.user, action=AuditAction.CREATE, obj=self.user, after={"x": 1})
        resp = self.client.get(
            reverse("audit-object"),
            {"model": "user", "object_id": str(self.user.id)},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["code"], 200)
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["action"], "create")
