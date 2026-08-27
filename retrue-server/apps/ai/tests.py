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

    def test_prepare_lesson_returns_summary_and_suggestions(self) -> None:
        """备课助手返回客户汇总与 AI 建议。"""
        from apps.training.models import TrainingRecord

        TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 6",
            next_plan="增加单腿稳定训练",
        )
        resp = self.client.get(reverse("ai-prepare-lesson"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIn("customer_summary", data)
        self.assertIn("ai_suggestions", data)
        # 疼痛 NRS 6 应触发风险提醒
        self.assertTrue(len(data["ai_suggestions"]["risk_reminders"]) >= 1)
        self.assertEqual(data["customer_summary"]["next_plan"], "增加单腿稳定训练")

    def test_prepare_lesson_requires_customer_id(self) -> None:
        """备课缺少 customer_id 返回 400。"""
        resp = self.client.get(reverse("ai-prepare-lesson"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RiskAlertApiTests(APITestCase):
    """风险提醒接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与训练记录。"""
        from apps.training.models import TrainingRecord

        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-25",
            customer_feedback="左膝疼痛 NRS 7",
        )
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 6",
        )

    def test_detect_risk_high_level(self) -> None:
        """连续 NRS>=6 触发高风险提醒。"""
        resp = self.client.post(
            reverse("ai-risk-detect"),
            {"customer_id": self.customer.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIsNotNone(data)
        self.assertEqual(data["risk_level"], "high")

    def test_risk_list_and_update(self) -> None:
        """风险列表与确认更新。"""
        from apps.ai.models import RiskAlert

        alert = RiskAlert.objects.create(
            therapist=self.therapist, customer=self.customer, risk_level="high", suggested_action="pause",
        )
        resp = self.client.get(reverse("ai-risk-list"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

        resp = self.client.put(
            reverse("ai-risk-update", args=[alert.id]),
            {"is_confirmed": True, "outcome": "已安排复查"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["is_confirmed"], True)
        self.assertEqual(resp.data["data"]["outcome"], "已安排复查")


class ProgressApiTests(APITestCase):
    """阶段进展参考接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与训练记录。"""
        from apps.training.models import TrainingRecord

        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-24",
            customer_feedback="左膝疼痛 NRS 6",
        )
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 2",
        )

    def test_analyze_progress_improvement(self) -> None:
        """疼痛降低识别为改善。"""
        resp = self.client.get(reverse("ai-progress"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["pain_trend"], "改善")
        self.assertTrue(any("NRS 6 降至 NRS 2" in obs for obs in data["observations"]))

    def test_analyze_progress_requires_customer_id(self) -> None:
        """缺少 customer_id 返回 400。"""
        resp = self.client.get(reverse("ai-progress"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
