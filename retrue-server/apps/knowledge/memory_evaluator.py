"""从客户相关对话中提取长期记忆候选并识别冲突。"""

from __future__ import annotations

import json
import logging
import re

from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.factory import get_provider
from apps.ai.schemas.memory import MemoryEvaluationResult
from apps.knowledge.memory_service import normalize_memory_value
from apps.knowledge.models import (
    CustomerKnowledgeItem,
    KnowledgeCandidate,
    MemoryConflictType,
    MemoryStatus,
)

logger = logging.getLogger(__name__)


def evaluate_message_for_memory(message) -> list[KnowledgeCandidate]:
    """评估一条客户会话中的康复师消息，返回需人工确认的候选。

    正式业务事实、临时状态、低可信推测和重复内容不会生成长期候选；
    同一 memory_key 的不同内容会关联当前有效记忆，供康复师决策。
    """
    conversation = message.conversation
    customer = conversation.customer
    if customer is None or message.role != "user":
        return []

    active = list(
        CustomerKnowledgeItem.objects.filter(
            therapist=conversation.therapist,
            customer=customer,
            status=MemoryStatus.ACTIVE,
            is_active=True,
        ).order_by("-importance_score", "-updated_at")[:30]
    )
    active_payload = [
        {
            "id": item.id,
            "memory_type": item.memory_type,
            "memory_key": item.memory_key,
            "content": item.content,
        }
        for item in active
    ]
    prompt = render_prompt(
        "memory_evaluator",
        customer_name=customer.name,
        active_memories=json.dumps(active_payload, ensure_ascii=False),
        message_content=message.content,
    )
    try:
        raw = get_provider().chat(prompt, system=load_prompt("memory_evaluator_system"))
        result = MemoryEvaluationResult.model_validate_json(_clean_json(raw))
    except Exception as exc:  # noqa: BLE001 - 评估失败不能影响正常对话
        logger.warning("对话记忆评估失败，已跳过本轮候选：%s", exc)
        return []

    created: list[KnowledgeCandidate] = []
    allowed = {"customer_memory", "therapist_observation"}
    category_map = {
        "preference": "preference",
        "dislike": "preference",
        "concern": "medical",
        "background": "medical",
    }
    for extracted in result.candidates:
        if extracted.classification not in allowed or extracted.confidence < 0.6:
            continue
        if not extracted.memory_key or not extracted.content.strip():
            continue
        normalized = extracted.normalized_value or normalize_memory_value(extracted.content)
        current = next(
            (
                item for item in active
                if item.memory_key == extracted.memory_key
            ),
            None,
        )
        if current and current.normalized_value == normalize_memory_value(normalized):
            continue
        if KnowledgeCandidate.objects.filter(
            therapist=conversation.therapist,
            customer=customer,
            source_message=message,
            memory_key=extracted.memory_key,
        ).exists():
            continue

        relation_map = {
            "conflict": MemoryConflictType.CONFLICT,
            "conditional": MemoryConflictType.CONDITIONAL,
            "supplement": MemoryConflictType.SUPPLEMENT,
        }
        conflict_type = relation_map.get(extracted.relation, MemoryConflictType.NONE)
        if current and conflict_type == MemoryConflictType.NONE:
            conflict_type = MemoryConflictType.CONFLICT

        candidate = KnowledgeCandidate.objects.create(
            therapist=conversation.therapist,
            customer=customer,
            content=extracted.content.strip(),
            category=category_map.get(extracted.memory_type, "other"),
            memory_type=extracted.memory_type,
            memory_key=extracted.memory_key,
            normalized_value=normalized,
            confidence=extracted.confidence,
            importance_score=extracted.importance_score,
            evidence=extracted.evidence,
            conflict_type=conflict_type,
            conflict_memory=current,
            source_conversation=conversation,
            source_message=message,
            source_ref=f"{conversation.get_origin_display()}会话 #{conversation.id}，消息 #{message.id}",
        )
        created.append(candidate)
    return created


def _clean_json(value: str) -> str:
    """移除模型可能返回的 Markdown JSON 围栏。"""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
