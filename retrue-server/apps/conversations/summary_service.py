"""长对话滚动摘要服务。"""

from __future__ import annotations

import json
import logging

from django.utils import timezone

from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.factory import get_provider

logger = logging.getLogger(__name__)


def refresh_conversation_summary(conversation, recent_limit: int = 10) -> bool:
    """将最近消息窗口之外的新旧消息增量合并进会话摘要。

    返回是否成功更新摘要。失败时保留完整消息与旧摘要，不影响正常对话。
    """
    recent_ids = list(
        conversation.messages.order_by("-created_at", "-id").values_list("id", flat=True)[:recent_limit]
    )
    if len(recent_ids) < recent_limit:
        return False
    oldest_recent_id = min(recent_ids)
    pending = conversation.messages.filter(id__lt=oldest_recent_id)
    if conversation.summarized_through_message_id is not None:
        pending = pending.filter(id__gt=conversation.summarized_through_message_id)
    pending_messages = list(pending.order_by("id"))
    if not pending_messages:
        return False

    prompt = render_prompt(
        "conversation_summary",
        existing_summary=conversation.summary or "暂无摘要",
        new_messages=json.dumps(
            [{"role": item.role, "content": item.content} for item in pending_messages],
            ensure_ascii=False,
        ),
    )
    try:
        summary = get_provider().chat(prompt, system=load_prompt("conversation_summary_system")).strip()
    except Exception as exc:  # noqa: BLE001 - 摘要失败不得影响对话
        logger.warning("会话 %s 自动摘要失败：%s", conversation.id, exc)
        return False
    if not summary:
        return False

    conversation.summary = summary[:4000]
    conversation.summarized_through_message_id = pending_messages[-1].id
    conversation.summary_updated_at = timezone.now()
    conversation.save(
        update_fields=["summary", "summarized_through_message_id", "summary_updated_at", "updated_at"]
    )
    # 每累计至少 10 条已压缩消息再评估 Episode，减少额外模型调用。
    from apps.knowledge.episode_service import refresh_episode_candidates

    refresh_episode_candidates(conversation, min_new_messages=10)
    return True
