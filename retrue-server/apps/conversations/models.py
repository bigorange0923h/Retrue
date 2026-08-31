"""AI 统一会话和消息模型。

所有 AI 入口共用同一套表，通过 therapist + customer（可空）隔离，
origin 记录入口，context_resource 记录本次讨论关联的业务对象。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class ConversationOrigin(models.TextChoices):
    """会话发起入口。"""

    DASHBOARD = "dashboard", "首页"
    CUSTOMER_DETAIL = "customer_detail", "客户详情"
    LESSON_PREPARATION = "lesson_preparation", "备课助手"
    TRAINING_RECORD = "training_record", "训练记录"
    ASSESSMENT = "assessment", "评估"
    KNOWLEDGE = "knowledge", "知识库"
    GENERAL = "general", "其他"


class ConversationType(models.TextChoices):
    """会话业务类型。"""

    GENERAL = "general", "通用问答"
    CUSTOMER_DISCUSSION = "customer_discussion", "客户讨论"
    PREPARATION = "preparation", "备课"
    TRAINING = "training", "训练"
    ASSESSMENT = "assessment", "评估"
    PROFESSIONAL_QUESTION = "professional_question", "专业问答"


class ConversationStatus(models.TextChoices):
    """会话状态。"""

    ACTIVE = "active", "进行中"
    ENDED = "ended", "已结束"


class MessageRole(models.TextChoices):
    """消息角色。"""

    USER = "user", "用户"
    ASSISTANT = "assistant", "AI 助手"
    SYSTEM = "system", "系统"
    TOOL = "tool", "工具"


class Conversation(models.Model):
    """一次连续 AI 对话，客户为空时代表康复师通用对话。"""

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="ai_conversations",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ai_conversations",
        verbose_name="客户",
    )
    origin = models.CharField(
        max_length=32,
        choices=ConversationOrigin.choices,
        default=ConversationOrigin.GENERAL,
        verbose_name="发起入口",
    )
    conversation_type = models.CharField(
        max_length=32,
        choices=ConversationType.choices,
        default=ConversationType.GENERAL,
        verbose_name="会话类型",
    )
    context_resource_type = models.CharField(max_length=32, blank=True, default="", verbose_name="关联资源类型")
    context_resource_id = models.CharField(max_length=100, blank=True, default="", verbose_name="关联资源标识")
    title = models.CharField(max_length=120, blank=True, default="", verbose_name="标题")
    summary = models.TextField(blank=True, default="", verbose_name="摘要")
    summarized_through_message_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="摘要已覆盖到的消息 ID",
    )
    summary_updated_at = models.DateTimeField(null=True, blank=True, verbose_name="摘要更新时间")
    episode_analyzed_through_message_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Episode 已分析到的消息 ID",
    )
    status = models.CharField(
        max_length=12,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
        verbose_name="状态",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="开始时间")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_ai_conversations"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["therapist", "customer", "status"], name="idx_conversation_scope"),
            models.Index(fields=["therapist", "origin"], name="idx_conversation_origin"),
        ]

    def __str__(self) -> str:
        """返回会话标题或主键。"""
        return self.title or f"会话 {self.pk}"


class Message(models.Model):
    """会话中的一条不可变消息。"""

    conversation = models.ForeignKey(
        Conversation,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="会话",
    )
    role = models.CharField(max_length=12, choices=MessageRole.choices, verbose_name="角色")
    content = models.TextField(verbose_name="内容")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="元数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = "tb_ai_messages"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"], name="idx_message_conversation")]

    def __str__(self) -> str:
        """返回消息角色与内容摘要。"""
        return f"{self.role}: {self.content[:40]}"
