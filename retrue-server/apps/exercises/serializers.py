"""exercises：动作库序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.exercises.models import Exercise, ExerciseAlias


class ExerciseAliasSerializer(serializers.ModelSerializer):
    """动作别名输入/输出。"""

    class Meta:
        model = ExerciseAlias
        fields = ["id", "alias"]


class ExerciseSerializer(serializers.ModelSerializer):
    """动作输出/输入，含别名。"""

    aliases = ExerciseAliasSerializer(many=True, required=False, read_only=True)

    class Meta:
        model = Exercise
        fields = [
            "id",
            "name",
            "body_part",
            "description",
            "precautions",
            "contraindications",
            "is_official",
            "aliases",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"name": {"required": True}}
