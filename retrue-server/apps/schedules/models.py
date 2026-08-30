"""schedules：课程模板、计划内课程与课程排期模型。

领域层级为“客户课程计划 → 计划内课程 → 课程排期 → 训练记录”：
- CourseType：康复师维护、可复用的课程模板。
- RehabPlanCourse：某个客户课程计划内的一种课程及计划次数。
- CourseSession：日历中的一次实际预约。
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models


class CourseSessionStatus(models.TextChoices):
    """课程状态。"""

    SCHEDULED = "scheduled", "待上课"
    COMPLETED = "completed", "已完成"
    CANCELLED = "cancelled", "已取消"
    ABSENT = "absent", "请假"


class PlanCourseStatus(models.TextChoices):
    """计划内课程状态。"""

    ACTIVE = "active", "进行中"
    PAUSED = "paused", "暂停"
    COMPLETED = "completed", "已完成"
    CANCELLED = "cancelled", "已取消"


class CourseType(models.Model):
    """课程类型（康复师维护的课程目录）。

    相当于"高数课/经济学课"这一层：可复用、可分配给不同客户，而非某次具体上课记录。
    已被计划内课程引用的模板不得物理删除，只能停用（is_active=False）。

    字段：
        therapist: 康复师（数据隔离归属）。
        name: 课程类型名称。
        description: 简介。
        is_active: 启用状态。
        default_duration: 默认时长（分钟）。
        default_session_cost: 默认单节课时消耗量（支持 0.5 半课 / 1.0 全课）。
        default_goals: 默认课程目标。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="course_types",
        verbose_name="康复师",
    )
    name = models.CharField(max_length=128, verbose_name="课程类型名称")
    description = models.CharField(max_length=255, blank=True, default="", verbose_name="简介")
    is_active = models.BooleanField(default=True, verbose_name="启用状态")
    default_duration = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="默认时长（分钟）"
    )
    default_session_cost = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("1.0"), verbose_name="默认单节课时消耗"
    )
    default_goals = models.TextField(blank=True, default="", verbose_name="默认课程目标")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_course_types"
        verbose_name = "课程类型"
        verbose_name_plural = "课程类型"
        ordering = ["-is_active", "name"]
        indexes = [
            models.Index(fields=["therapist", "is_active"], name="idx_coursetype_therapist"),
        ]

    def __str__(self) -> str:
        """返回课程类型描述。"""
        return self.name


class RehabPlanCourse(models.Model):
    """客户课程计划内的一种课程安排。

    周期负责总目标和日期；本模型只负责课程模板、计划次数、单次时长、
    单次课时消耗及课程级目标。计划次数的增减由 PlanCourseAdjustment 留痕。
    """

    rehab_plan = models.ForeignKey(
        "rehab.RehabPlan",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="plan_courses",
        verbose_name="客户课程计划",
    )
    course_type = models.ForeignKey(
        "schedules.CourseType",
        db_constraint=False,
        on_delete=models.PROTECT,
        related_name="plan_courses",
        verbose_name="课程类型",
    )
    package = models.ForeignKey(
        "courses.CoursePackage",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_courses",
        verbose_name="关联课时包",
    )
    status = models.CharField(
        max_length=12,
        choices=PlanCourseStatus.choices,
        default=PlanCourseStatus.ACTIVE,
        verbose_name="状态",
    )
    goals = models.TextField(blank=True, default="", verbose_name="课程目标")
    planned_count = models.PositiveIntegerField(
        default=1,
        verbose_name="计划次数",
    )
    session_cost = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("1.0"), verbose_name="单节课时消耗快照"
    )
    duration = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="单节课时长（分钟）快照"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_rehab_plan_courses"
        verbose_name = "计划内课程"
        verbose_name_plural = "计划内课程"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rehab_plan", "status"], name="idx_plancourse_plan_status"),
            models.Index(fields=["course_type"], name="idx_plancourse_type"),
        ]

    def __str__(self) -> str:
        """返回计划内课程描述。"""
        return f"{self.rehab_plan.name} - {self.course_type.name}"


class PlanCourseAdjustment(models.Model):
    """计划内课程次数的人工调整记录。"""

    plan_course = models.ForeignKey(
        RehabPlanCourse,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="adjustments",
        verbose_name="计划内课程",
    )
    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.PROTECT,
        related_name="plan_course_adjustments",
        verbose_name="操作康复师",
    )
    assessment = models.ForeignKey(
        "assessments.Assessment",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_course_adjustments",
        verbose_name="关联复评",
    )
    delta_count = models.IntegerField(verbose_name="次数调整量")
    before_count = models.PositiveIntegerField(verbose_name="调整前次数")
    after_count = models.PositiveIntegerField(verbose_name="调整后次数")
    reason = models.CharField(max_length=500, verbose_name="调整原因")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="调整时间")

    class Meta:
        db_table = "tb_plan_course_adjustments"
        verbose_name = "计划内课程次数调整"
        verbose_name_plural = "计划内课程次数调整"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """返回次数调整描述。"""
        return f"{self.plan_course} {self.delta_count:+d}"


class CourseSession(models.Model):
    """课程/日程条目（日历中的实际预约）。

    新建排期的标准流程：先选择客户，再选择该客户进行中周期里的课程，最后填写时间与本节训练主题。

    字段：
        therapist: 康复师（数据隔离归属）。
        customer: 关联客户。
        plan_course: 关联计划内课程（可空，允许首次评估等计划外课程）。
        session_topic: 本节训练主题，例如单腿稳定性与臀肌激活（不等于课程类型）。
        session_count: 本节约课时单位（半课 0.5 / 全课 1.0），用于课时包扣减。
        date: 上课日期。
        start_time: 开始时间，可空。
        end_time: 结束时间，可空。
        status: 课程状态。
        note: 备注。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="course_sessions",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="course_sessions",
        verbose_name="客户",
    )
    plan_course = models.ForeignKey(
        "schedules.RehabPlanCourse",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="计划内课程",
    )
    session_topic = models.CharField(max_length=128, default="康复训练", verbose_name="本节训练主题")
    session_count = models.DecimalField(
        max_digits=4, decimal_places=1, default=Decimal("1.0"), verbose_name="课时单位"
    )
    session_consumed = models.BooleanField(default=False, verbose_name="是否已扣课时")
    date = models.DateField(verbose_name="上课日期")
    start_time = models.TimeField(null=True, blank=True, verbose_name="开始时间")
    end_time = models.TimeField(null=True, blank=True, verbose_name="结束时间")
    status = models.CharField(
        max_length=12,
        choices=CourseSessionStatus.choices,
        default=CourseSessionStatus.SCHEDULED,
        verbose_name="状态",
    )
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_course_sessions"
        verbose_name = "课程"
        verbose_name_plural = "课程"
        ordering = ["date", "start_time"]
        indexes = [
            models.Index(fields=["therapist", "date"], name="idx_course_therapist_date"),
            models.Index(fields=["customer"], name="idx_course_customer"),
        ]

    def __str__(self) -> str:
        """返回课程条目描述。"""
        return f"{self.date} {self.customer.name}"
