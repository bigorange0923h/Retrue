"""training：训练记录模型。

记录康复师每节课的正式训练数据，包括动作明细、客户感受、
康复师观察与下次计划。正式记录修订必须可追溯。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class TrainingRecord(models.Model):
    """训练记录（一次课）。

    字段：
        therapist: 康复师（数据隔离归属）。
        customer: 关联客户。
        course_session: 关联课程条目，可空。
        training_date: 训练日期。
        customer_feedback: 客户感受（自然语言）。
        therapist_observation: 康复师观察。
        next_plan: 下次计划方向。
        note: 备注。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="training_records",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="training_records",
        verbose_name="客户",
    )
    course_session = models.ForeignKey(
        "schedules.CourseSession",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="training_records",
        verbose_name="关联课程",
    )
    training_date = models.DateField(verbose_name="训练日期")
    customer_feedback = models.TextField(blank=True, default="", verbose_name="客户感受")
    therapist_observation = models.TextField(blank=True, default="", verbose_name="康复师观察")
    next_plan = models.TextField(blank=True, default="", verbose_name="下次计划")
    note = models.TextField(blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_training_records"
        verbose_name = "训练记录"
        verbose_name_plural = "训练记录"
        ordering = ["-training_date", "-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_tr_therapist_customer"),
            models.Index(fields=["customer", "training_date"], name="idx_tr_customer_date"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["course_session"],
                condition=models.Q(course_session__isnull=False),
                name="uq_training_record_course_session",
            ),
        ]

    def __str__(self) -> str:
        """返回训练记录描述。"""
        return f"{self.training_date} {self.customer.name}"


class TrainingExercise(models.Model):
    """训练动作明细。

    一条训练记录包含多个动作，记录训练量（组数、次数、负荷、时长）与备注。
    """

    training_record = models.ForeignKey(
        TrainingRecord,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="exercises",
        verbose_name="训练记录",
    )
    exercise_name = models.CharField(max_length=128, verbose_name="动作名称")
    sets = models.PositiveIntegerField(null=True, blank=True, verbose_name="组数")
    reps = models.PositiveIntegerField(null=True, blank=True, verbose_name="次数")
    weight = models.CharField(max_length=32, blank=True, default="", verbose_name="负荷/重量")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True, verbose_name="时长（秒）")
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="备注")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="排序")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_training_exercises"
        verbose_name = "训练动作"
        verbose_name_plural = "训练动作"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        """返回动作名称。"""
        return self.exercise_name


class HomeTrainingPlan(models.Model):
    """家庭训练计划。

    康复师课后为客户创建的家庭训练方案。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="home_training_plans",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="home_training_plans",
        verbose_name="客户",
    )
    title = models.CharField(max_length=128, default="家庭训练", verbose_name="标题")
    frequency = models.CharField(max_length=64, blank=True, default="", verbose_name="频率")
    note = models.TextField(blank=True, default="", verbose_name="注意事项")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_home_training_plans"
        verbose_name = "家庭训练计划"
        verbose_name_plural = "家庭训练计划"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_hometrain_therapist"),
        ]

    def __str__(self) -> str:
        """返回计划描述。"""
        return f"{self.title} - {self.customer.name}"


class HomeTrainingExercise(models.Model):
    """家庭训练计划中的动作。"""

    plan = models.ForeignKey(
        HomeTrainingPlan,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="exercises",
        verbose_name="所属计划",
    )
    exercise_name = models.CharField(max_length=128, verbose_name="动作名称")
    sets = models.PositiveIntegerField(null=True, blank=True, verbose_name="组数")
    reps = models.PositiveIntegerField(null=True, blank=True, verbose_name="次数")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True, verbose_name="时长（秒）")
    frequency = models.CharField(max_length=64, blank=True, default="", verbose_name="频率")
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="注意事项")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="排序")

    class Meta:
        db_table = "tb_home_training_exercises"
        verbose_name = "家庭训练动作"
        verbose_name_plural = "家庭训练动作"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        """返回动作名称。"""
        return self.exercise_name
