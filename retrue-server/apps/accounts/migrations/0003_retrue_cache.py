"""为 DatabaseCache 创建 retrue_cache 表。

登录限流与多进程共享计数以 PostgreSQL 数据库缓存为后端，该表不属于任何
Django 模型，通过本迁移创建。生产部署与测试库均会执行。
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_user_table"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS retrue_cache (
                cache_key varchar(255) NOT NULL PRIMARY KEY,
                value text NOT NULL,
                expires timestamptz NOT NULL
            );
            CREATE INDEX IF NOT EXISTS retrue_cache_expires
                ON retrue_cache (expires);
            """,
            reverse_sql="""
            DROP TABLE IF EXISTS retrue_cache;
            """,
        ),
    ]
