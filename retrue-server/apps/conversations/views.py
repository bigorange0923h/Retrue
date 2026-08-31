"""统一 AI 会话接口。"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.conversations.models import Conversation
from apps.conversations.serializers import ConversationSerializer, MessageSerializer, SendMessageSerializer
from apps.conversations.services import send_user_message
from apps.knowledge.serializers import KnowledgeCandidateSerializer
from apps.knowledge.episode_service import refresh_episode_candidates
from apps.knowledge.serializers import MemoryEpisodeSerializer


class ConversationListCreateView(APIView):
    """查询当前康复师会话或创建新会话。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """返回当前康复师最近 50 个会话，可按客户筛选。"""
        queryset = Conversation.objects.filter(therapist=request.user).select_related("customer")
        customer_id = request.query_params.get("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        return ApiResponse.ok(
            ConversationSerializer(queryset[:50], many=True).data,
            message="查询会话成功",
        )

    def post(self, request):
        """创建会话并校验客户归属。"""
        serializer = ConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        customer = data.pop("customer", None)
        if customer is not None and customer.therapist_id != request.user.id:
            return ApiResponse.error("客户不存在或无权访问", 403)
        conversation = Conversation.objects.create(
            therapist=request.user,
            customer=customer,
            **data,
        )
        return ApiResponse.ok(ConversationSerializer(conversation).data, message="会话已创建")


class ConversationDetailView(APIView):
    """读取一条会话及其消息。"""

    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id: int):
        """仅允许会话所属康复师读取。"""
        conversation = Conversation.objects.filter(
            therapist=request.user, id=conversation_id
        ).prefetch_related("messages").first()
        if conversation is None:
            return ApiResponse.error("会话不存在或无权访问", 404)
        return ApiResponse.ok(ConversationSerializer(conversation).data, message="查询会话成功")


class ConversationMessageView(APIView):
    """向现有会话发送一条用户消息。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id: int):
        """保存对话双方消息并返回本轮产生的记忆候选。"""
        conversation = Conversation.objects.filter(
            therapist=request.user, id=conversation_id
        ).select_related("customer", "therapist").first()
        if conversation is None:
            return ApiResponse.error("会话不存在或无权访问", 404)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user_message, assistant_message, candidates = send_user_message(
                conversation, serializer.validated_data["content"]
            )
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        except Exception:
            return ApiResponse.error("AI 助手暂时无法回答，请稍后重试", 500)
        return ApiResponse.ok(
            {
                "conversation_id": conversation.id,
                "user_message": MessageSerializer(user_message).data,
                "assistant_message": MessageSerializer(assistant_message).data,
                "memory_candidates": KnowledgeCandidateSerializer(candidates, many=True).data,
            },
            message="AI 回复成功",
        )


class ConversationEpisodeExtractView(APIView):
    """由康复师主动触发当前会话的 Episode 候选提取。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id: int):
        """提取事件但不自动激活，仍需康复师确认。"""
        conversation = Conversation.objects.filter(
            therapist=request.user,
            id=conversation_id,
        ).select_related("customer", "therapist").first()
        if conversation is None:
            return ApiResponse.error("会话不存在或无权访问", 404)
        episodes = refresh_episode_candidates(conversation, force=True)
        return ApiResponse.ok(
            MemoryEpisodeSerializer(episodes, many=True).data,
            message=f"已生成 {len(episodes)} 条历史讨论事件候选",
        )
