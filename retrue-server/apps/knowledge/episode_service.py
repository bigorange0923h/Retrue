"""Memory Episode 提取、确认后检索与上下文构造。"""

from __future__ import annotations

import json
import logging
import re

from django.utils import timezone

from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.factory import get_provider
from apps.ai.schemas.memory import EpisodeEvaluationResult
from apps.knowledge.models import EpisodeStatus, MemoryEpisode

logger = logging.getLogger(__name__)


def refresh_episode_candidates(conversation, *, force: bool = False, min_new_messages: int = 10) -> list[MemoryEpisode]:
    """从会话摘要和最近消息中提取可确认的历史事件候选。

    自动模式每新增至少 10 条已压缩消息才执行，避免每轮重复调用模型；
    force 用于康复师主动触发。成功分析后记录进度，即使没有候选也不重复分析。
    """
    if conversation.customer_id is None:
        return []
    latest_message = conversation.messages.order_by("-id").first()
    if latest_message is None:
        return []

    analyzed_id = conversation.episode_analyzed_through_message_id or 0
    coverage_id = conversation.summarized_through_message_id or latest_message.id
    newly_covered = conversation.messages.filter(id__gt=analyzed_id, id__lte=coverage_id).count()
    if not force and newly_covered < min_new_messages:
        return []

    recent = list(conversation.messages.order_by("-id")[:10])
    recent.reverse()
    existing_keys = list(
        MemoryEpisode.objects.filter(conversation=conversation).values_list("episode_key", flat=True)
    )
    prompt = render_prompt(
        "episode_evaluator",
        customer_name=conversation.customer.name,
        conversation_summary=conversation.summary or "暂无摘要",
        recent_messages=json.dumps(
            [{"role": item.role, "content": item.content} for item in recent],
            ensure_ascii=False,
        ),
        existing_episode_keys=json.dumps(existing_keys, ensure_ascii=False),
    )
    try:
        raw = get_provider().chat(prompt, system=load_prompt("episode_evaluator_system"))
        result = EpisodeEvaluationResult.model_validate_json(_clean_json(raw))
    except Exception as exc:  # noqa: BLE001 - Episode 失败不影响对话
        logger.warning("会话 %s Episode 提取失败：%s", conversation.id, exc)
        return []

    first_message_id = conversation.messages.order_by("id").values_list("id", flat=True).first()
    created: list[MemoryEpisode] = []
    for extracted in result.episodes:
        if extracted.confidence < 0.7:
            continue
        episode, was_created = MemoryEpisode.objects.get_or_create(
            conversation=conversation,
            episode_key=extracted.episode_key,
            defaults={
                "therapist": conversation.therapist,
                "customer": conversation.customer,
                "title": extracted.title,
                "summary": extracted.summary,
                "key_points": extracted.key_points,
                "decisions": extracted.decisions,
                "next_actions": extracted.next_actions,
                "importance_score": extracted.importance_score,
                "confidence": extracted.confidence,
                "status": EpisodeStatus.CANDIDATE,
                "source_start_message_id": first_message_id,
                "source_end_message_id": latest_message.id,
            },
        )
        if was_created:
            created.append(episode)

    conversation.episode_analyzed_through_message_id = coverage_id
    conversation.save(update_fields=["episode_analyzed_through_message_id", "updated_at"])
    return created


def get_active_episode_context(therapist, customer_id: int, limit: int = 3) -> list[dict]:
    """返回当前客户最重要且最近的已确认 Episode。"""
    episodes = MemoryEpisode.objects.filter(
        therapist=therapist,
        customer_id=customer_id,
        status=EpisodeStatus.ACTIVE,
    ).order_by("-importance_score", "-created_at")[:limit]
    return [
        {
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "key_points": item.key_points,
            "decisions": item.decisions,
            "next_actions": item.next_actions,
            "source": "EPISODE",
        }
        for item in episodes
    ]


def decide_episode(episode: MemoryEpisode, therapist, action: str) -> MemoryEpisode:
    """由康复师确认或拒绝 Episode 候选。"""
    if episode.status != EpisodeStatus.CANDIDATE:
        raise ValueError("该历史事件候选已处理")
    if action not in {"confirm", "reject"}:
        raise ValueError("不支持的处理方式")
    episode.status = EpisodeStatus.ACTIVE if action == "confirm" else EpisodeStatus.REJECTED
    episode.decided_by = therapist
    episode.decided_at = timezone.now()
    episode.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return episode


def _clean_json(value: str) -> str:
    """移除模型可能返回的 Markdown JSON 围栏。"""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
