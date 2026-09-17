"""统一 AI 会话接口。"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.conversations.models import Conversation
from apps.conversations.serializers import ConversationSerializer


class ConversationListCreateView(APIView):
    """创建当前康复师的可追溯会话。"""

    permission_classes = [IsAuthenticated]

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
