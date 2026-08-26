"""training：训练记录接口单元测试。

覆盖训练记录创建、动作明细、数据隔离、时间线与修订审计。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.customers.models import Customer
from apps.training.models import TrainingRecord

User = get_user_model()


class TrainingApiTests(APITestCase):
    """训练记录接口测试。"""

    def setUp(self) -> None:
        """准备康复师账号、客户与训练记录。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.record = TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 2",
            next_plan="增加单腿稳定训练",
        )

    def test_create_record_with_exercises(self) -> None:
        """创建训练记录并保存动作明细。"""
        payload = {
            "customer": self.customer.id,
            "training_date": "2026-08-27",
            "customer_feedback": "比上次稳定",
            "exercises": [
                {"exercise_name": "臀桥", "sets": 3, "reps": 12},
                {"exercise_name": "靠墙静蹲", "duration_seconds": 30},
            ],
        }
        resp = self.client.post(reverse("training-list"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["customer_name"], "张三")
        self.assertEqual(len(data["exercises"]), 2)
        self.assertEqual(data["exercises"][0]["exercise_name"], "臀桥")

    def test_create_record_for_other_customer_forbidden(self) -> None:
        """不能为其他康复师的客户创建训练记录。"""
        resp = self.client.post(
            reverse("training-list"),
            {"customer": self.other_customer.id, "training_date": "2026-08-27"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], 403)

    def test_list_requires_customer_id(self) -> None:
        """缺少 customer_id 返回 400。"""
        resp = self.client.get(reverse("training-list"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revision_requires_reason_and_writes_audit(self) -> None:
        """修订正式记录必须填写原因，并写入审计。"""
        payload = {
            "reason": "修正客户感受",
            "customer_feedback": "左膝疼痛 NRS 1（修正）",
        }
        resp = self.client.put(reverse("training-detail", args=[self.record.id]), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["customer_feedback"], "左膝疼痛 NRS 1（修正）")

        # 校验审计日志
        logs = AuditLog.objects.filter(content_type__model="trainingrecord", object_id=str(self.record.id))
        self.assertTrue(logs.exists())
        last = logs.order_by("-created_at").first()
        self.assertEqual(last.action, "update")
        self.assertEqual(last.reason, "修正客户感受")
        self.assertEqual(last.actor, self.therapist)

    def test_revision_without_reason_returns_400(self) -> None:
        """修订不提供原因返回 400。"""
        resp = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {"customer_feedback": "修改内容"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_timeline_orders_by_date_desc(self) -> None:
        """客户时间线按训练日期倒序。"""
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-25"
        )
        resp = self.client.get(reverse("customer-timeline"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        dates = [item["training_date"] for item in resp.data["data"]]
        self.assertEqual(dates, ["2026-08-26", "2026-08-25"])

    def test_cannot_access_other_therapist_record(self) -> None:
        """不能读取其他康复师的训练记录。"""
        other_record = TrainingRecord.objects.create(
            therapist=self.other, customer=self.other_customer, training_date="2026-08-26"
        )
        resp = self.client.get(reverse("training-detail", args=[other_record.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
