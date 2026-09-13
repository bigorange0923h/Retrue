"""knowledge：向量化与 RAG 检索服务测试。

RAG 依赖真实 embedding/chat API，测试中用 mock 替换，
覆盖向量化保存、兜底检索与 RAG 回答流程。
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai.schemas.memory import EpisodeEvaluationResult, MemoryEvaluationResult
from apps.customers.models import Customer
from apps.knowledge.models import CustomerKnowledgeItem, MemoryStatus
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
    @patch("apps.ai.providers.factory.get_provider")
    def test_rag_answer_returns_text(self, mock_get_provider, *_mocks):
        """RAG 规则走 system 消息，知识片段作为普通资料发送。"""
        provider = MagicMock()
        provider.chat.return_value = "建议避免深蹲。"
        mock_get_provider.return_value = provider
        answer, chunks = rag_answer(
            self.customer.id,
            "我能深蹲吗？",
            therapist_name="张康复师",
            customer_name="张三",
        )
        self.assertIn("建议避免深蹲", answer)
        self.assertTrue(chunks)
        prompt = provider.chat.call_args.args[0]
        system = provider.chat.call_args.kwargs["system"]
        self.assertIn("<受控康复知识库>", prompt)
        self.assertIn("仅依据", system)

    def test_rag_answer_no_knowledge(self):
        """无相关知识时返回明确降级提示。"""
        empty_customer = Customer.objects.create(therapist=self.therapist, name="空客户")
        answer, chunks = rag_answer(empty_customer.id, "你好")
        self.assertFalse(chunks)
        self.assertIn("暂未检索到", answer)

    def test_search_excludes_inactive_and_expired_and_out_of_range(self) -> None:
        """停用/已替代/过期/超出有效期的知识不进入检索（F11 生命周期过滤统一）。"""
        now = timezone.now()
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer,
            content="停用知识", status=MemoryStatus.ACTIVE, is_active=False,
        )
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer,
            content="已替代知识", status=MemoryStatus.SUPERSEDED, is_active=True,
        )
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer,
            content="已过期知识", status=MemoryStatus.EXPIRED, is_active=False,
        )
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer,
            content="尚未生效", status=MemoryStatus.ACTIVE, is_active=True,
            effective_from=now + timedelta(days=1),
        )
        CustomerKnowledgeItem.objects.create(
            therapist=self.therapist, customer=self.customer,
            content="已超有效期", status=MemoryStatus.ACTIVE, is_active=True,
            effective_from=now - timedelta(days=5),
            effective_to=now - timedelta(days=1),
        )
        with patch("apps.knowledge.services.get_embedding_provider", return_value=None):
            result = search_knowledge(self.customer.id, "能深蹲吗？")
        contents = [item["content"] for item in result]
        self.assertIn("左膝 ACL 重建术后禁止深蹲", contents)  # 原始有效 safety 保留
        for excluded in ("停用知识", "已替代知识", "已过期知识", "尚未生效", "已超有效期"):
            self.assertNotIn(excluded, contents)

    def test_all_safety_items_not_excluded_by_topk(self) -> None:
        """全部有效安全限制均不受普通知识 top-k 截断（F11）。"""
        now = timezone.now()
        for i in range(4):
            CustomerKnowledgeItem.objects.create(
                therapist=self.therapist,
                customer=self.customer,
                content=f"安全限制 {i}",
                category="safety",
                importance="normal",
                created_at=now - timedelta(minutes=i),
            )
        # 大量较新的普通知识
        for i in range(8):
            CustomerKnowledgeItem.objects.create(
                therapist=self.therapist, customer=self.customer,
                content=f"近期普通偏好 {i}",
                category="preference",
                importance="normal",
                created_at=now - timedelta(minutes=i),
            )
        with patch("apps.knowledge.services.get_embedding_provider", return_value=None):
            result = search_knowledge(self.customer.id, "深蹲注意事项", top_k=3)
        contents = [item["content"] for item in result]
        # 五条 safety 均保留；普通条目才按 top_k 补充。
        self.assertIn("左膝 ACL 重建术后禁止深蹲", contents)
        for i in range(4):
            self.assertIn(f"安全限制 {i}", contents)
        self.assertGreaterEqual(len(result), 5)
        self.assertTrue(all(item["matched"] == "safety" for item in result[:5]))

    def test_search_marks_keyword_when_no_embedding(self) -> None:
        """无 embedding 时明确标注为 keyword（有限检索），不伪装语义检索（F11）。"""
        with patch("apps.knowledge.services.get_embedding_provider", return_value=None):
            result = search_knowledge(self.customer.id, "偏好")
        self.assertTrue(result)
        self.assertIn("keyword", [item["matched"] for item in result])


class MemorySchemaNullToleranceTests(SimpleTestCase):
    """记忆/Episode 候选 schema：模型输出的 null 不拖垮同批其他候选。

    ``memory_evaluator``（阈值 0.6）与 ``episode_service``（阈值 0.7）都按置信度、
    白名单逐个过滤候选；若 null 让整批校验失败，合法候选也会一起丢失。
    """

    def test_null_candidate_fields_are_normalized(self) -> None:
        """分类/置信度缺失的候选归一为会被消费方跳过的安全值，不影响同批其他候选。"""
        result = MemoryEvaluationResult.model_validate(
            {
                "candidates": [
                    {"classification": None, "confidence": None},
                    {
                        "classification": "customer_memory",
                        "confidence": 0.9,
                        "memory_key": "exercise_preference.running",
                        "content": "喜欢跑步",
                    },
                ]
            }
        )
        skipped, kept = result.candidates
        self.assertEqual(skipped.classification, "ignore")
        self.assertEqual(skipped.confidence, 0.0)
        self.assertEqual(skipped.memory_type, "other")
        self.assertEqual(skipped.relation, "new")
        self.assertEqual(kept.classification, "customer_memory")
        self.assertEqual(kept.confidence, 0.9)

    def test_null_episode_confidence_is_normalized(self) -> None:
        """Episode 置信度缺失归零，由低置信阈值跳过，而不是整批丢弃。"""
        result = EpisodeEvaluationResult.model_validate(
            {
                "episodes": [
                    {
                        "episode_key": "running_preference_change",
                        "title": "跑步偏好调整",
                        "summary": "客户改为室内跑",
                        "confidence": None,
                    }
                ]
            }
        )
        self.assertEqual(result.episodes[0].confidence, 0.0)
