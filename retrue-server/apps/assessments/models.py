"""assessments：评估模型。

支持首次评估与阶段复评。评估包含主诉、病史、康复目标与各类指标
（疼痛 NRS、肌力分级、活动度、特殊测试等）。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AssessmentType(models.TextChoices):
    """评估类型。"""

    INITIAL = "initial", "首次评估"
    REASSESSMENT = "reassessment", "阶段复评"


class Assessment(models.Model):
    """评估记录。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        plan: 关联康复计划，可空。
        assessment_type: 首次评估或阶段复评。
        assessment_date: 评估日期。
        chief_complaint: 主诉。
        medical_history: 病史。
        rehab_goal: 康复目标。
        current_status: 当前状态（复评用）。
        note: 自由备注。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name="客户",
    )
    plan = models.ForeignKey(
        "rehab.RehabPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assessments",
        verbose_name="关联计划",
    )
    assessment_type = models.CharField(
        max_length=16,
        choices=AssessmentType.choices,
        default=AssessmentType.INITIAL,
        verbose_name="评估类型",
    )
    assessment_date = models.DateField(verbose_name="评估日期")
    chief_complaint = models.TextField(blank=True, default="", verbose_name="主诉")
    medical_history = models.TextField(blank=True, default="", verbose_name="病史")
    rehab_goal = models.TextField(blank=True, default="", verbose_name="康复目标")
    current_status = models.TextField(blank=True, default="", verbose_name="当前状态")
    note = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "评估"
        verbose_name_plural = "评估"
        ordering = ["-assessment_date", "-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_assess_therapist"),
        ]

    def __str__(self) -> str:
        """返回评估描述。"""
        return f"{self.get_assessment_type_display()} - {self.customer.name}"


class MetricType(models.TextChoices):
    """评估指标类型。"""

    PAIN = "pain", "疼痛"
    STRENGTH = "strength", "肌力"
    ROM = "rom", "活动度"
    SPECIAL_TEST = "special_test", "特殊测试"
    FUNCTIONAL = "functional", "功能动作"


class AssessmentMetric(models.Model):
    """评估指标。

    记录评估中的各类量化指标与描述。

    字段：
        assessment: 所属评估。
        metric_type: 指标类型。
        body_part: 部位（如左膝）。
        score: 数值评分（如疼痛 NRS 0-10、肌力 0-5 级）。
        score_max: 评分满分（如 10、5）。
        description: 描述（如诱发动作、阳性意义）。
    """

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="metrics",
        verbose_name="所属评估",
    )
    metric_type = models.CharField(max_length=16, choices=MetricType.choices, verbose_name="指标类型")
    body_part = models.CharField(max_length=64, blank=True, default="", verbose_name="部位")
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="评分")
    score_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="满分")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="排序")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "评估指标"
        verbose_name_plural = "评估指标"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        """返回指标描述。"""
        return f"{self.get_metric_type_display()} {self.body_part}"
