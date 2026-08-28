"""schedules：课程/日程最小模型。

V1 不解析复杂 Excel 课表，仅建立最小课程表用于展示今日客户。
每个课程条目关联客户与康复师，记录日期与时间。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CourseSessionStatus(models.TextChoices):
    """课程状态。"""

    SCHEDULED = "scheduled", "待上课"
    COMPLETED = "completed", "已完成"
    CANCELLED = "cancelled", "已取消"
    ABSENT = "absent", "请假"


class CourseSession(models.Model):
    """课程/日程条目。

    字段：
        therapist: 康复师（数据隔离归属）。
        customer: 关联客户。
        course_name: 本次课程主题，例如初次评估、疼痛控制训练。
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
    course_name = models.CharField(max_length=128, default="康复训练", verbose_name="课程主题")
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
