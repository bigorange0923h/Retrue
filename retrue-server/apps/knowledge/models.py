"""knowledge：客户私有康复知识库模型。

客户私有知识库优先保存经康复师确认的高价值信息，按"康复师 + 客户"严格隔离。
包含两类实体：
    - CustomerKnowledgeItem：正式知识条目（含 pgvector 向量字段，用于 RAG 检索）。
    - KnowledgeCandidate：AI 建议的候选记忆，需康复师确认后才转为正式知识。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class KnowledgeCategory(models.TextChoices):
    """知识条目分类。"""

    MEDICAL = "medical", "医疗与康复背景"
    SAFETY = "safety", "安全限制"
    RECOVERY = "recovery", "康复过程"
    PREFERENCE = "preference", "个体化偏好"
    OTHER = "other", "其他"


class KnowledgeImportance(models.TextChoices):
    """知识重要级别。"""

    HIGH = "high", "高"
    NORMAL = "normal", "普通"


class KnowledgeSource(models.TextChoices):
    """知识来源。"""

    MANUAL = "manual", "康复师手动"
    AI_CONFIRMED = "ai_confirmed", "AI 建议确认"
    TRAINING = "training", "训练记录"
    ASSESSMENT = "assessment", "评估"
    CONVERSATION = "conversation", "AI 对话"


class CandidateStatus(models.TextChoices):
    """候选记忆状态。"""

    PENDING = "pending", "待确认"
    CONFIRMED = "confirmed", "已确认"
    REJECTED = "rejected", "已拒绝"


class CustomerKnowledgeItem(models.Model):
    """正式客户知识条目。

    每个条目按分类、内容、来源、重要级别、生效状态记录，并带审计。
    安全限制类（safety）高重要性条目应置顶，在 AI 上下文中优先呈现。
    启用状态下生成向量，供 RAG 检索；向量随内容变化重建。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        category: 分类。
        content: 知识内容。
        source: 来源。
        importance: 重要级别。
        is_active: 是否生效；停用后不再参与检索。
        embedding: pgvector 向量（1024 维），用于相似度检索，可为空。
        created_by / updated_by: 创建/更新人。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="knowledge_items",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="knowledge_items",
        verbose_name="客户",
    )
    category = models.CharField(
        max_length=16,
        choices=KnowledgeCategory.choices,
        default=KnowledgeCategory.OTHER,
        verbose_name="分类",
    )
    content = models.TextField(verbose_name="知识内容")
    source = models.CharField(
        max_length=16,
        choices=KnowledgeSource.choices,
        default=KnowledgeSource.MANUAL,
        verbose_name="来源",
    )
    importance = models.CharField(
        max_length=10,
        choices=KnowledgeImportance.choices,
        default=KnowledgeImportance.NORMAL,
        verbose_name="重要级别",
    )
    is_active = models.BooleanField(default=True, verbose_name="是否生效")
    embedding = VectorField(dimensions=1024, null=True, blank=True, verbose_name="向量")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_created",
        verbose_name="创建人",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_updated",
        verbose_name="更新人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_customer_knowledge_items"
        verbose_name = "客户知识条目"
        verbose_name_plural = "客户知识条目"
        ordering = ["-importance", "category", "-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_knowledge_therapist"),
            models.Index(fields=["customer", "is_active"], name="idx_knowledge_customer_active"),
        ]

    def __str__(self) -> str:
        """返回知识摘要。"""
        return self.content[:40]


class KnowledgeCandidate(models.Model):
    """AI 建议的候选记忆。

    AI 从训练记录、评估或对话中建议的候选知识，必须展示来源与拟写入内容，
    由康复师确认后才转为正式知识（confirmed 时创建 CustomerKnowledgeItem）。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="knowledge_candidates",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="knowledge_candidates",
        verbose_name="客户",
    )
    content = models.TextField(verbose_name="拟写入内容")
    category = models.CharField(
        max_length=16,
        choices=KnowledgeCategory.choices,
        default=KnowledgeCategory.OTHER,
        verbose_name="建议分类",
    )
    source_ref = models.CharField(max_length=255, blank=True, default="", verbose_name="来源说明")
    suggested_at = models.DateTimeField(auto_now_add=True, verbose_name="建议时间")
    status = models.CharField(
        max_length=12,
        choices=CandidateStatus.choices,
        default=CandidateStatus.PENDING,
        verbose_name="状态",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_decided",
        verbose_name="处理人",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="处理时间")
    knowledge_item = models.ForeignKey(
        "knowledge.CustomerKnowledgeItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidates",
        verbose_name="确认生成的知识",
    )

    class Meta:
        db_table = "tb_knowledge_candidates"
        verbose_name = "知识候选"
        verbose_name_plural = "知识候选"
        ordering = ["-suggested_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_kc_therapist"),
            models.Index(fields=["status"], name="idx_kc_status"),
        ]

    def __str__(self) -> str:
        """返回候选摘要。"""
        return self.content[:40]
