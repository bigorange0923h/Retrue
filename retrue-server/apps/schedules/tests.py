"""schedules：课程/今日日程接口单元测试。

覆盖今日课程查询、课程创建与数据隔离。
"""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.courses.models import CoursePackage
from apps.customers.models import Customer
from apps.schedules.models import (
    CourseSession,
    CourseSessionStatus,
    CourseType,
    CustomerCourse,
    CustomerCourseStatus,
)

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

    def test_create_course_with_session_topic(self) -> None:
        """本节训练主题随课程保存，用于区分康复周期内的不同课程。"""
        resp = self.client.post(
            reverse("course-create"),
            {"customer": self.customer.id, "date": "2026-08-27", "session_topic": "力量重建训练"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["session_topic"], "力量重建训练")

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


class CourseTypeApiTests(APITestCase):
    """课程类型接口测试。"""

    def setUp(self) -> None:
        """准备康复师账号。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

    def test_create_course_type(self) -> None:
        """康复师可创建课程类型。"""
        resp = self.client.post(
            reverse("course-type-list"),
            {"name": "力量重建", "description": "下肢力量重建训练"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["name"], "力量重建")
        self.assertTrue(resp.data["data"]["is_active"])

    def test_list_isolates_therapist(self) -> None:
        """只能看到本人课程类型。"""
        CourseType.objects.create(therapist=self.other, name="他人类型")
        CourseType.objects.create(therapist=self.therapist, name="我的类型")
        resp = self.client.get(reverse("course-type-list"))
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["name"], "我的类型")

    def test_disable_referenced_type_rejected(self) -> None:
        """被客户疗程引用的类型不能停用。"""
        customer = Customer.objects.create(therapist=self.therapist, name="张三")
        course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        CustomerCourse.objects.create(
            therapist=self.therapist,
            customer=customer,
            course_type=course_type,
        )
        resp = self.client.put(
            reverse("course-type-detail", args=[course_type.id]),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_unreferenced_type_ok(self) -> None:
        """未被引用的类型可正常更新与停用。"""
        course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        resp = self.client.put(
            reverse("course-type-detail", args=[course_type.id]),
            {"name": "力量重建二期", "is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["name"], "力量重建二期")
        self.assertFalse(resp.data["data"]["is_active"])


class CustomerCourseApiTests(APITestCase):
    """客户疗程接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与课程类型。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.course_type = CourseType.objects.create(
            therapist=self.therapist, name="力量重建", default_session_cost="1.0", default_duration=60
        )

    def test_create_customer_course_snapshots_defaults(self) -> None:
        """创建疗程时快照课程类型的默认时长与消耗量。"""
        resp = self.client.post(
            reverse("customer-course-list"),
            {"customer": self.customer.id, "course_type": self.course_type.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["session_cost"], "1.0")
        self.assertEqual(data["duration"], 60)
        self.assertEqual(data["status"], "pending")

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建疗程。"""
        other_customer = Customer.objects.create(therapist=self.other, name="李四")
        resp = self.client.post(
            reverse("customer-course-list"),
            {"customer": other_customer.id, "course_type": self.course_type.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_use_other_therapist_course_type(self) -> None:
        """不能使用其他康复师的课程类型。"""
        other_type = CourseType.objects.create(therapist=self.other, name="他人类型")
        resp = self.client.post(
            reverse("customer-course-list"),
            {"customer": self.customer.id, "course_type": other_type.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_session_cost_must_be_multiple_of_half(self) -> None:
        """课时消耗量必须为 0.5 的倍数。"""
        resp = self.client.post(
            reverse("customer-course-list"),
            {
                "customer": self.customer.id,
                "course_type": self.course_type.id,
                "session_cost": "0.7",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class CourseSessionCourseAssociationTests(APITestCase):
    """课程排期关联客户疗程测试。"""

    def setUp(self) -> None:
        """准备康复师、客户、课程类型与疗程。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        self.active_course = CustomerCourse.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            course_type=self.course_type,
            status=CustomerCourseStatus.ACTIVE,
        )

    def test_schedule_with_active_customer_course(self) -> None:
        """可为进行中的疗程排课。"""
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": self.customer.id,
                "customer_course": self.active_course.id,
                "session_topic": "力量重建训练",
                "session_count": "0.5",
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["session_count"], "0.5")
        self.assertEqual(resp.data["data"]["customer_course"], self.active_course.id)

    def test_schedule_rejects_non_active_course(self) -> None:
        """不能为非进行中的疗程排课。"""
        pending_course = CustomerCourse.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            course_type=self.course_type,
            status=CustomerCourseStatus.PENDING,
        )
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": self.customer.id,
                "customer_course": pending_course.id,
                "session_topic": "力量重建训练",
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_schedule_rejects_course_customer_mismatch(self) -> None:
        """排期客户与疗程客户不一致时拒绝。"""
        other_customer = Customer.objects.create(therapist=self.therapist, name="王五")
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": other_customer.id,
                "customer_course": self.active_course.id,
                "session_topic": "力量重建训练",
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SessionConsumptionTests(APITestCase):
    """课程完成自动扣课时测试。"""

    def setUp(self) -> None:
        """准备康复师、客户、课程类型、课时包与疗程。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        self.package = CoursePackage.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            name="30 次卡",
            total_sessions="30",
        )
        self.course = CustomerCourse.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            course_type=self.course_type,
            package=self.package,
            status=CustomerCourseStatus.ACTIVE,
        )

    def test_complete_session_deducts_full_session(self) -> None:
        """课程完成时按课时单位扣减（全课 1.0）。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            customer_course=self.course,
            session_count="1.0",
            date=date.today(),
            status=CourseSessionStatus.SCHEDULED,
        )
        resp = self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 1)
        self.assertEqual(self.package.remaining_sessions, 29)

    def test_complete_session_deducts_half_session(self) -> None:
        """课程完成时按半课 0.5 扣减。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            customer_course=self.course,
            session_count="0.5",
            date=date.today(),
            status=CourseSessionStatus.SCHEDULED,
        )
        self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "completed"},
            format="json",
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 0.5)

    def test_consumption_is_idempotent(self) -> None:
        """重复完成同一课程不会重复扣课时。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            customer_course=self.course,
            session_count="1.0",
            date=date.today(),
            status=CourseSessionStatus.COMPLETED,
            session_consumed=True,
        )
        # 已是完成状态且已扣减：再次更新不会重复扣
        self.client.put(
            reverse("course-detail", args=[session.id]),
            {"note": "补充备注"},
            format="json",
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 0)

    def test_cancel_session_does_not_deduct(self) -> None:
        """取消课程不扣课时。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            customer_course=self.course,
            session_count="1.0",
            date=date.today(),
            status=CourseSessionStatus.SCHEDULED,
        )
        self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "cancelled"},
            format="json",
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 0)

    def test_session_without_package_not_deducted(self) -> None:
        """疗程未关联课时包时，课程完成不扣课时。"""
        no_pkg_course = CustomerCourse.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            course_type=self.course_type,
            status=CustomerCourseStatus.ACTIVE,
        )
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            customer_course=no_pkg_course,
            session_count="1.0",
            date=date.today(),
            status=CourseSessionStatus.SCHEDULED,
        )
        self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "completed"},
            format="json",
        )
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 0)
