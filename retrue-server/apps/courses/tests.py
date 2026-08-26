"""courses：课时管理接口单元测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.courses.models import CoursePackage
from apps.courses.services import consume_session
from apps.customers.models import Customer

User = get_user_model()


class CoursePackageApiTests(APITestCase):
    """课时包接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与课时包。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.package = CoursePackage.objects.create(
            therapist=self.therapist, customer=self.customer, name="20课时包", total_sessions=20
        )

    def test_create_package(self) -> None:
        """创建课时包。"""
        resp = self.client.post(
            reverse("course-package-list"),
            {"customer": self.customer.id, "name": "10课时包", "total_sessions": 10},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["remaining_sessions"], 10)

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建课时包。"""
        resp = self.client.post(
            reverse("course-package-list"),
            {"customer": self.other_customer.id, "total_sessions": 10},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_consume_session(self) -> None:
        """消耗课时减少剩余课时。"""
        consume_session(self.therapist, self.package)
        self.package.refresh_from_db()
        self.assertEqual(self.package.remaining_sessions, 19)

    def test_consume_when_empty_raises(self) -> None:
        """课时不足时消耗报错。"""
        self.package.used_sessions = self.package.total_sessions
        self.package.save()
        with self.assertRaises(ValueError):
            consume_session(self.therapist, self.package)

    def test_adjust_requires_reason(self) -> None:
        """人工调整课时必须填原因。"""
        resp = self.client.post(
            reverse("course-package-adjust", args=[self.package.id]),
            {"delta": -1, "reason": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_adjust_sessions(self) -> None:
        """人工调整课时（退还误扣课时）。"""
        # 先消耗 2 课时
        consume_session(self.therapist, self.package)
        consume_session(self.therapist, self.package)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 2)

        # 退还 1 课时
        resp = self.client.post(
            reverse("course-package-adjust", args=[self.package.id]),
            {"delta": -1, "reason": "误扣退还1课时"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 1)
        self.assertEqual(self.package.remaining_sessions, 19)
