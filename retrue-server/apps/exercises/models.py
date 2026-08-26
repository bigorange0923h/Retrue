"""exercises：动作库模型。

提供官方基础动作库与康复师个人动作库。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Exercise(models.Model):
    """训练动作。

    官方动作（is_official=True）由系统维护，不随康复师删除；
    个人动作由康复师创建。

    字段：
        therapist: 创建者（官方动作为 None）。
        name: 正式名称。
        body_part: 训练部位。
        description: 动作说明。
        precautions: 注意事项。
        contraindications: 禁忌。
        is_official: 是否官方动作。
        created_at / updated_at: 时间戳。
    """

    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="exercises",
        verbose_name="创建者",
    )
    name = models.CharField(max_length=128, verbose_name="动作名称")
    body_part = models.CharField(max_length=64, blank=True, default="", verbose_name="训练部位")
    description = models.TextField(blank=True, default="", verbose_name="动作说明")
    precautions = models.TextField(blank=True, default="", verbose_name="注意事项")
    contraindications = models.TextField(blank=True, default="", verbose_name="禁忌")
    is_official = models.BooleanField(default=False, verbose_name="是否官方动作")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "训练动作"
        verbose_name_plural = "训练动作"
        ordering = ["-is_official", "name"]
        indexes = [
            models.Index(fields=["therapist"], name="idx_exercise_therapist"),
        ]

    def __str__(self) -> str:
        """返回动作名称。"""
        return self.name


class ExerciseAlias(models.Model):
    """动作别名。

    用于动作的自然语言识别匹配（如"臀桥"别名"桥式"）。
    """

    exercise = models.ForeignKey(
        Exercise, on_delete=models.CASCADE, related_name="aliases", verbose_name="动作"
    )
    alias = models.CharField(max_length=64, verbose_name="别名")

    class Meta:
        verbose_name = "动作别名"
        verbose_name_plural = "动作别名"

    def __str__(self) -> str:
        """返回别名。"""
        return self.alias
