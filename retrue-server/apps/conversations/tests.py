"""统一 AI 会话的客户隔离测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.conversations.models import Conversation
from apps.customers.models import Customer

User = get_user_model()


class ConversationApiTests(APITestCase):
    """覆盖会话创建与数据隔离。"""

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

    def test_other_therapist_cannot_read_conversation(self) -> None:
        """会话只能由所属康复师读取。"""
        conversation = Conversation.objects.create(therapist=self.other, customer=self.other_customer)
        response = self.client.get(reverse("conversation-detail", args=[conversation.id]))
        self.assertEqual(response.status_code, 404)

    def test_legacy_direct_message_routes_are_not_available(self) -> None:
        """旧的直接模型调用与 Episode 提取路由必须删除。"""
        conversation = Conversation.objects.create(therapist=self.therapist, customer=self.customer)
        message_response = self.client.post(f"/api/conversations/{conversation.id}/messages/", {}, format="json")
        episode_response = self.client.post(f"/api/conversations/{conversation.id}/episodes/extract/", {}, format="json")
        self.assertEqual(message_response.status_code, 404)
        self.assertEqual(episode_response.status_code, 404)
