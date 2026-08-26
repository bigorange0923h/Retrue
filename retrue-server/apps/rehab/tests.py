"""rehab：康复计划与阶段接口单元测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer
from apps.rehab.models import RehabPlan, RehabStage

User = get_user_model()


class RehabApiTests(APITestCase):
    """康复计划与阶段接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与计划。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.plan = RehabPlan.objects.create(
            therapist=self.therapist, customer=self.customer, start_date="2026-08-01"
        )

    def test_create_plan(self) -> None:
        """创建康复计划。"""
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {"customer": self.customer.id, "start_date": "2026-08-01", "name": "膝关节康复"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["name"], "膝关节康复")

    def test_cannot_create_plan_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建计划。"""
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {"customer": self.other_customer.id, "start_date": "2026-08-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_set_stage_closes_previous(self) -> None:
        """设置新阶段自动关闭上一阶段。"""
        RehabStage.objects.create(
            therapist=self.therapist, customer=self.customer, stage_type="acute", start_date="2026-08-01"
        )
        resp = self.client.post(
            reverse("rehab-stage"),
            {"customer": self.customer.id, "stage_type": "strength", "start_date": "2026-08-26"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # 上一阶段应已关闭
        old = RehabStage.objects.get(stage_type="acute", customer=self.customer)
        self.assertIsNotNone(old.end_date)
        # 新阶段有效
        current = RehabStage.objects.get(stage_type="strength", customer=self.customer)
        self.assertIsNone(current.end_date)

    def test_get_current_stage(self) -> None:
        """查询当前阶段。"""
        RehabStage.objects.create(
            therapist=self.therapist, customer=self.customer, stage_type="recovery", start_date="2026-08-10"
        )
        resp = self.client.get(reverse("rehab-stage"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["stage_type"], "recovery")

    def test_list_plans_isolated(self) -> None:
        """只能看到本人客户的计划。"""
        RehabPlan.objects.create(therapist=self.other, customer=self.other_customer, start_date="2026-08-01")
        resp = self.client.get(reverse("rehab-plan-list"), {"customer_id": self.customer.id})
        self.assertEqual(len(resp.data["data"]), 1)
