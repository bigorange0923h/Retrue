"""长期记忆写入与上下文服务。

LLM 或接口只能提交候选；本模块负责规范化、去重、替代和上下文裁剪，
避免把临时信息或已失效信息带入 AI 回答。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.knowledge.models import MemoryStatus

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from apps.knowledge.models import CustomerKnowledgeItem, KnowledgeCandidate


def normalize_memory_value(value: str) -> str:
    """将记忆内容转换为稳定的轻量去重键。"""
    return re.sub(r"\s+", "", value).strip().lower()


def confirm_candidate(
    candidate: "KnowledgeCandidate", therapist: "AbstractUser", *, supersede_existing: bool = False
) -> tuple["CustomerKnowledgeItem", bool]:
    """确认候选记忆并执行去重或明确替代。

    返回 (正式记忆, 是否新建)。同类型、同键且内容一致时仅刷新确认时间；
    同键内容不同时，只有康复师明确选择替代才会使旧记忆失效。
    """
    from apps.knowledge.models import CustomerKnowledgeItem, MemoryStatus

    normalized = candidate.normalized_value or normalize_memory_value(candidate.content)
    active = CustomerKnowledgeItem.objects.filter(
        therapist=therapist,
        customer=candidate.customer,
        status=MemoryStatus.ACTIVE,
    )
    if candidate.memory_key:
        active = active.filter(memory_key=candidate.memory_key)
    else:
        active = active.filter(memory_type=candidate.memory_type)

    duplicate = active.filter(normalized_value=normalized).first()
    now = timezone.now()
    if duplicate:
        duplicate.last_confirmed_at = now
        duplicate.confidence = max(duplicate.confidence, candidate.confidence)
        duplicate.save(update_fields=["last_confirmed_at", "confidence", "updated_at"])
        return duplicate, False

    prior = active.first() if candidate.memory_key else None
    if prior and supersede_existing:
        prior.status = MemoryStatus.SUPERSEDED
        prior.is_active = False
        prior.effective_to = now
        prior.save(update_fields=["status", "is_active", "effective_to", "updated_at"])
    else:
        prior = None

    item = CustomerKnowledgeItem.objects.create(
        therapist=therapist,
        customer=candidate.customer,
        category=candidate.category,
        memory_type=candidate.memory_type,
        memory_key=candidate.memory_key,
        content=candidate.content,
        normalized_value=normalized,
        source="ai_confirmed",
        source_type="conversation" if candidate.source_conversation_id else "candidate",
        source_id=str(candidate.source_conversation_id or candidate.id),
        source_message_id=str(candidate.source_message_id or ""),
        confidence=candidate.confidence,
        importance_score=candidate.importance_score,
        confirmed_by_user=True,
        status=MemoryStatus.ACTIVE,
        is_active=True,
        effective_from=now,
        last_confirmed_at=now,
        supersedes_memory=prior,
        created_by=therapist,
        updated_by=therapist,
    )
    return item, True


def get_active_memory_context(therapist: "AbstractUser", customer_id: int, limit: int = 10) -> list[dict]:
    """取得可安全注入 AI 的有效长期记忆，限制数量控制 token。

    生命周期过滤与知识检索一致：仅 ``status=active + is_active=True`` 且处于
    ``effective_from/effective_to`` 有效期内的记忆可注入 AI 上下文。
    """
    from django.db.models import Q
    from django.utils import timezone
    from apps.knowledge.models import CustomerKnowledgeItem

    now = timezone.now()
    items = (
        CustomerKnowledgeItem.objects.filter(
            therapist=therapist, customer_id=customer_id, status=MemoryStatus.ACTIVE, is_active=True
        )
        .filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=now),
            Q(effective_to__isnull=True) | Q(effective_to__gte=now),
        )
        .order_by("-importance_score", "-last_confirmed_at", "-created_at")[:limit]
    )
    return [
        {
            "type": item.memory_type,
            "content": item.content,
            "importance": item.importance_score,
            "source": "MEMORY",
        }
        for item in items
    ]
