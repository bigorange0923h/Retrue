from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("schedules", "0007_rehab_plan_courses"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="coursetype",
            name="default_stage",
        ),
        migrations.RemoveField(
            model_name="coursetype",
            name="default_notes",
        ),
    ]
