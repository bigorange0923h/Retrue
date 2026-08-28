"""courses：课时管理模型。

课时包记录客户购买的课时总数与已消耗数。
课时消耗需在课程完成且训练记录确认后触发，请假/取消不扣。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CoursePackage(models.Model):
    """课时包。

    记录客户购买的课时总数、已消耗与剩余课时。

    字段：
        therapist: 康复师（数据隔离）。
        customer: 关联客户。
        name: 课时包名称。
        total_sessions: 总课时数。
        used_sessions: 已消耗课时数。
        note: 备注。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_packages",
        verbose_name="康复师",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="course_packages",
        verbose_name="客户",
    )
    name = models.CharField(max_length=128, default="默认课时包", verbose_name="课时包名称")
    total_sessions = models.DecimalField(
        max_digits=8, decimal_places=1, default=0, verbose_name="总课时"
    )
    used_sessions = models.DecimalField(
        max_digits=8, decimal_places=1, default=0, verbose_name="已消耗课时"
    )
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_course_packages"
        verbose_name = "课时包"
        verbose_name_plural = "课时包"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "customer"], name="idx_coursepkg_therapist"),
        ]

    @property
    def remaining_sessions(self) -> Decimal:
        """剩余课时（支持半课 0.5）。"""
        from decimal import Decimal

        remaining = self.total_sessions - self.used_sessions
        return remaining if remaining > Decimal("0") else Decimal("0")

    def __str__(self) -> str:
        """返回课时包描述。"""
        return f"{self.name} - {self.customer.name}"


class CourseAdjustment(models.Model):
    """课时人工调整记录。

    人工调整剩余课时时必须记录原因，用于审计追溯。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_adjustments",
        verbose_name="康复师",
    )
    package = models.ForeignKey(
        CoursePackage,
        on_delete=models.CASCADE,
        related_name="adjustments",
        verbose_name="课时包",
    )
    delta = models.DecimalField(
        max_digits=6, decimal_places=1, verbose_name="调整量（正负，支持半课 0.5）"
    )
    reason = models.CharField(max_length=255, verbose_name="调整原因")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = "tb_course_adjustments"
        verbose_name = "课时调整"
        verbose_name_plural = "课时调整"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """返回调整描述。"""
        return f"{self.delta:+d} 课时 - {self.reason}"
