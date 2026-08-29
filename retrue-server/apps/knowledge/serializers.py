"""knowledge：知识条目序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.knowledge.models import (
    CandidateStatus,
    CustomerKnowledgeItem,
    KnowledgeCandidate,
    KnowledgeCategory,
    KnowledgeImportance,
)


class KnowledgeItemSerializer(serializers.ModelSerializer):
    """知识条目输出/输入。

    正式知识条目，含分类、来源、重要级别与生效状态。
    安全限制类高重要性条目在返回时置顶（排序在后端处理）。
    """

    category_display = serializers.CharField(source="get_category_display", read_only=True)
    importance_display = serializers.CharField(source="get_importance_display", read_only=True)

    class Meta:
        model = CustomerKnowledgeItem
        fields = [
            "id",
            "customer",
            "category",
            "category_display",
            "content",
            "source",
            "importance",
            "importance_display",
            "is_active",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "content": {"required": True},
            "customer": {"write_only": True},
        }


class KnowledgeCandidateSerializer(serializers.ModelSerializer):
    """知识候选输出/输入。

    AI 建议的候选记忆，需康复师确认后才转为正式知识。
    """

    category_display = serializers.CharField(source="get_category_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = KnowledgeCandidate
        fields = [
            "id",
            "customer",
            "content",
            "category",
            "category_display",
            "source_ref",
            "suggested_at",
            "status",
            "status_display",
        ]
        extra_kwargs = {
            "content": {"required": True},
            "customer": {"write_only": True},
        }


class CandidateConfirmSerializer(serializers.Serializer):
    """候选确认/拒绝输入。"""

    action = serializers.ChoiceField(choices=["confirm", "reject"])
    category = serializers.ChoiceField(
        choices=KnowledgeCategory.choices,
        required=False,
        help_text="确认时使用的知识分类，缺省沿用候选分类",
    )
    importance = serializers.ChoiceField(
        choices=KnowledgeImportance.choices,
        required=False,
        default=KnowledgeImportance.NORMAL,
        help_text="确认时的知识重要级别",
    )
