"""统一 AI 会话发送服务。"""

from __future__ import annotations

import json
import logging

from django.utils import timezone

from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.factory import get_provider
from apps.conversations.context_builder import build_conversation_context
from apps.conversations.models import ConversationStatus, Message, MessageRole
from apps.conversations.summary_service import refresh_conversation_summary
from apps.knowledge.memory_evaluator import evaluate_message_for_memory

logger = logging.getLogger(__name__)


def send_user_message(conversation, content: str) -> tuple[Message, Message, list]:
    """保存用户消息、生成并保存 AI 回复，再执行非阻断的记忆候选评估。"""
    if conversation.status != ConversationStatus.ACTIVE:
        raise ValueError("该会话已经结束")
    user_message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.USER,
        content=content.strip(),
    )
    if not conversation.title:
        conversation.title = content.strip()[:40]
        conversation.save(update_fields=["title", "updated_at"])

    context = build_conversation_context(conversation)
    prompt = render_prompt(
        "assistant_chat",
        context=json.dumps(context, ensure_ascii=False),
        question=content.strip(),
    )
    answer = get_provider().chat(prompt, system=load_prompt("assistant_system"))
    assistant_message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        content=answer,
    )
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["updated_at"])

    refresh_conversation_summary(conversation, recent_limit=10)
    # 候选评估失败不会回滚已经完成的正常对话。
    candidates = evaluate_message_for_memory(user_message)
    return user_message, assistant_message, candidates
