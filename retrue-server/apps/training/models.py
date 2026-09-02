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


class TrainingExerciseActivityType(models.TextChoices):
    """训练项目类型：区分训练动作、康复治疗与按摩，避免把治疗误当动作。"""

    EXERCISE = "exercise", "训练动作"
    THERAPY = "therapy", "康复治疗"
    MASSAGE = "massage", "按摩"


class TrainingExercise(models.Model):
    """训练动作明细。

    一条训练记录包含多个项目，记录训练量（组数、次数、负荷、时长）与备注。
    通过 ``activity_type`` 区分训练动作、康复治疗与按摩；``quantity``/``unit``
    表达"康复按摩 1 次"这类以数量为单位、无法用组数/次数表达的项目。
    """

    training_record = models.ForeignKey(
        TrainingRecord,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="exercises",
        verbose_name="训练记录",
    )
    activity_type = models.CharField(
        max_length=16,
        choices=TrainingExerciseActivityType.choices,
        default=TrainingExerciseActivityType.EXERCISE,
        verbose_name="项目类型",
    )
    exercise_name = models.CharField(max_length=128, verbose_name="动作名称")
    sets = models.PositiveIntegerField(null=True, blank=True, verbose_name="组数")
    reps = models.PositiveIntegerField(null=True, blank=True, verbose_name="次数")
    quantity = models.PositiveIntegerField(null=True, blank=True, verbose_name="数量")
    unit = models.CharField(max_length=16, blank=True, default="", verbose_name="单位")
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


class TrainingRecordBatchItemStatus(models.TextChoices):
    """多客户批量训练补记的子项状态。"""

    PENDING = "pending", "待处理"
    SEARCHING_CUSTOMER = "searching_customer", "查找客户中"
    WAITING_CUSTOMER = "waiting_customer", "等待客户确认"
    WAITING_DRAFT = "waiting_draft", "等待草稿确认"
    SAVING = "saving", "保存中"
    COMPLETED = "completed", "已完成"
    SKIPPED = "skipped", "已跳过"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"


class TrainingRecordBatchItem(models.Model):
    """多客户批量训练补记的有序业务子项。

    一个父级批量任务包含多个子项，每个子项对应一位客户的一段训练描述。
    子项按 ``sequence`` 严格顺序推进；客户、草稿、正式记录均通过服务校验归属。

    字段：
        assistant_task: 父级批量任务（task_type=multi_customer_training_record）。
        sequence: 子项顺序，从 1 开始。
        source_message: 原始输入（保存在会话消息中，此处存原文引用或原文）。
        customer_name_hint: 从原文识别的客户姓名提示。
        customer: 确认后的客户，可空。
        parsed_payload: 该子项结构化训练内容（JSON）。
        ai_draft: 关联的 AI 草稿，可空。
        training_record: 确认后创建的正式训练记录，可空。
        status: 子项状态。
        confirmation_key: 正式保存幂等键。
        error_code / error_message: 失败信息。
    """

    assistant_task = models.ForeignKey(
        "assistant_tasks.AssistantTask",
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="batch_items",
        verbose_name="父级批量任务",
    )
    sequence = models.PositiveIntegerField(verbose_name="子项顺序")
    source_message = models.TextField(blank=True, default="", verbose_name="原始输入")
    customer_name_hint = models.CharField(max_length=64, blank=True, default="", verbose_name="客户姓名提示")
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="training_batch_items",
        verbose_name="客户",
    )
    parsed_payload = models.JSONField(default=dict, blank=True, verbose_name="结构化训练内容")
    ai_draft = models.ForeignKey(
        "ai.AiDraft",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_items",
        verbose_name="AI 草稿",
    )
    training_record = models.ForeignKey(
        TrainingRecord,
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_items",
        verbose_name="正式训练记录",
    )
    status = models.CharField(
        max_length=24,
        choices=TrainingRecordBatchItemStatus.choices,
        default=TrainingRecordBatchItemStatus.PENDING,
        verbose_name="子项状态",
    )
    confirmation_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_index=True,
        verbose_name="正式保存幂等键",
    )
    error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="错误代码")
    error_message = models.CharField(max_length=500, blank=True, default="", verbose_name="错误信息")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_training_record_batch_items"
        verbose_name = "训练批量子项"
        verbose_name_plural = "训练批量子项"
        ordering = ["sequence", "id"]
        indexes = [
            models.Index(fields=["assistant_task", "status"], name="idx_trb_item_task_status"),
            models.Index(fields=["assistant_task", "sequence"], name="idx_trb_item_task_seq"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assistant_task", "sequence"],
                name="uniq_trb_item_task_sequence",
            ),
        ]

    @property
    def is_terminal(self) -> bool:
        """判断子项是否已进入终态。"""
        return self.status in {
            TrainingRecordBatchItemStatus.COMPLETED,
            TrainingRecordBatchItemStatus.SKIPPED,
            TrainingRecordBatchItemStatus.FAILED,
            TrainingRecordBatchItemStatus.CANCELLED,
        }

    def __str__(self) -> str:
        """返回子项展示标识。"""
        return f"批量任务 #{self.assistant_task_id} 第 {self.sequence} 项"
