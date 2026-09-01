"""AssistantTask 统一任务、执行和事件模型。

本模块只描述任务编排基础设施，不包含任何具体提示词或 AI 供应商逻辑。
任务与一次执行（run）使用独立状态机，便于同一任务失败重试、暂停后恢复，
并保留工具调用和状态变更的可追溯记录。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AssistantTaskStatus(models.TextChoices):
    """助手任务生命周期状态。"""

    PENDING = "pending", "待处理"
    RUNNING = "running", "执行中"
    WAITING_USER = "waiting_user", "等待用户输入"
    WAITING_CONFIRMATION = "waiting_confirmation", "等待确认"
    BLOCKED = "blocked", "已阻塞"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "执行失败"
    CANCELLED = "cancelled", "已取消"
    EXPIRED = "expired", "已过期"


class AssistantRunStatus(models.TextChoices):
    """单次助手执行状态，与任务状态相互独立。"""

    QUEUED = "queued", "排队中"
    RUNNING = "running", "执行中"
    SUCCEEDED = "succeeded", "成功"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"
    TIMED_OUT = "timed_out", "超时"


class ToolExecutionStatus(models.TextChoices):
    """一次工具调用的执行状态。"""

    PENDING = "pending", "待执行"
    RUNNING = "running", "执行中"
    SUCCEEDED = "succeeded", "成功"
    FAILED = "failed", "失败"
    CANCELLED = "cancelled", "已取消"


class AssistantTask(models.Model):
    """统一的助手任务上下文与生命周期记录。

    任务只保存编排状态、业务资源引用和 AI 草稿/结果引用，不保存提示词。
    所有外键均关闭数据库物理约束，关联存在性和康复师归属由 service 校验。

    字段：
        therapist/customer/conversation: 任务归属与上下文，可按需为空。
        skill_code/task_type/invocation_mode/origin: 任务分类和调用入口。
        context_resource_*: 当前任务关联的业务资源引用。
        business_key/client_request_id: 业务复用键和客户端幂等键。
        status/current_step/missing_fields/state_data: 可恢复状态。
        draft/result_resource_*: AI 草稿和最终结果资源引用。
        version: 每次状态或编排数据变化递增的版本号。
        last_activity_at/expires_at/completed_at/cancelled_at: 生命周期时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="assistant_tasks",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_tasks",
        verbose_name="客户",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_tasks",
        verbose_name="会话",
    )

    skill_code = models.CharField(max_length=100, blank=True, default="", verbose_name="技能代码")
    task_type = models.CharField(max_length=64, blank=True, default="", verbose_name="任务类型")
    invocation_mode = models.CharField(
        max_length=32,
        blank=True,
        default="manual",
        verbose_name="调用模式",
    )
    origin = models.CharField(max_length=64, blank=True, default="", verbose_name="任务来源")
    context_resource_type = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="上下文资源类型",
    )
    context_resource_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="上下文资源标识",
    )
    business_key = models.CharField(max_length=255, blank=True, default="", verbose_name="业务复用键")
    client_request_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="客户端请求幂等键",
    )

    status = models.CharField(
        max_length=20,
        choices=AssistantTaskStatus.choices,
        default=AssistantTaskStatus.PENDING,
        verbose_name="任务状态",
    )
    current_step = models.CharField(max_length=128, blank=True, default="", verbose_name="当前步骤")
    missing_fields = models.JSONField(default=list, blank=True, verbose_name="待补充字段")
    state_data = models.JSONField(default=dict, blank=True, verbose_name="任务状态数据")
    draft_resource_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="草稿资源类型",
    )
    draft_resource_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="草稿资源标识",
    )
    result_resource_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="结果资源类型",
    )
    result_resource_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="结果资源标识",
    )
    version = models.PositiveIntegerField(default=1, verbose_name="任务版本")
    last_activity_at = models.DateTimeField(default=timezone.now, verbose_name="最近活动时间")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="过期时间")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="取消时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_assistant_tasks"
        verbose_name = "助手任务"
        verbose_name_plural = "助手任务"
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["therapist", "status", "updated_at"], name="idx_astask_scope_status"),
            models.Index(fields=["therapist", "customer", "status"], name="idx_astask_customer_status"),
            models.Index(fields=["therapist", "business_key"], name="idx_astask_business_key"),
            models.Index(fields=["therapist", "client_request_id"], name="idx_astask_client_request"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="chk_astask_version_pos",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[value for value, _ in AssistantTaskStatus.choices]),
                name="chk_astask_status_valid",
            ),
            models.UniqueConstraint(
                fields=["therapist", "client_request_id"],
                condition=~models.Q(client_request_id=""),
                name="uniq_astask_client_request",
            ),
            models.UniqueConstraint(
                fields=["therapist", "customer", "business_key"],
                condition=(
                    ~models.Q(business_key="")
                    & models.Q(customer__isnull=False)
                    & models.Q(
                        status__in=[
                            "pending",
                            "running",
                            "waiting_user",
                            "waiting_confirmation",
                            "blocked",
                            "failed",
                        ]
                    )
                ),
                name="uniq_astask_active_biz_customer",
            ),
            models.UniqueConstraint(
                fields=["therapist", "business_key"],
                condition=(
                    ~models.Q(business_key="")
                    & models.Q(customer__isnull=True)
                    & models.Q(
                        status__in=[
                            "pending",
                            "running",
                            "waiting_user",
                            "waiting_confirmation",
                            "blocked",
                            "failed",
                        ]
                    )
                ),
                name="uniq_astask_active_biz_general",
            ),
        ]

    @property
    def is_resumable(self) -> bool:
        """判断任务是否仍可被客户端恢复或继续处理。"""
        return self.status in {
            AssistantTaskStatus.PENDING,
            AssistantTaskStatus.RUNNING,
            AssistantTaskStatus.WAITING_USER,
            AssistantTaskStatus.WAITING_CONFIRMATION,
            AssistantTaskStatus.BLOCKED,
            AssistantTaskStatus.FAILED,
        }

    @property
    def last_activity(self):
        """提供不带 ``_at`` 后缀的兼容读取属性。"""
        return self.last_activity_at

    def __str__(self) -> str:
        """返回任务展示标识。"""
        return f"{self.task_type or self.skill_code or '助手任务'} #{self.pk}"


class AssistantRun(models.Model):
    """助手任务的一次执行尝试。

    同一任务可以有多条执行记录；本表的 ``status`` 表示这一次运行，
    不应与 AssistantTask 的总体状态混用。
    """

    task = models.ForeignKey(
        AssistantTask,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="runs",
        verbose_name="助手任务",
    )
    client_request_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="本次执行幂等键",
    )
    attempt = models.PositiveIntegerField(default=1, verbose_name="执行尝试次数")
    status = models.CharField(
        max_length=20,
        choices=AssistantRunStatus.choices,
        default=AssistantRunStatus.QUEUED,
        verbose_name="执行状态",
    )
    trigger_message = models.ForeignKey(
        "conversations.Message",
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_runs",
        verbose_name="触发消息",
    )
    provider = models.CharField(max_length=64, blank=True, default="", verbose_name="模型供应商")
    model = models.CharField(max_length=128, blank=True, default="", verbose_name="模型名称")
    input_summary = models.JSONField(default=dict, blank=True, verbose_name="执行输入脱敏摘要")
    output_summary = models.JSONField(default=dict, blank=True, verbose_name="执行输出脱敏摘要")
    error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="错误代码")
    error_message = models.CharField(max_length=500, blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_assistant_runs"
        verbose_name = "助手执行"
        verbose_name_plural = "助手执行"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["task", "status"], name="idx_asrun_task_status"),
            models.Index(fields=["task", "attempt"], name="idx_asrun_task_attempt"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(attempt__gte=1),
                name="chk_asrun_attempt_pos",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[value for value, _ in AssistantRunStatus.choices]),
                name="chk_asrun_status_valid",
            ),
            models.UniqueConstraint(
                fields=["task", "client_request_id"],
                condition=~models.Q(client_request_id=""),
                name="uniq_asrun_client_request",
            ),
        ]

    @property
    def run_number(self) -> int:
        """返回执行序号别名，便于训练接入按运行次数读取。"""
        return self.attempt

    @property
    def input_data(self):
        """返回输入摘要兼容属性；不代表完整原始输入。"""
        return self.input_summary

    @property
    def output_data(self):
        """返回输出摘要兼容属性；不代表完整原始输出。"""
        return self.output_summary

    def __str__(self) -> str:
        """返回执行记录展示标识。"""
        return f"任务 #{self.task_id} 第 {self.attempt} 次执行"


class ToolExecution(models.Model):
    """一次助手执行中的工具调用记录。"""

    run = models.ForeignKey(
        AssistantRun,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="tool_executions",
        verbose_name="助手执行",
    )
    task = models.ForeignKey(
        AssistantTask,
        db_constraint=False,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tool_executions",
        verbose_name="助手任务",
    )
    sequence = models.PositiveIntegerField(default=0, verbose_name="调用顺序")
    tool_name = models.CharField(max_length=128, verbose_name="工具名称")
    status = models.CharField(
        max_length=20,
        choices=ToolExecutionStatus.choices,
        default=ToolExecutionStatus.PENDING,
        verbose_name="工具执行状态",
    )
    input_summary = models.JSONField(default=dict, blank=True, verbose_name="工具输入脱敏摘要")
    output_summary = models.JSONField(default=dict, blank=True, verbose_name="工具输出脱敏摘要")
    is_write = models.BooleanField(default=False, verbose_name="是否写操作")
    requires_confirmation = models.BooleanField(default=False, verbose_name="是否需要确认")
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_tool_executions",
        verbose_name="确认人",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="确认时间")
    result_resource_type = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="结果资源类型",
    )
    result_resource_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="结果资源标识",
    )
    error_code = models.CharField(max_length=64, blank=True, default="", verbose_name="错误代码")
    error_message = models.CharField(max_length=500, blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_tool_executions"
        verbose_name = "工具执行"
        verbose_name_plural = "工具执行"
        ordering = ["run", "sequence", "id"]
        indexes = [
            models.Index(fields=["run", "status"], name="idx_toolexec_run_status"),
            models.Index(fields=["task", "status"], name="idx_toolexec_task_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(sequence__gte=0),
                name="chk_toolexec_sequence_nonneg",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[value for value, _ in ToolExecutionStatus.choices]),
                name="chk_toolexec_status_valid",
            ),
        ]

    @property
    def tool_code(self) -> str:
        """返回工具名称的兼容别名。"""
        return self.tool_name

    @property
    def arguments(self):
        """返回工具输入脱敏摘要别名。"""
        return self.input_summary

    @property
    def result(self):
        """返回工具输出脱敏摘要别名。"""
        return self.output_summary

    def __str__(self) -> str:
        """返回工具调用展示标识。"""
        return f"{self.tool_name} ({self.status})"


class TaskEvent(models.Model):
    """任务生命周期和编排事件的不可变审计记录。"""

    task = models.ForeignKey(
        AssistantTask,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="助手任务",
    )
    run = models.ForeignKey(
        AssistantRun,
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        verbose_name="关联执行",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_task_events",
        verbose_name="操作人",
    )
    event_type = models.CharField(max_length=64, verbose_name="事件类型")
    from_status = models.CharField(max_length=20, blank=True, default="", verbose_name="变更前状态")
    to_status = models.CharField(max_length=20, blank=True, default="", verbose_name="变更后状态")
    event_data = models.JSONField(default=dict, blank=True, verbose_name="事件数据")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="事件时间")

    class Meta:
        db_table = "tb_task_events"
        verbose_name = "任务事件"
        verbose_name_plural = "任务事件"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["task", "created_at"], name="idx_taskevent_task_time"),
            models.Index(fields=["task", "event_type"], name="idx_taskevent_task_type"),
        ]

    @property
    def data(self):
        """返回事件数据兼容别名。"""
        return self.event_data

    def __str__(self) -> str:
        """返回任务事件展示标识。"""
        return f"任务 #{self.task_id} {self.event_type}"
