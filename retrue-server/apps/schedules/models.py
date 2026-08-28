"""schedules：课程/日程模型。

实现"课程类型 → 客户疗程 → 课程排期"三层语义：
- CourseType：康复师维护、可复用的课程目录定义。
- CustomerCourse：将课程类型分配给某客户后形成的个体化执行单元。
- CourseSession：日历中的实际预约条目，关联客户疗程。

课程排期完成后按客户疗程规则触发课时包扣减（半课/全课用 Decimal 课时单位）。
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


class CustomerCourseStatus(models.TextChoices):
    """客户疗程状态机。"""

    PENDING = "pending", "待开始"
    ACTIVE = "active", "进行中"
    PAUSED = "paused", "暂停"
    COMPLETED = "completed", "已完成"
    CANCELLED = "cancelled", "已取消"


class CourseType(models.Model):
    """课程类型（康复师维护的课程目录）。

    相当于"高数课/经济学课"这一层：可复用、可分配给不同客户，而非某次具体上课记录。
    已被客户疗程引用的类型不得物理删除，只能停用（is_active=False）。

    字段：
        therapist: 康复师（数据隔离归属）。
        name: 课程类型名称。
        description: 简介。
        is_active: 启用状态。
        default_duration: 默认时长（分钟）。
        default_session_cost: 默认单节课时消耗量（支持 0.5 半课 / 1.0 全课）。
        default_stage: 默认适用康复阶段（text）。
        default_goals: 默认课程目标。
        default_notes: 默认注意事项。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
    default_stage = models.CharField(max_length=12, blank=True, default="", verbose_name="默认适用阶段")
    default_goals = models.TextField(blank=True, default="", verbose_name="默认课程目标")
    default_notes = models.TextField(blank=True, default="", verbose_name="默认注意事项")
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


class CustomerCourse(models.Model):
    """客户疗程。

    将课程类型分配给一位客户后形成的个体化执行单元。
    一个客户可在不同时间拥有多个疗程，也可在同一康复计划内并行多个疗程。

    课程类型后续被编辑时，不应改变已开设客户疗程的快照（session_cost/duration），
    避免历史疗程含义漂移。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        course_type: 关联课程类型。
        plan: 可选关联康复计划。
        stage_type: 可选当前康复阶段类型。
        package: 可选关联课时包。
        start_date / end_date: 实际起止日期。
        status: 状态机（待开始/进行中/暂停/已完成/已取消）。
        individual_goals: 个体化目标。
        planned_sessions: 计划课次或计划课时。
        session_cost: 单节课时消耗量快照（半课 0.5 / 全课 1.0）。
        duration: 单节课时长（分钟）快照。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_courses",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="customer_courses",
        verbose_name="客户",
    )
    course_type = models.ForeignKey(
        "schedules.CourseType",
        on_delete=models.PROTECT,
        related_name="customer_courses",
        verbose_name="课程类型",
    )
    plan = models.ForeignKey(
        "rehab.RehabPlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_courses",
        verbose_name="关联康复计划",
    )
    stage_type = models.CharField(
        max_length=12,
        blank=True,
        default="",
        verbose_name="当前康复阶段",
    )
    package = models.ForeignKey(
        "courses.CoursePackage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_courses",
        verbose_name="关联课时包",
    )
    start_date = models.DateField(null=True, blank=True, verbose_name="开始日期")
    end_date = models.DateField(null=True, blank=True, verbose_name="结束日期")
    status = models.CharField(
        max_length=12,
        choices=CustomerCourseStatus.choices,
        default=CustomerCourseStatus.PENDING,
        verbose_name="状态",
    )
    individual_goals = models.TextField(blank=True, default="", verbose_name="个体化目标")
    planned_sessions = models.DecimalField(
        max_digits=6, decimal_places=1, null=True, blank=True, verbose_name="计划课次/课时"
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
        db_table = "tb_customer_courses"
        verbose_name = "客户疗程"
        verbose_name_plural = "客户疗程"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_custcourse_therapist"),
            models.Index(fields=["customer", "status"], name="idx_custcourse_customer_status"),
        ]

    def __str__(self) -> str:
        """返回客户疗程描述。"""
        return f"{self.course_type.name} - {self.customer.name}"


class CourseSession(models.Model):
    """课程/日程条目（日历中的实际预约）。

    新建排期的标准流程：先选择客户，再选择该客户"进行中"的客户疗程，最后填写时间与本节训练主题。

    字段：
        therapist: 康复师（数据隔离归属）。
        customer: 关联客户。
        customer_course: 关联客户疗程（可空，历史排期逐步关联）。
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
        on_delete=models.CASCADE,
        related_name="course_sessions",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="course_sessions",
        verbose_name="客户",
    )
    customer_course = models.ForeignKey(
        "schedules.CustomerCourse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="客户疗程",
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
