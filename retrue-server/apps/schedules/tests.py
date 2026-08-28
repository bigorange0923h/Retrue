"""schedules：课程/今日日程接口单元测试。

覆盖今日课程查询、课程创建与数据隔离。
"""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer
from apps.schedules.models import CourseSession

User = get_user_model()


class CourseApiTests(APITestCase):
    """课程接口测试。"""

    def setUp(self) -> None:
        """准备康复师账号、客户与课程数据。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            date=date.today(),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )

    def test_today_courses_returns_masked_customer(self) -> None:
        """今日课程返回脱敏客户信息。"""
        resp = self.client.get(reverse("today-courses"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["customer_name"], "张三")
        self.assertIn("customer_phone_masked", items[0])

    def test_today_courses_isolates_therapist(self) -> None:
        """只能看到本人课程。"""
        CourseSession.objects.create(
            therapist=self.other,
            customer=self.other_customer,
            date=date.today(),
        )
        resp = self.client.get(reverse("today-courses"))
        self.assertEqual(len(resp.data["data"]), 1)

    def test_create_course_for_own_customer(self) -> None:
        """可为本人客户排课。"""
        resp = self.client.post(
            reverse("course-create"),
            {"customer": self.customer.id, "date": "2026-08-27", "start_time": "14:00:00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["customer_name"], "张三")

    def test_create_course_with_course_name(self) -> None:
        """课程主题随课程保存，用于区分康复周期内的不同课程。"""
        resp = self.client.post(
            reverse("course-create"),
            {"customer": self.customer.id, "date": "2026-08-27", "course_name": "力量重建训练"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["course_name"], "力量重建训练")

    def test_cannot_schedule_for_other_customer(self) -> None:
        """不能为其他康复师的客户排课。"""
        resp = self.client.post(
            reverse("course-create"),
            {"customer": self.other_customer.id, "date": "2026-08-27"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], 403)

    def test_today_courses_bad_date(self) -> None:
        """非法日期返回 400。"""
        resp = self.client.get(reverse("today-courses"), {"date": "not-a-date"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_calendar_returns_courses_in_requested_range(self) -> None:
        """课表接口仅返回所选日期范围内的本人课程。"""
        from datetime import timedelta

        today = date.today()
        start = today + timedelta(days=1)
        outside = today + timedelta(days=3)
        CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            date=start,
            start_time=time(14, 0),
        )
        CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            date=outside,
            start_time=time(15, 0),
        )
        resp = self.client.get(
            reverse("course-calendar"),
            {"start": start.isoformat(), "end": start.isoformat()},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["date"], start.isoformat())

    def test_calendar_rejects_invalid_range(self) -> None:
        """课表接口拒绝倒置的日期范围。"""
        resp = self.client.get(
            reverse("course-calendar"),
            {"start": "2026-08-28", "end": "2026-08-27"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_course_status(self) -> None:
        """康复师可将本人课程状态改为已取消。"""
        session = CourseSession.objects.get(therapist=self.therapist)
        resp = self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "cancelled", "note": "客户临时有事"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "cancelled")

    def test_cannot_update_other_therapist_course(self) -> None:
        """不能管理其他康复师的课程。"""
        session = CourseSession.objects.create(
            therapist=self.other,
            customer=self.other_customer,
            date=date.today(),
        )
        resp = self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "cancelled"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
