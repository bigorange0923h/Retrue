"""为课表增加面向业务的安排类型，并整理历史数据。"""

from django.db import migrations, models


def fill_arrangement_type(apps, schema_editor):
    """历史上关联计划课程的排课归为计划课程，其余归为其他事项。"""
    CourseSession = apps.get_model("schedules", "CourseSession")
    CourseSession.objects.filter(plan_course__isnull=False).update(arrangement_type="plan")
    CourseSession.objects.filter(plan_course__isnull=True).update(arrangement_type="other")


class Migration(migrations.Migration):

    dependencies = [
        ("schedules", "0010_alter_coursesession_customer_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursesession",
            name="arrangement_type",
            field=models.CharField(
                choices=[
                    ("plan", "计划课程"),
                    ("initial_assessment", "首次评估"),
                    ("reassessment", "阶段复评"),
                    ("other", "其他事项"),
                ],
                default="other",
                max_length=24,
                verbose_name="安排类型",
            ),
        ),
        migrations.RunPython(fill_arrangement_type, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="coursesession",
            index=models.Index(
                fields=["therapist", "arrangement_type", "date"],
                name="idx_course_arrangement_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="coursesession",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(arrangement_type="plan", plan_course__isnull=False)
                    | (
                        ~models.Q(arrangement_type="plan")
                        & models.Q(plan_course__isnull=True)
                    )
                ),
                name="chk_session_arrangement_plan",
            ),
        ),
    ]
