"""followups：回访/复查接口单元测试。"""

from __future__ import annotations

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer
from apps.followups.models import FollowUpTask

User = get_user_model()


class FollowUpApiTests(APITestCase):
    """回访/复查接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与待办。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.task = FollowUpTask.objects.create(
            therapist=self.therapist, customer=self.customer, followup_type="visit", due_date="2026-08-27"
        )

    def test_create_followup(self) -> None:
        """创建回访。"""
        resp = self.client.post(
            reverse("followup-list"),
            {"customer": self.customer.id, "followup_type": "review", "due_date": "2026-08-28", "content": "复评膝盖"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["followup_type_display"], "复查")

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建回访。"""
        resp = self.client.post(
            reverse("followup-list"),
            {"customer": self.other_customer.id, "due_date": "2026-08-28"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_and_update_status(self) -> None:
        """列表与更新状态。"""
        resp = self.client.get(reverse("followup-list"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

        resp = self.client.put(
            reverse("followup-detail", args=[self.task.id]),
            {"status": "done", "result": "电话回访完成"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "done")

    def test_terminal_status_requires_actual_result_or_skip_reason(self) -> None:
        """完成与跳过拒绝空白或占位文案，失败保留待处理状态。"""
        for state, result in [("done", ""), ("done", "已完成"), ("skipped", "  ")]:
            resp = self.client.put(reverse("followup-detail", args=[self.task.id]),
                                   {"status": state, "result": result}, format="json")
            self.assertEqual(resp.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "pending")
        resp = self.client.put(reverse("followup-detail", args=[self.task.id]),
                               {"status": "skipped", "result": "测试客户暂不便接听，改日联系"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["data"]["status"], "skipped")

    def test_explicit_next_followup_is_atomic_and_not_duplicated(self) -> None:
        """完成并显式建下一项；重复同一处理不重复续建。"""
        payload = {"status": "done", "result": "测试客户报告动作可完成，仍需跟进",
                   "next_task": {"followup_type": "review", "due_date": "2026-09-10", "content": "核对训练表现"}}
        resp = self.client.put(reverse("followup-detail", args=[self.task.id]), payload, format="json")
        self.assertEqual(resp.status_code, 200)
        following = FollowUpTask.objects.get(id=resp.data["data"]["next_task_id"])
        self.assertEqual(following.customer_id, self.customer.id)
        self.assertEqual(following.status, "pending")
        resp = self.client.put(reverse("followup-detail", args=[self.task.id]), payload, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(FollowUpTask.objects.count(), 2)

    def test_next_task_requires_explicit_due_date_and_done(self) -> None:
        """部分更新不能绕过下一项必填日期，也不能跳过时隐式续建。"""
        for payload in [{"status": "done", "result": "测试结果", "next_task": {}},
                        {"status": "skipped", "result": "测试原因", "next_task": {"due_date": "2026-09-10"}}]:
            resp = self.client.put(reverse("followup-detail", args=[self.task.id]), payload, format="json")
            self.assertEqual(resp.status_code, 400)
        self.assertEqual(FollowUpTask.objects.count(), 1)

    def test_followup_audit_failure_rolls_back_state_and_next_task(self) -> None:
        """审计写入失败时，状态和下一项一起回滚。"""
        with patch("apps.followups.services.write_audit_log", side_effect=RuntimeError("模拟审计失败")):
            resp = self.client.put(reverse("followup-detail", args=[self.task.id]),
                                   {"status": "done", "result": "测试实际结果",
                                    "next_task": {"due_date": "2026-09-10"}}, format="json")
        self.assertEqual(resp.status_code, 500)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "pending")
        self.assertEqual(FollowUpTask.objects.count(), 1)

    def test_followup_cannot_rebind_or_use_foreign_task(self) -> None:
        """客户关联不能改绑，另一账号不能处理当前客户回访。"""
        resp = self.client.put(reverse("followup-detail", args=[self.task.id]),
                               {"customer": self.other_customer.id}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.client.force_login(self.other)
        resp = self.client.put(reverse("followup-detail", args=[self.task.id]),
                               {"status": "done", "result": "测试结果"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_invalid_customer_filter_is_client_error(self) -> None:
        """非法筛选不触发数据库转换异常。"""
        resp = self.client.get(reverse("followup-list"), {"customer_id": "not-an-id"})
        self.assertEqual(resp.status_code, 400)

    def test_done_cannot_reuse_old_skipped_reason(self) -> None:
        """跳过原因不自动变成完成结果，必须明确输入本次内容。"""
        self.task.status = "skipped"
        self.task.result = "测试客户暂不便回访"
        self.task.save()
        resp = self.client.put(reverse("followup-detail", args=[self.task.id]), {"status": "done"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "skipped")
