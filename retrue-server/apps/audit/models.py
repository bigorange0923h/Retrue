"""audit：审计日志基础模型与记录服务。

用于记录正式业务数据的变更历史，保留修改前后的快照、修改原因、
操作人和时间，确保历史记录可追溯。AI 不允许直接修改正式数据，
所有变更须经过人工确认并通过审计服务记录。
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditAction(models.TextChoices):
    """审计动作类型。"""

    CREATE = "create", "创建"
    UPDATE = "update", "更新"
    DELETE = "delete", "删除"
    CONFIRM = "confirm", "确认"  # AI 草稿经人工确认后落库
    LOGIN = "login", "登录"
    LOGOUT = "logout", "登出"


class AuditLog(models.Model):
    """审计日志。

    记录一次对业务对象的变更，含操作前与操作后的数据快照。

    字段：
        actor: 操作人（系统用户），可空表示系统操作。
        action: 动作类型，见 AuditAction。
        content_type / object_id: 被操作业务对象的通用关联。
        before_data: 操作前快照（JSON）。
        after_data: 操作后快照（JSON）。
        reason: 修改原因，修改正式记录时必填。
        created_at: 记录创建时间。
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="操作人",
    )
    action = models.CharField(max_length=20, choices=AuditAction.choices, verbose_name="动作")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.CharField(max_length=64, null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")
    before_data = models.JSONField(default=dict, blank=True, verbose_name="操作前快照")
    after_data = models.JSONField(default=dict, blank=True, verbose_name="操作后快照")
    reason = models.CharField(max_length=500, blank=True, default="", verbose_name="修改原因")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="记录时间")

    class Meta:
        db_table = "tb_audit_logs"
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="idx_audit_content"),
            models.Index(fields=["created_at"], name="idx_audit_created"),
        ]

    def __str__(self) -> str:
        """返回审计日志的简要描述。"""
        return f"{self.action} #{self.object_id or ''} by {self.actor_id or 'system'}"


def write_audit_log(
    *,
    actor,
    action: str,
    obj: Any = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
) -> AuditLog:
    """记录一条审计日志。

    参数：
        actor: 操作人（User 实例或 None）。
        action: 动作类型，取值见 AuditAction。
        obj: 被操作的业务对象实例；提供时自动解析 content_type 与 object_id。
        before: 操作前数据快照（dict）。
        after: 操作后数据快照（dict）。
        reason: 修改原因；修改正式记录时必须填写。
    返回：
        已创建的 AuditLog 实例。
    """
    content_type = None
    object_id = None
    if obj is not None:
        content_type = ContentType.objects.get_for_model(obj)
        object_id = str(obj.pk)

    return AuditLog.objects.create(
        actor=actor if actor is not None else None,
        action=action,
        content_type=content_type,
        object_id=object_id,
        before_data=json.loads(json.dumps(before or {}, ensure_ascii=False)),
        after_data=json.loads(json.dumps(after or {}, ensure_ascii=False)),
        reason=reason,
    )
