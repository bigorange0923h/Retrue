"""training：训练记录序列化器。"""

from __future__ import annotations

from rest_framework import serializers

from apps.training.models import TrainingExercise, TrainingRecord


class TrainingExerciseSerializer(serializers.ModelSerializer):
    """训练动作输入/输出。"""

    class Meta:
        model = TrainingExercise
        fields = [
            "id",
            "exercise_name",
            "sets",
            "reps",
            "weight",
            "duration_seconds",
            "note",
            "sort_order",
        ]
        extra_kwargs = {"exercise_name": {"required": True}}


class TrainingRecordSerializer(serializers.ModelSerializer):
    """训练记录输出，包含动作明细。"""

    exercises = TrainingExerciseSerializer(many=True, required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = TrainingRecord
        fields = [
            "id",
            "customer",
            "customer_name",
            "course_session",
            "training_date",
            "customer_feedback",
            "therapist_observation",
            "next_plan",
            "note",
            "exercises",
            "created_at",
            "updated_at",
        ]


class TrainingRecordCreateSerializer(serializers.ModelSerializer):
    """训练记录创建/更新输入。

    支持嵌套提交动作明细（exercises）。
    """

    exercises = TrainingExerciseSerializer(many=True, required=False)

    class Meta:
        model = TrainingRecord
        fields = [
            "customer",
            "course_session",
            "training_date",
            "customer_feedback",
            "therapist_observation",
            "next_plan",
            "note",
            "exercises",
        ]
        extra_kwargs = {"training_date": {"required": True}}

    def create(self, validated_data: dict) -> TrainingRecord:
        """创建训练记录及其动作明细。"""
        exercises_data = validated_data.pop("exercises", [])
        record = TrainingRecord.objects.create(**validated_data)
        self._create_exercises(record, exercises_data)
        return record

    def update(self, instance: TrainingRecord, validated_data: dict) -> TrainingRecord:
        """更新训练记录并同步动作明细（整体替换）。"""
        exercises_data = validated_data.pop("exercises", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if exercises_data is not None:
            instance.exercises.all().delete()
            self._create_exercises(instance, exercises_data)
        return instance

    def _create_exercises(self, record: TrainingRecord, exercises_data: list) -> None:
        """批量创建动作明细。"""
        for index, item in enumerate(exercises_data):
            item["sort_order"] = item.get("sort_order", index)
            TrainingExercise.objects.create(training_record=record, **item)


class TrainingRecordRevisionSerializer(serializers.Serializer):
    """训练记录人工修订输入。

    修改正式记录必须提供修改原因。
    """

    reason = serializers.CharField(max_length=500, write_only=True)
