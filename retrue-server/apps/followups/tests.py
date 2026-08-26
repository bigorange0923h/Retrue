"""followups：回访/复查接口单元测试。"""

from __future__ import annotations

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
