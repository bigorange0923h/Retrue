"""rehab：康复计划与康复阶段模型。

康复计划是客户康复过程的框架，采用默认四阶段管理。
AI 不自动修改康复阶段，阶段调整须由康复师手动进行。
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class RehabStageType(models.TextChoices):
    """康复阶段类型（默认四阶段框架）。"""

    ACUTE = "acute", "急性期/疼痛控制"
    RECOVERY = "recovery", "恢复期/活动度恢复"
    STRENGTH = "strength", "力量重建期"
    FUNCTIONAL = "functional", "功能回归期"


class RehabPlanTemplate(models.Model):
    """康复师维护的可复用课程计划模板。

    模板只提供客户课程计划的初始方案，不承载任何客户执行进度。应用模板时，
    模板字段和模板课程会复制为客户专属快照，后续修改模板不影响既有计划。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rehab_plan_templates",
        verbose_name="康复师",
    )
    name = models.CharField(max_length=128, verbose_name="模板名称")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="适用说明")
    suggested_duration_weeks = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="建议时长（周）",
    )
    goals = models.TextField(blank=True, default="", verbose_name="默认计划目标")
    is_active = models.BooleanField(default=True, verbose_name="启用状态")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_rehab_plan_templates"
        verbose_name = "课程计划模板"
        verbose_name_plural = "课程计划模板"
        ordering = ["-is_active", "name"]
        indexes = [
            models.Index(
                fields=["therapist", "is_active"],
                name="idx_rpt_therapist_active",
            ),
        ]

    def __str__(self) -> str:
        """返回课程计划模板名称。"""
        return self.name


class RehabPlanTemplateCourse(models.Model):
    """课程计划模板中的课程组成和默认课时快照。"""

    template = models.ForeignKey(
        RehabPlanTemplate,
        on_delete=models.CASCADE,
        related_name="courses",
        verbose_name="课程计划模板",
    )
    course_type = models.ForeignKey(
        "schedules.CourseType",
        on_delete=models.PROTECT,
        related_name="rehab_plan_template_courses",
        verbose_name="课程模板",
    )
    planned_count = models.PositiveIntegerField(default=1, verbose_name="默认计划次数")
    session_cost = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("1.0"),
        verbose_name="默认单次课时扣减",
    )
    duration = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="默认单次时长（分钟）",
    )
    goals = models.TextField(blank=True, default="", verbose_name="默认课程目标")
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="排序")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_rehab_plan_template_courses"
        verbose_name = "课程计划模板课程"
        verbose_name_plural = "课程计划模板课程"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "course_type"],
                name="uniq_rpt_course_type",
            ),
        ]

    def __str__(self) -> str:
        """返回计划模板与课程名称。"""
        return f"{self.template.name} - {self.course_type.name}"


class RehabPlan(models.Model):
    """客户的一段课程计划。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        source_template: 创建本计划时使用的来源模板，仅用于追溯。
        name: 计划名称。
        start_date / end_date: 周期起止日期。
        goals: 本计划总体目标。
        status: 状态（进行中/已结束）。
        note: 备注。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rehab_plans",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="rehab_plans",
        verbose_name="客户",
    )
    source_template = models.ForeignKey(
        RehabPlanTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_plans",
        verbose_name="来源课程计划模板",
    )
    name = models.CharField(max_length=128, default="默认康复计划", verbose_name="计划名称")
    start_date = models.DateField(verbose_name="开始日期")
    end_date = models.DateField(null=True, blank=True, verbose_name="结束日期")
    status = models.CharField(
        max_length=12,
        choices=[("active", "进行中"), ("closed", "已结束")],
        default="active",
        verbose_name="状态",
    )
    goals = models.TextField(blank=True, default="", verbose_name="计划目标")
    note = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_rehab_plans"
        verbose_name = "客户课程计划"
        verbose_name_plural = "客户课程计划"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_rehabplan_therapist"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["therapist", "customer"],
                condition=models.Q(status="active"),
                name="uniq_active_rehab_plan",
            ),
        ]

    def __str__(self) -> str:
        """返回计划描述。"""
        return f"{self.name} - {self.customer.name}"


class RehabStage(models.Model):
    """康复阶段。

    记录客户课程计划内的康复阶段及调整历史。阶段由康复师手动设置，
    AI 不自动修改。每个周期同一时间最多一个有效阶段。
    """

    plan = models.ForeignKey(
        RehabPlan,
        on_delete=models.CASCADE,
        related_name="stages",
        verbose_name="所属计划",
    )
    stage_type = models.CharField(
        max_length=12,
        choices=RehabStageType.choices,
        verbose_name="阶段类型",
    )
    start_date = models.DateField(verbose_name="进入日期")
    end_date = models.DateField(null=True, blank=True, verbose_name="结束日期")
    note = models.TextField(blank=True, default="", verbose_name="阶段说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_rehab_stages"
        verbose_name = "康复阶段"
        verbose_name_plural = "康复阶段"
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["plan", "stage_type"], name="idx_rehabstage_plan"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["plan"],
                condition=models.Q(end_date__isnull=True),
                name="uniq_current_stage_per_plan",
            ),
        ]

    def __str__(self) -> str:
        """返回阶段描述。"""
        return f"{self.get_stage_type_display()} - {self.plan.customer.name}"
