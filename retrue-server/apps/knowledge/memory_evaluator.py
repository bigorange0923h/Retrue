"""从客户相关对话中提取长期记忆候选并识别冲突。"""

from __future__ import annotations

import json
import logging
import re

from django.db.models import Q
from django.utils import timezone

from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.factory import get_provider
from apps.ai.schemas.memory import MemoryEvaluationResult
from apps.knowledge.memory_service import normalize_memory_value
from apps.knowledge.models import (
    CandidateStatus,
    CustomerKnowledgeItem,
    KnowledgeCandidate,
    MemoryConflictType,
    MemoryStatus,
)

logger = logging.getLogger(__name__)


def evaluate_message_for_memory(message, *, raise_errors=False) -> list[KnowledgeCandidate]:
    """评估一条客户会话中的康复师消息，返回需人工确认的候选。

    正式业务事实、临时状态、低可信推测和重复内容不会生成长期候选；
    同一 memory_key 的不同内容会关联当前有效记忆，供康复师决策。
    """
    conversation = message.conversation
    customer = conversation.customer
    if customer is None or message.role != "user":
        return []

    now = timezone.now()
    active = list(
        CustomerKnowledgeItem.objects.filter(
            therapist=conversation.therapist,
            customer=customer,
            status=MemoryStatus.ACTIVE,
            is_active=True,
        )
        .filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=now),
            Q(effective_to__isnull=True) | Q(effective_to__gte=now),
        )
        .order_by("-importance_score", "-updated_at")[:30]
    )
    active_payload = [
        {
            "id": item.id,
            "reference_status": "active_memory",
            "memory_type": item.memory_type,
            "memory_key": item.memory_key,
            "content": item.content,
        }
        for item in active
    ]
    open_candidates = list(
        KnowledgeCandidate.objects.filter(
            therapist=conversation.therapist,
            customer=customer,
            status__in=[CandidateStatus.PENDING, CandidateStatus.DEFERRED],
        )
        .only("id", "memory_type", "memory_key", "content", "normalized_value", "status")
        .order_by("-suggested_at")[:30]
    )
    reference_payload = active_payload + [
        {
            "id": item.id,
            "reference_status": "open_candidate",
            "memory_type": item.memory_type,
            "memory_key": item.memory_key,
            "content": item.content,
        }
        for item in open_candidates
    ]
    prompt = render_prompt(
        "memory_evaluator",
        customer_name=customer.name,
        active_memories=json.dumps(reference_payload, ensure_ascii=False),
        message_content=message.content,
    )
    try:
        raw = get_provider().chat(prompt, system=load_prompt("memory_evaluator_system"))
        result = MemoryEvaluationResult.model_validate_json(_clean_json(raw))
    except Exception as exc:  # noqa: BLE001 - 评估失败不能影响正常对话
        if raise_errors:
            raise
        logger.warning("对话记忆评估失败，已跳过本轮候选：%s", exc)
        return []

    created: list[KnowledgeCandidate] = []
    classification_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}

    def record_outcome(name: str) -> None:
        """记录不含原文的评估统计，便于定位候选为何未生成。"""
        outcome_counts[name] = outcome_counts.get(name, 0) + 1

    allowed = {"customer_memory", "therapist_observation"}
    category_map = {
        "preference": "preference",
        "dislike": "preference",
        "concern": "medical",
        "background": "medical",
    }
    seen_in_result: set[tuple[str, str]] = set()
    for extracted in result.candidates:
        classification_counts[extracted.classification] = classification_counts.get(extracted.classification, 0) + 1
        if extracted.classification not in allowed or extracted.confidence < 0.6:
            record_outcome("filtered_classification_or_confidence")
            continue
        if not extracted.memory_key or not extracted.content.strip():
            record_outcome("filtered_missing_key_or_content")
            continue
        normalized = normalize_memory_value(extracted.normalized_value or extracted.content)
        duplicate_signature = (extracted.memory_type, normalized)
        if duplicate_signature in seen_in_result:
            record_outcome("skipped_duplicate_in_result")
            continue
        seen_in_result.add(duplicate_signature)
        current = next(
            (
                item for item in active
                if item.memory_key == extracted.memory_key
            ),
            None,
        )
        if _has_same_memory(active, extracted.memory_key, extracted.memory_type, normalized):
            record_outcome("skipped_duplicate_active")
            continue
        if _has_same_memory(open_candidates, extracted.memory_key, extracted.memory_type, normalized):
            record_outcome("skipped_duplicate_open_candidate")
            continue
        if extracted.relation == "duplicate":
            record_outcome("skipped_duplicate_model")
            continue
        if KnowledgeCandidate.objects.filter(
            therapist=conversation.therapist,
            customer=customer,
            source_message=message,
            memory_key=extracted.memory_key,
        ).exists():
            record_outcome("skipped_duplicate_source")
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
        record_outcome("created")
    logger.info(
        "对话记忆评估完成：customer_id=%s classifications=%s outcomes=%s created=%s",
        customer.id,
        classification_counts,
        outcome_counts,
        len(created),
    )
    return created


def _has_same_memory(items, memory_key: str, memory_type: str, normalized_value: str) -> bool:
    """按稳定键优先、类型兜底识别同一长期信息，防止模型换 key 后重复建候选。"""
    for item in items:
        item_normalized = normalize_memory_value(item.normalized_value or item.content)
        if item_normalized != normalized_value:
            continue
        if item.memory_key == memory_key or item.memory_type == memory_type:
            return True
    return False


def _clean_json(value: str) -> str:
    """移除模型可能返回的 Markdown JSON 围栏。"""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
