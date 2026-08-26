"""assessments：评估接口单元测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assessments.models import Assessment
from apps.customers.models import Customer
from apps.audit.models import AuditLog

User = get_user_model()


class AssessmentApiTests(APITestCase):
    """评估接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与评估。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.assessment = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="initial",
            assessment_date="2026-08-01",
            chief_complaint="左膝前侧疼痛",
        )

    def test_create_assessment_with_metrics(self) -> None:
        """创建评估并保存指标。"""
        payload = {
            "customer": self.customer.id,
            "assessment_type": "initial",
            "assessment_date": "2026-08-01",
            "chief_complaint": "左膝疼痛",
            "metrics": [
                {"metric_type": "pain", "body_part": "左膝", "score": 6, "score_max": 10},
                {"metric_type": "strength", "body_part": "左膝", "score": 4, "score_max": 5},
            ],
        }
        resp = self.client.post(reverse("assessment-list"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(len(data["metrics"]), 2)
        self.assertEqual(data["metrics"][0]["metric_type"], "pain")

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建评估。"""
        resp = self.client.post(
            reverse("assessment-list"),
            {"customer": self.other_customer.id, "assessment_date": "2026-08-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_and_detail(self) -> None:
        """列表与详情。"""
        resp = self.client.get(reverse("assessment-list"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

        resp = self.client.get(reverse("assessment-detail", args=[self.assessment.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["chief_complaint"], "左膝前侧疼痛")

    def test_cannot_access_other_therapist_assessment(self) -> None:
        """不能访问其他康复师的评估。"""
        other_assessment = Assessment.objects.create(
            therapist=self.other, customer=self.other_customer, assessment_date="2026-08-01"
        )
        resp = self.client.get(reverse("assessment-detail", args=[other_assessment.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_writes_audit(self) -> None:
        """更新评估并记录审计。"""
        resp = self.client.put(
            reverse("assessment-detail", args=[self.assessment.id]),
            {"chief_complaint": "左膝疼痛（更新）", "rehab_goal": "恢复下蹲"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["chief_complaint"], "左膝疼痛（更新）")
        self.assertTrue(AuditLog.objects.filter(content_type__model="assessment").exists())
