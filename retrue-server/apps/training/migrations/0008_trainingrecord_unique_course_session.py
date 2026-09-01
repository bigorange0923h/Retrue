"""为每节非空排课只允许一条正式训练记录。"""

from django.db import migrations, models
from django.db.models import Count


def validate_course_session_uniqueness(apps, schema_editor) -> None:
    """在添加唯一约束前检查历史重复排课，避免静默丢弃正式记录。"""
    training_record = apps.get_model("training", "TrainingRecord")
    duplicates = (
        training_record.objects.filter(course_session__isnull=False)
        .values("course_session_id")
        .annotate(record_count=Count("id"))
        .filter(record_count__gt=1)
    )
    if duplicates.exists():
        duplicate_ids = ", ".join(str(row["course_session_id"]) for row in duplicates[:20])
        raise RuntimeError(
            "tb_training_records 存在重复 course_session，无法添加唯一约束；"
            f"请先处理排课 ID：{duplicate_ids}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0007_alter_hometrainingexercise_plan_and_more"),
    ]

    operations = [
        migrations.RunPython(validate_course_session_uniqueness, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="trainingrecord",
            constraint=models.UniqueConstraint(
                condition=models.Q(course_session__isnull=False),
                fields=("course_session",),
                name="uq_training_record_course_session",
            ),
        ),
    ]
