"""therapists：康复师身份模型。

V1 中一名康复师对应一个系统用户账号，康复师是客户数据的归属主体，
用于实现康复师间的数据隔离。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Therapist(models.Model):
    """康复师。

    通过 OneToOne 与系统用户关联，作为客户、训练记录等业务数据的归属者。

    字段：
        user: 关联的系统用户（OneToOne）。
        name: 康复师姓名，独立于登录用户名存储。
        phone: 联系手机号，可空。
        is_active: 是否在职/可用。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        db_constraint=False,
        on_delete=models.CASCADE,
        related_name="therapist_profile",
        verbose_name="关联用户",
    )
    name = models.CharField(max_length=64, verbose_name="康复师姓名")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="联系电话")
    is_active = models.BooleanField(default=True, verbose_name="是否在职")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "tb_therapists"
        verbose_name = "康复师"
        verbose_name_plural = "康复师"

    def __str__(self) -> str:
        """返回康复师的展示名。"""
        return self.name
