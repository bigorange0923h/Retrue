"""初始化演示数据命令。

用于在开发环境中创建可重复执行的演示账号，避免手工创建。
用法：python manage.py init_demo_data
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.therapists.models import Therapist

User = get_user_model()


class Command(BaseCommand):
    """初始化演示康复师账号与管理员账号。"""

    help = "初始化演示数据：管理员账号与演示康复师账号"

    def handle(self, *args, **options):
        """执行初始化逻辑。"""
        self.stdout.write(self.style.NOTICE("开始初始化演示数据..."))

        # 创建管理员账号
        admin, admin_created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@retrue.local", "is_staff": True, "is_superuser": True},
        )
        if admin_created:
            admin.set_password("admin123")
            admin.save()
            self.stdout.write(self.style.SUCCESS("管理员账号 admin 已创建"))
        else:
            self.stdout.write("管理员账号 admin 已存在，跳过")

        # 创建演示康复师账号及 Therapist
        demo, demo_created = User.objects.get_or_create(username="retrue")
        demo.set_password("retrue123")
        demo.is_active = True
        demo.save()
        _, therapist_created = Therapist.objects.get_or_create(
            user=demo,
            defaults={"name": "张康复师", "phone": "13800138000"},
        )
        if demo_created or therapist_created:
            self.stdout.write(self.style.SUCCESS("演示康复师 retrue / retrue123 已就绪"))
        else:
            self.stdout.write("演示康复师 retrue 已存在，跳过")

        self.stdout.write(self.style.SUCCESS("演示数据初始化完成"))
