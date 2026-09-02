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


class AiDraftType(models.TextChoices):
    """AI 草稿类型。"""

    TRAINING_RECORD = "training_record", "训练补记"
    ASSESSMENT = "assessment", "评估"
    TRAINING_REVISION = "training_revision", "训练记录修订"
    FOLLOWUP = "followup", "随访"


class AiDraft(models.Model):
    """AI 生成草稿。

    字段：
        therapist: 操作康复师（数据隔离）。
        customer: 关联客户，客户不确定时可空（待候选确认）。
        assistant_task: 可选的统一助手任务，供补记流程追踪。
        training_record: 确认后创建的正式训练记录。
        status: 草稿状态。
        input_text: 用户原始输入。
        ai_result: AI 初始结构化结果（JSON）。
        confirmed_result: 人工确认后的最终结果（JSON）。
        confirmation_key: 确认请求幂等键。
        error_message: 解析失败的错误信息。
        confirmed_at: 确认时间。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="ai_drafts",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_drafts",
        verbose_name="关联客户",
    )
    assistant_task = models.ForeignKey(
        "assistant_tasks.AssistantTask",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_drafts",
        verbose_name="统一助手任务",
    )
    training_record = models.ForeignKey(
        "training.TrainingRecord",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_drafts",
        verbose_name="正式训练记录",
    )
    assessment = models.ForeignKey(
        "assessments.Assessment",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_drafts",
        verbose_name="正式评估",
    )
    followup = models.ForeignKey(
        "followups.FollowUpTask",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_drafts",
        verbose_name="正式随访",
    )
    draft_type = models.CharField(
        max_length=24,
        choices=AiDraftType.choices,
        default=AiDraftType.TRAINING_RECORD,
        verbose_name="草稿类型",
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
    confirmation_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        verbose_name="确认幂等键",
    )
    error_message = models.CharField(max_length=500, blank=True, default="", verbose_name="错误信息")
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_ai_drafts"
        verbose_name = "AI 草稿"
        verbose_name_plural = "AI 草稿"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "status"], name="idx_ai_therapist_status"),
        ]

    def __str__(self) -> str:
        """返回草稿描述。"""
        return f"{self.get_status_display()} #{self.id}"


class RiskLevel(models.TextChoices):
    """风险等级。"""

    LOW = "low", "低"
    MEDIUM = "medium", "中"
    HIGH = "high", "高"


class RiskAction(models.TextChoices):
    """建议动作。"""

    PAUSE = "pause", "暂停"
    REVIEW = "review", "复查"
    CHECK = "check", "检查"
    REFER = "refer", "考虑转诊"


class RiskAlert(models.Model):
    """风险提醒。

    记录 AI 检测到的异常风险，结构化保存风险等级、发现依据与建议动作。
    康复师可确认或记录处理结果。AI 不替代诊断，仅提供提醒。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        training_record: 关联训练记录，可空。
        risk_level: 风险等级。
        evidence: 发现依据（AI 根据哪些历史信息判断）。
        suggested_action: 建议动作。
        is_confirmed: 康复师是否确认。
        outcome: 康复师最终处理方式。
        created_at: 创建时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="risk_alerts",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="risk_alerts",
        verbose_name="客户",
    )
    training_record = models.ForeignKey(
        "training.TrainingRecord",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_alerts",
        verbose_name="关联训练记录",
    )
    risk_level = models.CharField(
        max_length=10, choices=RiskLevel.choices, default=RiskLevel.MEDIUM, verbose_name="风险等级"
    )
    evidence = models.TextField(blank=True, default="", verbose_name="发现依据")
    suggested_action = models.CharField(
        max_length=10, choices=RiskAction.choices, default=RiskAction.CHECK, verbose_name="建议动作"
    )
    is_confirmed = models.BooleanField(default=False, verbose_name="是否确认")
    outcome = models.CharField(max_length=255, blank=True, default="", verbose_name="处理结果")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = "tb_risk_alerts"
        verbose_name = "风险提醒"
        verbose_name_plural = "风险提醒"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_risk_therapist"),
        ]

    def __str__(self) -> str:
        """返回风险提醒描述。"""
        return f"{self.get_risk_level_display()}风险 - {self.customer.name}"
