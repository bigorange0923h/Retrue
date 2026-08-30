from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("training", "0005_trainingrecord_confirmed"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="trainingrecord",
            name="confirmed",
        ),
    ]
