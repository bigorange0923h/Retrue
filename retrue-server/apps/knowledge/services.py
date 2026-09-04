"""knowledge：知识向量化与 RAG 检索服务。

提供知识条目的向量化、检索与 RAG 回答能力：
    - embed_texts: 调用 Qwen embedding 将文本向量化。
    - build_knowledge_index: 为客户的激活知识条目生成并保存向量。
    - search_knowledge: 用余弦相似度检索客户私有知识，安全限制优先。
    - rag_answer: 检索知识并渲染 prompt，调用聊天模型生成回答。

embedding 依赖 Qwen（text-embedding-v3），密钥缺失或调用失败时可降级为
无向量的纯文本兜底（不影响知识条目 CRUD）。
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.apps import apps
from pgvector.django import CosineDistance

logger = logging.getLogger(__name__)


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


def build_knowledge_index(customer_id: int) -> int:
    """为指定客户的所有激活知识条目生成向量。

    参数：
        customer_id: 客户 ID。
    返回：
        成功向量化的条目数；embedding 不可用时返回 0。
    """
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    items = list(
        # 结构化长期记忆数量很少，Context Builder 直接读取即可；只为自由文本/历史
        # 数据保留向量化能力，避免把所有短记忆错误地当作 RAG 文档。
        CustomerKnowledgeItem.objects.filter(
            customer_id=customer_id,
            is_active=True,
            status="active",
            memory_type="other",
        ).order_by("id")
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
    """检索客户私有知识，按相关度排序，安全限制优先。

    参数：
        customer_id: 客户 ID。
        query: 用户问题。
        top_k: 返回条数。
    返回：
        知识片段字典列表，含 content、category、importance、similarity。
    """
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    query_vector = None
    provider = get_embedding_provider()
    if provider is not None:
        try:
            embedded = provider.embed([query])
            query_vector = embedded[0] if embedded else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("查询向量化失败，使用无向量兜底：%s", exc)
            query_vector = None

    if query_vector is not None:
        return _search_by_vector(customer_id, query_vector, top_k)
    return _search_fallback(customer_id, top_k)


def _search_by_vector(customer_id: int, query_vector: list[float], top_k: int) -> list[dict]:
    """基于向量余弦相似度检索。"""
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    qs = (
        CustomerKnowledgeItem.objects.filter(customer_id=customer_id, is_active=True)
        .exclude(embedding__isnull=True)
        .annotate(similarity=CosineDistance("embedding", query_vector))
        .order_by("similarity")[:top_k]
    )
    # 安全限制类高重要性条目优先展示（放大其在上下文中的排序权重）
    items = list(qs)
    items.sort(key=lambda it: (0 if it.importance == "high" else 1))
    return [
        {
            "content": item.content,
            "category": item.category,
            "importance": item.importance,
            "similarity": round(float(item.similarity), 4),
        }
        for item in items
    ]


def _search_fallback(customer_id: int, top_k: int) -> list[dict]:
    """无向量可用时的兜底检索：高重要级别优先 + 最近创建。

    注意：importance 为字符串（high/normal），不能直接按字母序排序，
    需显式按 high 优先排序。
    """
    CustomerKnowledgeItem = apps.get_model("knowledge", "CustomerKnowledgeItem")
    qs = list(
        CustomerKnowledgeItem.objects.filter(customer_id=customer_id, is_active=True).order_by(
            "-created_at"
        )[:top_k]
    )
    # high 优先，再按最近创建
    qs.sort(key=lambda it: (0 if it.importance == "high" else 1))
    return [
        {
            "content": item.content,
            "category": item.category,
            "importance": item.importance,
            "similarity": None,
        }
        for item in qs
    ]


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
