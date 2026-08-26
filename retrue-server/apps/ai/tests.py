"""ai：AI 草稿接口单元测试。

覆盖草稿解析、确认创建正式记录、取消、状态流转与数据隔离。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft, AiDraftStatus
from apps.customers.models import Customer
from apps.training.models import TrainingRecord

User = get_user_model()


class AiDraftApiTests(APITestCase):
    """AI 草稿接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与草稿。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

        self.draft = AiDraft.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            input_text="做了臀桥 3 组 12 次，左膝疼痛 2 分",
            ai_result={"exercises": [{"exercise_name": "臀桥", "sets": 3, "reps": 12}]},
            status=AiDraftStatus.PENDING,
        )

    def test_parse_creates_pending_draft(self) -> None:
        """解析文本生成待确认草稿。"""
        resp = self.client.post(
            reverse("ai-parse"),
            {"input_text": "今天做了臀桥 3 组 12 次，靠墙静蹲 30 秒", "customer_id": self.customer.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(len(data["ai_result"]["exercises"]), 2)

    def test_parse_empty_text_returns_400(self) -> None:
        """空文本被参数校验拒绝，返回 400。"""
        resp = self.client.post(reverse("ai-parse"), {"input_text": ""}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_creates_training_record(self) -> None:
        """确认草稿创建正式训练记录。"""
        confirmed = {
            "training_date": "2026-08-26",
            "customer_feedback": "左膝疼痛 NRS 2",
            "exercises": [{"exercise_name": "臀桥", "sets": 3, "reps": 12}],
        }
        resp = self.client.post(
            reverse("ai-confirm", args=[self.draft.id]),
            {"customer_id": self.customer.id, "confirmed": confirmed},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "confirmed")
        # 正式记录已创建
        self.assertEqual(TrainingRecord.objects.filter(customer=self.customer).count(), 1)
        record = TrainingRecord.objects.get(customer=self.customer)
        self.assertEqual(record.customer_feedback, "左膝疼痛 NRS 2")
        self.assertEqual(record.exercises.count(), 1)

    def test_confirm_cannot_confirm_other_therapist_draft(self) -> None:
        """不能确认其他康复师的草稿。"""
        other_draft = AiDraft.objects.create(
            therapist=self.other,
            input_text="x",
            status=AiDraftStatus.PENDING,
        )
        resp = self.client.post(
            reverse("ai-confirm", args=[other_draft.id]),
            {"customer_id": self.customer.id, "confirmed": {"training_date": "2026-08-26"}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_draft(self) -> None:
        """取消草稿不创建正式记录。"""
        resp = self.client.post(reverse("ai-cancel", args=[self.draft.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "cancelled")
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_customer_candidates(self) -> None:
        """按姓名提示返回客户候选。"""
        resp = self.client.get(reverse("ai-candidates"), {"name": "张"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in resp.data["data"]]
        self.assertIn("张三", names)
        # 候选不返回完整手机号
        self.assertIn("phone_masked", resp.data["data"][0])
