"""knowledge：知识条目序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.knowledge.models import (
    CandidateStatus,
    CustomerKnowledgeItem,
    KnowledgeCandidate,
    KnowledgeCategory,
    KnowledgeImportance,
    MemoryEpisode,
    MemoryType,
)


class KnowledgeItemSerializer(serializers.ModelSerializer):
    """知识条目输出/输入。

    正式知识条目，含分类、来源、重要级别与生效状态。
    安全限制类高重要性条目在返回时置顶（排序在后端处理）。
    """

    category_display = serializers.CharField(source="get_category_display", read_only=True)
    importance_display = serializers.CharField(source="get_importance_display", read_only=True)
    memory_type_display = serializers.CharField(source="get_memory_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CustomerKnowledgeItem
        fields = [
            "id",
            "customer",
            "category",
            "category_display",
            "memory_type",
            "memory_type_display",
            "memory_key",
            "content",
            "normalized_value",
            "source",
            "source_type",
            "source_id",
            "source_message_id",
            "importance",
            "importance_display",
            "importance_score",
            "confidence",
            "is_active",
            "status",
            "status_display",
            "confirmed_by_user",
            "effective_from",
            "effective_to",
            "last_confirmed_at",
            "supersedes_memory",
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
    memory_type_display = serializers.CharField(source="get_memory_type_display", read_only=True)
    conflict_type_display = serializers.CharField(source="get_conflict_type_display", read_only=True)
    conflict_memory_content = serializers.CharField(source="conflict_memory.content", read_only=True)

    class Meta:
        model = KnowledgeCandidate
        fields = [
            "id",
            "customer",
            "content",
            "category",
            "category_display",
            "memory_type",
            "memory_type_display",
            "memory_key",
            "normalized_value",
            "confidence",
            "importance_score",
            "evidence",
            "conflict_type",
            "conflict_type_display",
            "conflict_memory",
            "conflict_memory_content",
            "source_conversation",
            "source_message",
            "source_ref",
            "resolution_action",
            "suggested_at",
            "status",
            "status_display",
        ]
        extra_kwargs = {
            "content": {"required": True},
            "customer": {"write_only": True},
            "conflict_type": {"read_only": True},
            "conflict_memory": {"read_only": True},
            "source_conversation": {"read_only": True},
            "source_message": {"read_only": True},
            "resolution_action": {"read_only": True},
        }


class CandidateConfirmSerializer(serializers.Serializer):
    """候选确认/拒绝输入。"""

    action = serializers.ChoiceField(
        choices=["confirm", "reject", "replace", "keep_existing", "coexist", "defer"]
    )
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
    memory_type = serializers.ChoiceField(choices=MemoryType.choices, required=False)
    importance_score = serializers.IntegerField(min_value=1, max_value=5, required=False)
    supersede_existing = serializers.BooleanField(required=False, default=False)
    resolved_memory_key = serializers.CharField(max_length=100, required=False, allow_blank=False)


class MemoryEpisodeSerializer(serializers.ModelSerializer):
    """历史讨论事件及来源输出。"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = MemoryEpisode
        fields = [
            "id", "customer", "conversation", "episode_key", "title", "summary", "key_points",
            "decisions", "next_actions", "importance_score", "confidence", "status",
            "status_display", "source_start_message_id", "source_end_message_id", "decided_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class EpisodeDecisionSerializer(serializers.Serializer):
    """Episode 候选确认或拒绝输入。"""

    action = serializers.ChoiceField(choices=["confirm", "reject"])
