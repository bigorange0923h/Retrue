import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0004_alter_courseadjustment_delta_and_more"),
        ("schedules", "0008_remove_coursetype_stage_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseadjustment",
            name="adjustment_type",
            field=models.CharField(
                choices=[("consumption", "课程扣减"), ("manual", "人工调整")],
                default="manual",
                max_length=16,
                verbose_name="流水类型",
            ),
        ),
        migrations.AddField(
            model_name="courseadjustment",
            name="course_session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="course_adjustments",
                to="schedules.coursesession",
                verbose_name="来源排课",
            ),
        ),
    ]
