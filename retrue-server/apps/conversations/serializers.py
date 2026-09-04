"""统一 AI 会话接口序列化器。"""

from rest_framework import serializers

from apps.conversations.models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    """输出会话消息。"""

    class Meta:
        model = Message
        fields = ["id", "role", "content", "metadata", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    """创建和输出会话，不允许客户端指定康复师。"""

    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id", "customer", "origin", "conversation_type", "context_resource_type",
            "context_resource_id", "title", "summary", "summarized_through_message_id",
            "summary_updated_at", "context_data", "episode_analyzed_through_message_id", "status", "started_at", "ended_at",
            "created_at", "updated_at", "messages",
        ]
        read_only_fields = [
            "summary", "summarized_through_message_id", "summary_updated_at", "context_data", "status",
            "episode_analyzed_through_message_id", "started_at", "ended_at", "created_at", "updated_at",
        ]


class SendMessageSerializer(serializers.Serializer):
    """发送用户消息输入。"""

    content = serializers.CharField(max_length=8000, allow_blank=False, trim_whitespace=True)
