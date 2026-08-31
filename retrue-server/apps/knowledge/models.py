"""knowledge：客户私有康复知识库模型。

客户私有知识库优先保存经康复师确认的高价值信息，按"康复师 + 客户"严格隔离。
包含两类实体：
    - CustomerKnowledgeItem：正式知识条目（含 pgvector 向量字段，用于 RAG 检索）。
    - KnowledgeCandidate：AI 建议的候选记忆，需康复师确认后才转为正式知识。
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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


class MemoryType(models.TextChoices):
    """长期记忆的业务分类，和正式康复事实保持隔离。"""

    PREFERENCE = "preference", "训练偏好"
    DISLIKE = "dislike", "不喜欢"
    COMMUNICATION = "communication", "沟通习惯"
    HABIT = "habit", "训练或生活习惯"
    GOAL = "goal", "长期目标"
    CONCERN = "concern", "顾虑"
    PATTERN = "pattern", "长期观察规律"
    BACKGROUND = "background", "康复相关背景"
    THERAPIST_OBSERVATION = "therapist_observation", "康复师长期观察"
    OTHER = "other", "其他"


class MemoryStatus(models.TextChoices):
    """长期记忆生命周期。只有 active 会进入 AI 上下文。"""

    CANDIDATE = "candidate", "待确认"
    ACTIVE = "active", "生效"
    SUPERSEDED = "superseded", "已替代"
    EXPIRED = "expired", "已停用"
    DELETED = "deleted", "已删除"


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
    DEFERRED = "deferred", "暂缓处理"


class MemoryConflictType(models.TextChoices):
    """候选与当前有效记忆的关系。"""

    NONE = "none", "无冲突"
    CONFLICT = "conflict", "内容冲突"
    CONDITIONAL = "conditional", "适用条件不同"
    SUPPLEMENT = "supplement", "补充信息"


class EpisodeStatus(models.TextChoices):
    """历史讨论事件生命周期。"""

    CANDIDATE = "candidate", "待确认"
    ACTIVE = "active", "生效"
    REJECTED = "rejected", "已拒绝"
    DELETED = "deleted", "已删除"


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
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="knowledge_items",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
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
    memory_type = models.CharField(
        max_length=32,
        choices=MemoryType.choices,
        default=MemoryType.OTHER,
        verbose_name="记忆类型",
    )
    memory_key = models.CharField(max_length=100, blank=True, default="", verbose_name="记忆键")
    content = models.TextField(verbose_name="知识内容")
    normalized_value = models.TextField(blank=True, default="", verbose_name="标准化内容")
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
    status = models.CharField(
        max_length=12,
        choices=MemoryStatus.choices,
        default=MemoryStatus.ACTIVE,
        verbose_name="记忆状态",
    )
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=1, verbose_name="可信度")
    importance_score = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="重要度（1-5）",
    )
    source_type = models.CharField(max_length=32, blank=True, default="", verbose_name="来源类型")
    source_id = models.CharField(max_length=100, blank=True, default="", verbose_name="来源标识")
    source_message_id = models.CharField(max_length=100, blank=True, default="", verbose_name="来源消息标识")
    confirmed_by_user = models.BooleanField(default=True, verbose_name="是否人工确认")
    effective_from = models.DateTimeField(null=True, blank=True, verbose_name="生效时间")
    effective_to = models.DateTimeField(null=True, blank=True, verbose_name="失效时间")
    last_confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="最近确认时间")
    supersedes_memory = models.ForeignKey(
        "self",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
        verbose_name="替代的旧记忆",
    )
    embedding = VectorField(dimensions=1024, null=True, blank=True, verbose_name="向量")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_created",
        verbose_name="创建人",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
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
            models.Index(fields=["customer", "status"], name="idx_memory_customer_status"),
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
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="knowledge_candidates",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
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
    memory_type = models.CharField(
        max_length=32,
        choices=MemoryType.choices,
        default=MemoryType.OTHER,
        verbose_name="建议记忆类型",
    )
    memory_key = models.CharField(max_length=100, blank=True, default="", verbose_name="建议记忆键")
    normalized_value = models.TextField(blank=True, default="", verbose_name="建议标准化内容")
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0.5, verbose_name="提取可信度")
    importance_score = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="建议重要度（1-5）",
    )
    evidence = models.TextField(blank=True, default="", verbose_name="提取证据")
    conflict_type = models.CharField(
        max_length=16,
        choices=MemoryConflictType.choices,
        default=MemoryConflictType.NONE,
        verbose_name="与现有记忆的关系",
    )
    conflict_memory = models.ForeignKey(
        "knowledge.CustomerKnowledgeItem",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conflicting_candidates",
        verbose_name="冲突的有效记忆",
    )
    source_conversation = models.ForeignKey(
        "conversations.Conversation",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_candidates",
        verbose_name="来源会话",
    )
    source_message = models.ForeignKey(
        "conversations.Message",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_candidates",
        verbose_name="来源消息",
    )
    resolution_action = models.CharField(max_length=20, blank=True, default="", verbose_name="处理方式")
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
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_decided",
        verbose_name="处理人",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="处理时间")
    knowledge_item = models.ForeignKey(
        "knowledge.CustomerKnowledgeItem",
        db_constraint=False,
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


class MemoryEpisode(models.Model):
    """一次值得跨会话回顾的重要讨论事件。

    AI 只生成 candidate；康复师确认后才变为 active 并进入上下文。
    Episode 保存历史讨论，不替代训练、评估、计划等正式业务事实。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="memory_episodes",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="memory_episodes",
        verbose_name="客户",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_episodes",
        verbose_name="来源会话",
    )
    episode_key = models.CharField(max_length=120, verbose_name="事件键")
    title = models.CharField(max_length=160, verbose_name="主题")
    summary = models.TextField(verbose_name="讨论摘要")
    key_points = models.JSONField(default=list, blank=True, verbose_name="关键点")
    decisions = models.JSONField(default=list, blank=True, verbose_name="讨论决定")
    next_actions = models.JSONField(default=list, blank=True, verbose_name="下一步行动")
    importance_score = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name="重要度（1-5）",
    )
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0.5, verbose_name="可信度")
    status = models.CharField(
        max_length=12,
        choices=EpisodeStatus.choices,
        default=EpisodeStatus.CANDIDATE,
        verbose_name="状态",
    )
    source_start_message_id = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="来源起始消息 ID")
    source_end_message_id = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="来源结束消息 ID")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_episodes_decided",
        verbose_name="处理人",
    )
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="处理时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_memory_episodes"
        ordering = ["-importance_score", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "episode_key"],
                name="uq_episode_conversation_key",
            )
        ]
        indexes = [
            models.Index(fields=["therapist", "customer", "status"], name="idx_episode_scope"),
            models.Index(fields=["customer", "created_at"], name="idx_episode_customer_time"),
        ]

    def __str__(self) -> str:
        """返回事件主题。"""
        return self.title
