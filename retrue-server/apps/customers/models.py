"""customers：客户档案模型。

客户是康复服务的主体，归属于某个康复师，实现数据隔离。
列表场景默认脱敏手机号，仅编辑场景返回完整号码。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CustomerStatus(models.TextChoices):
    """客户状态。"""

    ACTIVE = "active", "正常"
    PAUSED = "paused", "暂停"
    CLOSED = "closed", "结案"


class Customer(models.Model):
    """客户档案。

    字段：
        therapist: 主负责康复师（数据隔离归属）。
        name: 客户姓名。
        phone: 完整手机号，仅受控编辑场景返回。
        phone_masked: 脱敏手机号（如 138****1234），列表默认展示。
        gender: 性别（男/女/未知）。
        birth_date: 出生日期，可空。
        occupation: 职业，可空。
        sport: 运动项目，可空。
        main_issue: 当前主要康复问题。
        injury_date: 受伤日期，可空。
        surgery_date: 手术日期，可空。
        status: 客户状态。
        first_visit_date: 首次到店日期。
        note: 代课等备注。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customers",
        verbose_name="主负责康复师",
    )
    name = models.CharField(max_length=64, verbose_name="客户姓名")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="手机号")
    phone_masked = models.CharField(max_length=20, blank=True, default="", verbose_name="脱敏手机号")
    gender = models.CharField(
        max_length=10,
        blank=True,
        default="",
        choices=[("male", "男"), ("female", "女")],
        verbose_name="性别",
    )
    birth_date = models.DateField(null=True, blank=True, verbose_name="出生日期")
    occupation = models.CharField(max_length=64, blank=True, default="", verbose_name="职业")
    sport = models.CharField(max_length=64, blank=True, default="", verbose_name="运动项目")
    main_issue = models.CharField(max_length=255, blank=True, default="", verbose_name="主要问题")
    injury_date = models.DateField(null=True, blank=True, verbose_name="受伤日期")
    surgery_date = models.DateField(null=True, blank=True, verbose_name="手术日期")
    status = models.CharField(
        max_length=10,
        choices=CustomerStatus.choices,
        default=CustomerStatus.ACTIVE,
        verbose_name="状态",
    )
    first_visit_date = models.DateField(null=True, blank=True, verbose_name="首次到店日期")
    note = models.CharField(max_length=500, blank=True, default="", verbose_name="备注")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "客户"
        verbose_name_plural = "客户"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["therapist", "status"], name="idx_customer_therapist_status"),
            models.Index(fields=["therapist", "name"], name="idx_customer_therapist_name"),
        ]

    def __str__(self) -> str:
        """返回客户姓名。"""
        return self.name

    def save(self, *args, **kwargs):
        """保存时自动同步脱敏手机号，保证与完整号码一致。"""
        self.phone_masked = mask_phone(self.phone)
        super().save(*args, **kwargs)


def mask_phone(phone: str) -> str:
    """生成脱敏手机号。

    对 11 位手机号保留前 3 位与后 4 位，中间以 **** 替代；
    非 11 位号码整体脱敏为空字符串。

    参数：
        phone: 完整手机号。
    返回：
        脱敏后的手机号字符串。
    """
    if not phone:
        return ""
    digits = phone.strip()
    if len(digits) == 11:
        return f"{digits[:3]}****{digits[-4:]}"
    return ""
