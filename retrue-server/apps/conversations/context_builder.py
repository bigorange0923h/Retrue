"""统一 AI 对话上下文组装器。"""

from __future__ import annotations

from apps.knowledge.memory_service import get_active_memory_context
from apps.knowledge.episode_service import get_active_episode_context


def build_conversation_context(conversation, recent_limit: int = 10) -> dict:
    """按事实、记忆和最近消息分区构造有界上下文。"""
    customer = conversation.customer
    facts = None
    memories: list[dict] = []
    episodes: list[dict] = []
    if customer is not None:
        facts = {
            "customer_id": customer.id,
            "name": customer.name,
            "main_issue": customer.main_issue,
            "sport": customer.sport,
            "status": customer.status,
        }
        memories = get_active_memory_context(conversation.therapist, customer.id, limit=10)
        episodes = get_active_episode_context(conversation.therapist, customer.id, limit=3)

    recent = list(conversation.messages.order_by("-created_at", "-id")[:recent_limit])
    recent.reverse()
    return {
        "scope": {
            "therapist_id": conversation.therapist_id,
            "customer_id": conversation.customer_id,
            "origin": conversation.origin,
            "conversation_type": conversation.conversation_type,
            "context_resource_type": conversation.context_resource_type,
            "context_resource_id": conversation.context_resource_id,
        },
        "facts": facts,
        "memories": memories,
        "episodes": episodes,
        "conversation_summary": conversation.summary,
        "recent_messages": [{"role": item.role, "content": item.content} for item in recent],
    }
