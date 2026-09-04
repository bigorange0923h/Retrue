from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversations", "0003_conversation_episode_analyzed_through_message_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="context_data",
            field=models.JSONField(blank=True, default=dict, verbose_name="受控会话工作上下文"),
        ),
    ]
