"""accounts：认证与用户模型。

V1 采用 Session + Cookie 认证，使用 Django 内置用户模型扩展。
自定义 User 模型从项目初始定义，便于后续扩展字段而不必重建表。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """系统用户。

    继承 Django 内置 AbstractUser，保留 username/password 等认证字段。
    V1 中一个 User 对应一个康复师账号。
    """

    class Meta:
        db_table = "tb_users"
        verbose_name = "系统用户"
        verbose_name_plural = "系统用户"

    def __str__(self) -> str:
        """返回用户的展示名。"""
        return self.get_username()
