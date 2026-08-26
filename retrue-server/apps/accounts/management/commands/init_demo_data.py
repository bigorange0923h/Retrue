"""初始化演示数据命令。

用于在开发环境中创建可重复执行的演示账号、演示客户与课程。
所有数据均为明确标记的模拟数据，不含真实客户健康信息。
用法：python manage.py init_demo_data
"""

from __future__ import annotations

from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.customers.models import Customer
from apps.schedules.models import CourseSession
from apps.therapists.models import Therapist

User = get_user_model()


class Command(BaseCommand):
    """初始化演示数据。"""

    help = "初始化演示数据：管理员账号、演示康复师、演示客户与课程"

    def handle(self, *args, **options):
        """执行初始化逻辑。"""
        self.stdout.write(self.style.NOTICE("开始初始化演示数据..."))

        therapist = self._ensure_accounts()

        # 创建演示客户
        demo_customers = self._ensure_customers(therapist)

        # 创建演示课程（今日 + 明日）
        self._ensure_courses(therapist, demo_customers)

        self.stdout.write(self.style.SUCCESS("演示数据初始化完成"))

    def _ensure_accounts(self) -> User:
        """创建管理员与演示康复师账号。

        返回：
            演示康复师用户实例。
        """
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

        demo, demo_created = User.objects.get_or_create(username="retrue")
        demo.set_password("retrue123")
        demo.is_active = True
        demo.save()
        Therapist.objects.get_or_create(
            user=demo,
            defaults={"name": "张康复师", "phone": "13800138000"},
        )
        if demo_created:
            self.stdout.write(self.style.SUCCESS("演示康复师 retrue / retrue123 已就绪"))
        return demo

    def _ensure_customers(self, therapist: User) -> list:
        """创建演示客户。

        参数：
            therapist: 演示康复师用户。
        返回：
            演示客户实例列表。
        """
        customers_data = [
            {"name": "测试客户A", "phone": "13800138000", "gender": "male", "main_issue": "左膝前侧疼痛"},
            {"name": "测试客户B", "phone": "13800138001", "gender": "female", "main_issue": "肩关节活动度受限"},
            {"name": "测试客户C", "phone": "13800138002", "gender": "male", "main_issue": "下背痛"},
        ]
        created = []
        for data in customers_data:
            customer, is_new = Customer.objects.get_or_create(
                therapist=therapist,
                name=data["name"],
                defaults=data,
            )
            created.append(customer)
            if is_new:
                self.stdout.write(f"创建演示客户：{customer.name}")
        return created

    def _ensure_courses(self, therapist: User, customers: list) -> None:
        """创建演示课程（今日与明日）。

        参数：
            therapist: 演示康复师用户。
            customers: 演示客户列表。
        """
        today = date.today()
        schedules = [
            (today, time(10, 0), time(11, 0), customers[0]),
            (today, time(14, 0), time(15, 0), customers[1]),
            (today + timedelta(days=1), time(9, 0), time(10, 0), customers[2]),
        ]
        for day, start, end, customer in schedules:
            _, is_new = CourseSession.objects.get_or_create(
                therapist=therapist,
                customer=customer,
                date=day,
                start_time=start,
                defaults={"end_time": end, "status": "scheduled"},
            )
            if is_new:
                self.stdout.write(f"创建演示课程：{day} {customer.name}")
