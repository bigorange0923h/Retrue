"""knowledge：客户知识库接口单元测试。

覆盖知识条目 CRUD、候选提交/确认/拒绝、数据隔离与审计。
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.customers.models import Customer
from apps.knowledge.models import (
    CandidateStatus,
    CustomerKnowledgeItem,
    KnowledgeCandidate,
)

User = get_user_model()


class KnowledgeItemApiTests(APITestCase):
    """知识条目接口测试。"""

    def setUp(self) -> None:
        """准备康复师与客户数据。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

    def test_create_knowledge_item(self) -> None:
        """康复师可为客户新增知识条目。"""
        resp = self.client.post(
            reverse("knowledge-item-list"),
            {
                "customer": self.customer.id,
                "content": "左膝 ACL 重建术后 6 周，禁止深蹲",
                "category": "safety",
                "importance": "high",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["category"], "safety")
        self.assertTrue(resp.data["data"]["is_active"])

    def test_create_writes_audit_log(self) -> None:
        """知识条目新增写入审计日志。"""
        self.client.post(
            reverse("knowledge-item-list"),
            {"customer": self.customer.id, "content": "有深静脉血栓史"},
            format="json",
        )
        self.assertTrue(AuditLog.objects.filter(action="create", actor=self.therapist).exists())

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户新增知识。"""
        resp = self.client.post(
            reverse("knowledge-item-list"),
            {"customer": self.other_customer.id, "content": "测试"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_isolates_customer(self) -> None:
        """知识条目按客户隔离。"""
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer, content="自己的知识"
        )
        CustomerKnowledgeItem.objects.create(
            therapist=self.other, customer=self.other_customer, content="他人知识"
        )
        resp = self.client.get(reverse("knowledge-item-list"), {"customer": self.customer.id})
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["content"], "自己的知识")

    def test_update_and_disable(self) -> None:
        """可更新内容并停用条目。"""
        item = CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer, content="旧内容"
        )
        resp = self.client.put(
            reverse("knowledge-item-detail", args=[item.id]),
            {"content": "新内容", "is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["content"], "新内容")
        self.assertFalse(resp.data["data"]["is_active"])


class KnowledgeCandidateTests(APITestCase):
    """知识候选确认/拒绝测试。"""

    def setUp(self) -> None:
        """准备康复师与客户数据。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

    def test_submit_candidate(self) -> None:
        """AI 可提交候选记忆，但不自动写入正式知识。"""
        resp = self.client.post(
            reverse("knowledge-candidate-list"),
            {
                "customer": self.customer.id,
                "content": "建议记录：患者对高抬腿动作耐受良好",
                "source_ref": "训练记录 #123",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "pending")
        # 候选提交不产生正式知识
        self.assertEqual(CustomerKnowledgeItem.objects.count(), 0)

    def test_confirm_candidate_creates_knowledge(self) -> None:
        """确认候选后转为正式知识。"""
        candidate = KnowledgeCandidate.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            content="患者对高抬腿动作耐受良好",
            category="recovery",
        )
        resp = self.client.post(
            reverse("knowledge-candidate-decide", args=[candidate.id]),
            {"action": "confirm", "importance": "high"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.CONFIRMED)
        item = CustomerKnowledgeItem.objects.get()
        self.assertEqual(item.content, "患者对高抬腿动作耐受良好")
        self.assertEqual(item.source, "ai_confirmed")
        self.assertEqual(item.importance, "high")

    def test_reject_candidate(self) -> None:
        """拒绝候选不生成正式知识。"""
        candidate = KnowledgeCandidate.objects.create(
            therapist=self.therapist, customer=self.customer, content="无效建议"
        )
        resp = self.client.post(
            reverse("knowledge-candidate-decide", args=[candidate.id]),
            {"action": "reject"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.REJECTED)
        self.assertEqual(CustomerKnowledgeItem.objects.count(), 0)

    def test_cannot_decide_twice(self) -> None:
        """已处理的候选不能再次处理。"""
        candidate = KnowledgeCandidate.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            content="建议",
            status=CandidateStatus.REJECTED,
        )
        resp = self.client.post(
            reverse("knowledge-candidate-decide", args=[candidate.id]),
            {"action": "confirm"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RagApiTests(APITestCase):
    """RAG 回答接口测试。"""

    def setUp(self) -> None:
        """准备康复师与客户数据。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

    @patch("apps.knowledge.views.rag_answer")
    def test_rag_requires_customer(self, _mock):
        """缺少 customer 参数时返回 400。"""
        resp = self.client.post(reverse("knowledge-rag"), {"question": "你好"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.knowledge.views.rag_answer")
    def test_rag_requires_question(self, _mock):
        """缺少 question 参数时返回 400。"""
        resp = self.client.post(reverse("knowledge-rag"), {"customer": self.customer.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(
        "apps.knowledge.views.rag_answer",
        return_value=("建议避免深蹲。", [{"content": "禁止深蹲", "category": "safety", "importance": "high"}]),
    )
    def test_rag_returns_answer(self, _mock):
        """RAG 回答基于客户知识生成，并标注使用客户上下文。"""
        resp = self.client.post(
            reverse("knowledge-rag"),
            {"customer": self.customer.id, "question": "我能深蹲吗？"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["answer"], "建议避免深蹲。")
        self.assertTrue(data["using_customer_context"])
        self.assertTrue(data["used_knowledge"])

    def test_rag_rejects_other_therapist_customer(self):
        """不能基于其他康复师的客户做 RAG 回答。"""
        other = User.objects.create_user(username="t2", password="test12345")
        other_customer = Customer.objects.create(therapist=other, name="李四")
        resp = self.client.post(
            reverse("knowledge-rag"),
            {"customer": other_customer.id, "question": "你好"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
