"""followups：回访/复查待办模型。

支持回访、复查与其他跟进的轻量级待办管理。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class FollowUpType(models.TextChoices):
    """跟进类型。"""

    VISIT = "visit", "回访"
    REVIEW = "review", "复查"
    OTHER = "other", "其他"


class FollowUpStatus(models.TextChoices):
    """跟进状态。"""

    PENDING = "pending", "待处理"
    DONE = "done", "已完成"
    SKIPPED = "skipped", "已跳过"


class FollowUpTask(models.Model):
    """回访/复查待办。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        followup_type: 类型（回访/复查/其他）。
        due_date: 计划日期。
        content: 内容。
        status: 状态。
        result: 完成结果。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="followup_tasks",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="followup_tasks",
        verbose_name="客户",
    )
    followup_type = models.CharField(
        max_length=12, choices=FollowUpType.choices, default=FollowUpType.VISIT, verbose_name="类型"
    )
    due_date = models.DateField(verbose_name="计划日期")
    content = models.CharField(max_length=255, blank=True, default="", verbose_name="内容")
    status = models.CharField(
        max_length=12, choices=FollowUpStatus.choices, default=FollowUpStatus.PENDING, verbose_name="状态"
    )
    result = models.CharField(max_length=255, blank=True, default="", verbose_name="完成结果")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_followup_tasks"
        verbose_name = "回访/复查"
        verbose_name_plural = "回访/复查"
        ordering = ["due_date", "-created_at"]
        indexes = [
            models.Index(fields=["therapist", "due_date"], name="idx_followup_therapist"),
        ]

    def __str__(self) -> str:
        """返回待办描述。"""
        return f"{self.get_followup_type_display()} - {self.customer.name}"
