"""ai：AI 草稿模型。

保存 AI 解析流程的原始输入、AI 初始结果、最终确认结果与错误信息。
AI 只生成待确认草稿，不直接修改正式训练记录。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AiDraftStatus(models.TextChoices):
    """AI 草稿状态。"""

    PENDING = "pending", "待确认"
    CONFIRMED = "confirmed", "已确认"
    CANCELLED = "cancelled", "已取消"
    FAILED = "failed", "解析失败"


class AiDraft(models.Model):
    """AI 生成草稿。

    字段：
        therapist: 操作康复师（数据隔离）。
        customer: 关联客户，客户不确定时可空（待候选确认）。
        status: 草稿状态。
        input_text: 用户原始输入。
        ai_result: AI 初始结构化结果（JSON）。
        confirmed_result: 人工确认后的最终结果（JSON）。
        error_message: 解析失败的错误信息。
        confirmed_at: 确认时间。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_drafts",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_drafts",
        verbose_name="关联客户",
    )
    status = models.CharField(
        max_length=12,
        choices=AiDraftStatus.choices,
        default=AiDraftStatus.PENDING,
        verbose_name="状态",
    )
    input_text = models.TextField(verbose_name="用户原始输入")
    ai_result = models.JSONField(default=dict, blank=True, verbose_name="AI 初始结果")
    confirmed_result = models.JSONField(default=dict, blank=True, verbose_name="确认结果")
    error_message = models.CharField(max_length=500, blank=True, default="", verbose_name="错误信息")
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "AI 草稿"
        verbose_name_plural = "AI 草稿"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "status"], name="idx_ai_therapist_status"),
        ]

    def __str__(self) -> str:
        """返回草稿描述。"""
        return f"{self.get_status_display()} #{self.id}"
