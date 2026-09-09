"""knowledge：知识向量化与 RAG 检索服务。

提供知识条目的向量化、检索与 RAG 回答能力：
    - embed_texts: 调用 Qwen embedding 将文本向量化。
    - build_knowledge_index: 为客户的生效知识条目生成并保存向量。
    - search_knowledge: 统一生命周期过滤后检索客户私有知识；安全限制/高重要性
      条目独立召回，不因相似度 top-k 截断被排除。
    - rag_answer: 检索知识并渲染 prompt，调用聊天模型生成回答。

生命周期语义与长期记忆一致：仅 ``status=active + is_active=True`` 且处于
``effective_from/effective_to`` 有效期内的条目可进入回答。

embedding 依赖 Qwen（text-embedding-v3），密钥缺失或调用失败时可降级为
无向量的纯文本兜底；调用方需明确向用户呈现“有限关键词/最近条目”而非语义检索。
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.apps import apps
from django.db.models import Q
from django.utils import timezone
from pgvector.django import CosineDistance

logger = logging.getLogger(__name__)

#: 检索返回中“安全/高重要条目”的召回上限。安全限制数量少，优先全量独立召回。
PROTECTED_RECALL_LIMIT = 8


def get_embedding_provider():
    """获取 embedding provider，失败时记录并返回 None（降级）。"""
    try:
        from apps.ai.providers.factory import get_embedding_provider as factory
        return factory()
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding provider 不可用：%s", exc)
        return None


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """将文本列表向量化。

    参数：
        texts: 待向量化文本列表。
    返回：
        向量列表；embedding 不可用时返回 None（调用方降级处理）。
    """
    provider = get_embedding_provider()
    if provider is None:
        return None
    try:
        return provider.embed(texts)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding 调用失败，降级跳过向量化：%s", exc)
        return None


def _effective_items(customer_id: int) -> "list":
    """返回处于有效生命周期内的知识条目列表。

    生命周期语义：``is_active=True``、``status=active``，且
    ``effective_from``（若有）不晚于当前、``effective_to``（若有）不早于当前。

    参数：
        customer_id: 客户 ID。
    返回：
        满足有效条件的 CustomerKnowledgeItem 查询结果（未切片）。
    """
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    now = timezone.now()
    return CustomerKnowledgeItem.objects.filter(
        customer_id=customer_id,
        is_active=True,
        status="active",
    ).filter(
        Q(effective_from__isnull=True) | Q(effective_from__lte=now),
        Q(effective_to__isnull=True) | Q(effective_to__gte=now),
    )


def build_knowledge_index(customer_id: int) -> int:
    """为指定客户的所有生效自由文本知识条目生成向量。

    只处理 ``memory_type=other``（自由文本/历史资料）且当前为空 embedding 的条目，
    避免把所有结构化短记忆重复当作 RAG 文档。生命周期过滤与检索一致。

    参数：
        customer_id: 客户 ID。
    返回：
        成功向量化的条目数；embedding 不可用时返回 0。
    """
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    items = list(
        _effective_items(customer_id).filter(memory_type="other").order_by("id")
    )
    pending = [item for item in items if item.embedding is None]
    if not pending:
        return 0
    vectors = embed_texts([item.content for item in pending])
    if vectors is None:
        return 0
    updated = 0
    for item, vector in zip(pending, vectors):
        item.embedding = vector
        item.save(update_fields=["embedding", "updated_at"])
        updated += 1
    logger.info("客户 %s 知识向量化完成 %s 条", customer_id, updated)
    return updated


def search_knowledge(customer_id: int, query: str, top_k: int = 5) -> list[dict]:
    """检索客户私有知识：安全/高重要条目独立召回 + 相似文本合并。

    检索只返回有效生命周期内的条目。安全限制（safety 或 high）先独立按
    相关度/最近取 ``PROTECTED_RECALL_LIMIT``，避免旧的但重要的安全限制被
    相似度 top-k 或最近 top-k 排除；随后再补足相关自由文本到 ``top_k``。

    参数：
        customer_id: 客户 ID。
        query: 用户问题。
        top_k: 返回条数。
    返回：
        知识片段字典列表，含 content、category、importance、similarity。
        每条含 ``matched``（vector=语义检索 / keyword=有限关键词或最近兜底），
        供调用方区分检索方式，不伪装已做语义检索。
    """
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    base = _effective_items(customer_id)

    query_vector = None
    provider = get_embedding_provider()
    if provider is not None:
        try:
            embedded = provider.embed([query])
            query_vector = embedded[0] if embedded else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("查询向量化失败，使用无向量兜底：%s", exc)
            query_vector = None

    # 1) 安全限制 / 高重要条目独立召回（不因 top-k 被排除）
    protected_qs = base.filter(Q(category="safety") | Q(importance="high"))
    protected = list(protected_qs.order_by("category", "-created_at")[:PROTECTED_RECALL_LIMIT])
    protected_ids = {item.id for item in protected}

    # 2) 其余相关文本按语义或最近补充
    rest = base.exclude(id__in=protected_ids)
    if query_vector is not None:
        related = list(
            rest.exclude(embedding__isnull=True)
            .annotate(similarity=CosineDistance("embedding", query_vector))
            .order_by("similarity")
        )
        related = related[: max(top_k - len(protected), 0)]
        related_objs = protected + related
        matched = "vector"
    else:
        related = list(rest.order_by("-created_at")[: max(top_k - len(protected), 0)])
        related_objs = protected + related
        matched = "keyword"

    # 排序：安全/高重要在前，其余按相似度/最近；总条数不超过 top_k。
    items = sorted(
        related_objs,
        key=lambda it: (0 if it.importance == "high" or it.category == "safety" else 1),
    )[:top_k]

    result = []
    for item in items:
        similarity = getattr(item, "similarity", None)
        result.append(
            {
                "content": item.content,
                "category": item.category,
                "importance": item.importance,
                "similarity": round(float(similarity), 4) if similarity is not None else None,
                "matched": matched,
            }
        )
    return result



def rag_answer(customer_id: int, question: str, therapist_name: str = "", customer_name: str = ""):
    """基于客户私有知识库生成 RAG 回答。

    检索客户知识 → 渲染 rag_system prompt → 调用聊天模型。
    若无可用聊天 provider 或检索失败，返回明确的降级信息，而非静默出错。

    返回：
        (answer, used_knowledge) 二元组。
    """
    from apps.ai.providers.factory import get_provider
    from apps.ai.prompts.loader import load_prompt, render_prompt

    chunks = search_knowledge(customer_id, question, top_k=5)
    if not chunks:
        answer = "知识库中暂未检索到与该问题相关的客户信息，建议直接向康复师确认。"
        return answer, []

    knowledge_text = "\n".join(f"- [{item['category']}] {item['content']}" for item in chunks)
    prompt = render_prompt(
        "rag_answer",
        therapist_name=therapist_name or "康复师",
        customer_name=customer_name or "该客户",
        knowledge_chunks=knowledge_text,
        question=question,
    )

    try:
        provider = get_provider()
        answer = provider.chat(prompt, system=load_prompt("rag_system"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG 回答调用失败：%s", exc)
        answer = "AI 暂时无法生成回答，请稍后重试，或直接咨询康复师。"
    return answer, chunks
