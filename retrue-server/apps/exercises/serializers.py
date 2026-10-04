"""exercises：动作库序列化器。"""

from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from apps.exercises.models import Exercise, ExerciseAlias


class ExerciseAliasSerializer(serializers.ModelSerializer):
    """动作别名输入/输出。"""

    class Meta:
        model = ExerciseAlias
        fields = ["id", "alias"]


class ExerciseSerializer(serializers.ModelSerializer):
    """动作输出/输入，含别名。"""

    aliases = ExerciseAliasSerializer(many=True, required=False)

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

    def validate_aliases(self, value: list) -> list:
        """拒绝空白和重复别名，保留动作名称与别名的明确区别。"""
        normalized = [row["alias"].strip().casefold() for row in value]
        if len(normalized) != len(set(normalized)):
            raise serializers.ValidationError("同一动作的别名不能重复")
        return value

    @transaction.atomic
    def create(self, validated_data: dict) -> Exercise:
        """原子创建个人动作与别名。"""
        aliases = validated_data.pop("aliases", [])
        exercise = Exercise.objects.create(**validated_data)
        for row in aliases:
            ExerciseAlias.objects.create(exercise=exercise, alias=row["alias"])
        return exercise

    @transaction.atomic
    def update(self, instance: Exercise, validated_data: dict) -> Exercise:
        """原子更新动作；提交 aliases 时整体替换，省略保留原值。"""
        aliases = validated_data.pop("aliases", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if aliases is not None:
            instance.aliases.all().delete()
            for row in aliases:
                ExerciseAlias.objects.create(exercise=instance, alias=row["alias"])
        instance._prefetched_objects_cache = {}
        return instance
