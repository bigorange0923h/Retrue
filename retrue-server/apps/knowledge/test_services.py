"""knowledge：向量化与 RAG 检索服务测试。

RAG 依赖真实 embedding/chat API，测试中用 mock 替换，
覆盖向量化保存、兜底检索与 RAG 回答流程。
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.models import Customer
from apps.knowledge.models import CustomerKnowledgeItem
from apps.knowledge.services import build_knowledge_index, rag_answer, search_knowledge

User = get_user_model()


class FakeEmbeddingProvider:
    """确定性 embedding provider（1024 维，匹配 VectorField 定义）。"""

    name = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vec = [0.0] * 1024
        for t in texts:
            vec[0] = float(len(t))
        return [vec[:] for _ in texts]


class KnowledgeServicesTests(TestCase):
    """知识服务测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与知识条目。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.item = CustomerKnowledgeItem.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            content="左膝 ACL 重建术后禁止深蹲",
            category="safety",
            importance="high",
        )
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            content="患者偏好下午训练",
            category="preference",
            importance="normal",
        )

    @patch("apps.knowledge.services.get_embedding_provider", return_value=FakeEmbeddingProvider())
    def test_build_index_saves_vectors(self, _mock):
        """向量化后知识条目保存 embedding。"""
        updated = build_knowledge_index(self.customer.id)
        self.assertEqual(updated, 2)
        items = CustomerKnowledgeItem.objects.filter(customer=self.customer)
        for item in items:
            self.assertIsNotNone(item.embedding)

    @patch("apps.knowledge.services.get_embedding_provider", return_value=None)
    def test_search_fallback_without_embedding(self, _mock):
        """无 embedding 时兜底检索仍返回知识，且安全限制优先。"""
        result = search_knowledge(self.customer.id, "能深蹲吗？")
        self.assertTrue(result)
        self.assertEqual(result[0]["content"], "左膝 ACL 重建术后禁止深蹲")
        self.assertEqual(result[0]["importance"], "high")

    @patch("apps.knowledge.services.get_embedding_provider", return_value=FakeEmbeddingProvider())
    @patch(
        "apps.knowledge.services.search_knowledge",
        return_value=[{"content": "左膝 ACL 重建术后禁止深蹲", "category": "safety", "importance": "high", "similarity": 0.1}],
    )
    @patch(
        "apps.ai.providers.factory.get_provider",
        return_value=type("FakeChat", (), {"chat": staticmethod(lambda p, s=None: "建议避免深蹲。")})(),
    )
    def test_rag_answer_returns_text(self, *_mocks):
        """RAG 回答基于检索知识生成文本。"""
        answer, chunks = rag_answer(
            self.customer.id,
            "我能深蹲吗？",
            therapist_name="张康复师",
            customer_name="张三",
        )
        self.assertIn("建议避免深蹲", answer)
        self.assertTrue(chunks)

    def test_rag_answer_no_knowledge(self):
        """无相关知识时返回明确降级提示。"""
        empty_customer = Customer.objects.create(therapist=self.therapist, name="空客户")
        answer, chunks = rag_answer(empty_customer.id, "你好")
        self.assertFalse(chunks)
        self.assertIn("暂未检索到", answer)
