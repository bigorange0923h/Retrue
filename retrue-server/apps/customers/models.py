"""customers：客户档案模型。

客户是康复服务的主体，归属于某个康复师，实现数据隔离。
列表场景默认脱敏手机号，仅编辑场景返回完整号码。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


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
        db_constraint=False,
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
        db_table = "tb_customers"
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
        """保存时自动同步脱敏手机号，保证与完整号码一致。

        新建客户时，若未手动指定首次到店日期，则自动设为建档当天
        （首次到店时间即视为手动创建客户的时间）。
        """
        if self.pk is None and self.first_visit_date is None:
            self.first_visit_date = timezone.localdate()
        self.phone_masked = mask_phone(self.phone)
        super().save(*args, **kwargs)


class CustomerAlias(models.Model):
    """客户别称。

    同一康复师范围内的别称用于文本目录匹配（如"阿成"→"黄伟成"）。
    别称严格隔离到康复师：`normalized_alias` 在 `therapist` 范围内唯一，
    冲突时由目录服务标记为歧义，绝不自动绑定。

    字段：
        therapist: 归属康复师（数据隔离）。
        customer: 别称指向的客户（归属由 customer 决定，保存前须校验一致）。
        alias: 用户可见的原始别称。
        normalized_alias: 规范化后的匹配键（NFKC + 去称谓/分隔符 + 折叠大小写）。
        created_at: 创建时间。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="customer_aliases",
        verbose_name="归属康复师",
    )
    customer = models.ForeignKey(
        Customer,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="aliases",
        verbose_name="客户",
    )
    alias = models.CharField(max_length=64, verbose_name="别称")
    normalized_alias = models.CharField(max_length=64, verbose_name="规范化别称")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        db_table = "tb_customer_aliases"
        verbose_name = "客户别称"
        verbose_name_plural = "客户别称"
        constraints = [
            models.UniqueConstraint(
                fields=["therapist", "normalized_alias"],
                name="uniq_therapist_normalized_alias",
            )
        ]
        indexes = [
            models.Index(fields=["therapist", "normalized_alias"], name="idx_alias_therapist_norm"),
        ]

    def __str__(self) -> str:
        """返回归一化别称与客户名的可读形式。"""
        return f"{self.normalized_alias} -> {self.customer_id}"


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
