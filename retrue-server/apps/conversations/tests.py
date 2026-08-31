"""统一 AI 会话、客户隔离与记忆冲突评估测试。"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.conversations.models import Conversation, Message
from apps.conversations.context_builder import build_conversation_context
from apps.customers.models import Customer
from apps.knowledge.models import CustomerKnowledgeItem, KnowledgeCandidate
from apps.knowledge.models import MemoryEpisode

User = get_user_model()


class _AnswerProvider:
    """会话测试用固定回答 provider。"""

    def chat(self, prompt: str, system: str | None = None) -> str:
        return "已结合客户上下文给出建议。"


class _MemoryProvider:
    """记忆评估测试用固定冲突输出 provider。"""

    def chat(self, prompt: str, system: str | None = None) -> str:
        return json.dumps(
            {
                "candidates": [
                    {
                        "classification": "customer_memory",
                        "memory_type": "dislike",
                        "memory_key": "exercise_preference.running",
                        "content": "客户目前不喜欢跑步",
                        "normalized_value": "不喜欢跑步",
                        "confidence": 0.95,
                        "importance_score": 3,
                        "evidence": "康复师明确表示客户已经不喜欢跑步",
                        "relation": "conflict",
                    }
                ]
            },
            ensure_ascii=False,
        )


class _SummaryProvider:
    """长对话测试用固定摘要 provider。"""

    def chat(self, prompt: str, system: str | None = None) -> str:
        return "已压缩的早期对话摘要"


class _EpisodeProvider:
    """Episode 测试用固定结构化输出。"""

    def chat(self, prompt: str, system: str | None = None) -> str:
        return json.dumps(
            {
                "episodes": [
                    {
                        "episode_key": "running_preference_change",
                        "title": "客户跑步偏好变化讨论",
                        "summary": "客户跑步兴趣下降，讨论后决定调整训练。",
                        "key_points": ["客户觉得跑步辛苦"],
                        "decisions": ["减少长时间跑步"],
                        "next_actions": ["确认户外跑偏好"],
                        "importance_score": 4,
                        "confidence": 0.92,
                    }
                ]
            },
            ensure_ascii=False,
        )


class ConversationApiTests(APITestCase):
    """覆盖会话创建、消息归档、数据隔离和冲突候选。"""

    def setUp(self) -> None:
        """创建两位康复师及各自客户。"""
        self.therapist = User.objects.create_user(username="conversation_t1", password="test12345")
        self.other = User.objects.create_user(username="conversation_t2", password="test12345")
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")
        self.client.force_login(self.therapist)

    def test_cannot_create_conversation_for_other_customer(self) -> None:
        """不能把会话绑定到其他康复师的客户。"""
        response = self.client.post(
            reverse("conversation-list-create"),
            {"customer": self.other_customer.id, "origin": "customer_detail"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.knowledge.memory_evaluator.get_provider", return_value=_MemoryProvider())
    @patch("apps.conversations.services.get_provider", return_value=_AnswerProvider())
    def test_send_message_archives_turn_and_creates_conflict_candidate(
        self, _answer_mock, _memory_mock
    ) -> None:
        """客户对话保存双方消息，并把偏好变化标记为冲突候选。"""
        old = CustomerKnowledgeItem.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            memory_type="preference",
            memory_key="exercise_preference.running",
            content="客户喜欢跑步",
            normalized_value="喜欢跑步",
        )
        conversation = Conversation.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            origin="customer_detail",
            conversation_type="customer_discussion",
        )
        response = self.client.post(
            reverse("conversation-message", args=[conversation.id]),
            {"content": "这个客户现在已经不喜欢跑步了"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Message.objects.filter(conversation=conversation).count(), 2)
        candidate = KnowledgeCandidate.objects.get()
        self.assertEqual(candidate.conflict_type, "conflict")
        self.assertEqual(candidate.conflict_memory_id, old.id)
        self.assertEqual(candidate.source_conversation_id, conversation.id)
        self.assertIsNotNone(candidate.source_message_id)

    def test_other_therapist_cannot_read_conversation(self) -> None:
        """会话只能由所属康复师读取。"""
        conversation = Conversation.objects.create(therapist=self.other, customer=self.other_customer)
        response = self.client.get(reverse("conversation-detail", args=[conversation.id]))
        self.assertEqual(response.status_code, 404)

    @patch("apps.conversations.summary_service.get_provider", return_value=_SummaryProvider())
    @patch("apps.conversations.services.get_provider", return_value=_AnswerProvider())
    def test_messages_over_ten_are_summarized_and_context_keeps_ten(
        self, _answer_mock, _summary_mock
    ) -> None:
        """超过 10 条时旧消息进入滚动摘要，上下文只保留最近 10 条。"""
        conversation = Conversation.objects.create(therapist=self.therapist)
        for index in range(10):
            Message.objects.create(
                conversation=conversation,
                role="user" if index % 2 == 0 else "assistant",
                content=f"历史消息 {index + 1}",
            )
        response = self.client.post(
            reverse("conversation-message", args=[conversation.id]),
            {"content": "第十一条用户消息"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        conversation.refresh_from_db()
        self.assertEqual(conversation.summary, "已压缩的早期对话摘要")
        self.assertIsNotNone(conversation.summarized_through_message_id)
        context = build_conversation_context(conversation)
        self.assertEqual(len(context["recent_messages"]), 10)
        self.assertEqual(context["conversation_summary"], "已压缩的早期对话摘要")

    @patch("apps.knowledge.episode_service.get_provider", return_value=_EpisodeProvider())
    def test_extract_confirmed_episode_enters_customer_context(self, _episode_mock) -> None:
        """主动提取只生成候选，确认后才作为 EPISODE 进入上下文。"""
        conversation = Conversation.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            summary="正在讨论客户跑步偏好变化",
        )
        Message.objects.create(
            conversation=conversation,
            role="user",
            content="客户现在不喜欢跑步，我们决定减少跑步训练",
        )
        extract_response = self.client.post(
            reverse("conversation-episode-extract", args=[conversation.id]),
            {},
            format="json",
        )
        self.assertEqual(extract_response.status_code, 200)
        episode = MemoryEpisode.objects.get()
        self.assertEqual(episode.status, "candidate")

        decide_response = self.client.post(
            reverse("memory-episode-decide", args=[episode.id]),
            {"action": "confirm"},
            format="json",
        )
        self.assertEqual(decide_response.status_code, 200)
        context = build_conversation_context(conversation)
        self.assertEqual(len(context["episodes"]), 1)
        self.assertEqual(context["episodes"][0]["source"], "EPISODE")
