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


class AssessmentStatus(models.TextChoices):
    """评估填写状态。"""

    DRAFT = "draft", "草稿"
    COMPLETED = "completed", "已完成"


class OnsetMode(models.TextChoices):
    """问题或症状的发生方式。"""

    INJURY = "injury", "受伤"
    SUDDEN = "sudden", "突然发作"
    GRADUAL = "gradual", "逐渐加重"
    POSTOPERATIVE = "postoperative", "术后"
    OTHER = "other", "其他"
    UNKNOWN = "unknown", "不清楚"


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
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="assessments",
        verbose_name="客户",
    )
    plan = models.ForeignKey(
        "rehab.RehabPlan",
        db_constraint=False,
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
    status = models.CharField(
        max_length=16,
        choices=AssessmentStatus.choices,
        default=AssessmentStatus.DRAFT,
        verbose_name="评估状态",
    )
    assessment_date = models.DateField(verbose_name="评估日期")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    chief_complaint = models.TextField(blank=True, default="", verbose_name="主诉")
    medical_history = models.TextField(blank=True, default="", verbose_name="病史")
    rehab_goal = models.TextField(blank=True, default="", verbose_name="康复目标")
    current_status = models.TextField(blank=True, default="", verbose_name="当前状态")
    note = models.TextField(blank=True, default="", verbose_name="备注")
    onset_date = models.DateField(null=True, blank=True, verbose_name="问题开始日期")
    onset_description = models.TextField(blank=True, default="", verbose_name="问题开始描述")
    onset_mode = models.CharField(
        max_length=16,
        choices=OnsetMode.choices,
        default=OnsetMode.UNKNOWN,
        verbose_name="发生方式",
    )
    aggravating_factors = models.TextField(blank=True, default="", verbose_name="加重因素")
    relieving_factors = models.TextField(blank=True, default="", verbose_name="缓解因素")
    prior_care = models.TextField(blank=True, default="", verbose_name="既往就医与治疗")
    surgery_history = models.TextField(blank=True, default="", verbose_name="手术史快照")
    medication = models.TextField(blank=True, default="", verbose_name="用药情况")
    exercise_habits = models.TextField(blank=True, default="", verbose_name="运动习惯快照")
    work_demands = models.TextField(blank=True, default="", verbose_name="工作负荷快照")
    sleep_impact = models.TextField(blank=True, default="", verbose_name="睡眠影响")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_assessments"
        verbose_name = "评估"
        verbose_name_plural = "评估"
        ordering = ["-assessment_date", "-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_assess_therapist"),
            models.Index(
                fields=["therapist", "customer", "assessment_type"],
                name="idx_assess_identity",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["therapist", "customer"],
                condition=models.Q(assessment_type=AssessmentType.INITIAL),
                name="uniq_initial_assessment",
            ),
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


class MetricSide(models.TextChoices):
    """指标对应的身体侧别。"""

    LEFT = "left", "左侧"
    RIGHT = "right", "右侧"
    BILATERAL = "bilateral", "双侧"
    NOT_APPLICABLE = "not_applicable", "不适用"


class MetricContext(models.TextChoices):
    """疼痛或表现出现的场景。"""

    REST = "rest", "静息"
    ACTIVITY = "activity", "活动时"
    PRE_TRAINING = "pre_training", "训练前"
    POST_TRAINING = "post_training", "训练后"
    NIGHT = "night", "夜间"
    CUSTOM = "custom", "自定义"


class MeasurementMode(models.TextChoices):
    """活动度测量方式。"""

    ACTIVE = "active", "主动 AROM"
    PASSIVE = "passive", "被动 PROM"


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
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="metrics",
        verbose_name="所属评估",
    )
    metric_type = models.CharField(max_length=16, choices=MetricType.choices, verbose_name="指标类型")
    body_part = models.CharField(max_length=64, blank=True, default="", verbose_name="部位")
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="评分")
    score_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="满分")
    description = models.TextField(blank=True, default="", verbose_name="描述")
    side = models.CharField(
        max_length=16,
        choices=MetricSide.choices,
        blank=True,
        default="",
        verbose_name="侧别",
    )
    scale_code = models.CharField(max_length=32, blank=True, default="", verbose_name="量表代码")
    unit = models.CharField(max_length=16, blank=True, default="", verbose_name="单位")
    context = models.CharField(
        max_length=24,
        choices=MetricContext.choices,
        blank=True,
        default="",
        verbose_name="评估场景",
    )
    movement = models.CharField(max_length=128, blank=True, default="", verbose_name="动作/肌群")
    measurement_mode = models.CharField(
        max_length=16,
        choices=MeasurementMode.choices,
        blank=True,
        default="",
        verbose_name="测量方式",
    )
    result_code = models.CharField(max_length=32, blank=True, default="", verbose_name="分类结果")
    details = models.JSONField(default=dict, blank=True, verbose_name="扩展信息")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="排序")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def save(self, *args, **kwargs):
        """保存时派生量表、单位与满分，避免绕过 API 时写入伪满分。"""
        derived_fields = {"score_max", "scale_code", "unit"}
        if self.metric_type == MetricType.PAIN:
            self.scale_code = "NRS_0_10"
            self.unit = "point"
            self.score_max = 10
        elif self.metric_type == MetricType.STRENGTH:
            self.scale_code = "MRC_0_5"
            self.unit = "grade"
            self.score_max = 5
        elif self.metric_type == MetricType.ROM:
            self.scale_code = ""
            self.unit = "degree"
            self.score_max = None
        elif self.metric_type in {
            MetricType.SPECIAL_TEST,
            MetricType.FUNCTIONAL,
        }:
            self.scale_code = ""
            self.unit = ""
            self.score = None
            self.score_max = None
            derived_fields.add("score")
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | derived_fields
        super().save(*args, **kwargs)

    class Meta:
        db_table = "tb_assessment_metrics"
        verbose_name = "评估指标"
        verbose_name_plural = "评估指标"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        """返回指标描述。"""
        return f"{self.get_metric_type_display()} {self.body_part}"
