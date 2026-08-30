"""schedules：课程/今日日程接口单元测试。

覆盖今日课程查询、课程创建与数据隔离。
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.courses.models import CoursePackage
from apps.customers.models import Customer
from apps.rehab.models import RehabPlan
from apps.schedules.models import (
    CourseSession,
    CourseSessionStatus,
    CourseType,
    PlanCourseStatus,
    RehabPlanCourse,
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
            {
                "customer": self.customer.id,
                "date": "2026-08-27",
                "start_time": "14:00:00",
                "end_time": "15:00:00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["customer_name"], "张三")

    def test_create_rejects_incomplete_or_reversed_time(self) -> None:
        """排课时间必须成对填写且结束时间晚于开始时间。"""
        incomplete = self.client.post(
            reverse("course-create"),
            {"customer": self.customer.id, "date": "2026-08-27", "start_time": "14:00:00"},
            format="json",
        )
        reversed_time = self.client.post(
            reverse("course-create"),
            {
                "customer": self.customer.id,
                "date": "2026-08-27",
                "start_time": "15:00:00",
                "end_time": "14:00:00",
            },
            format="json",
        )
        self.assertEqual(incomplete.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(reversed_time.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_cannot_start_completed(self) -> None:
        """新建排课不能绕过正式训练记录直接标记完成。"""
        resp = self.client.post(
            reverse("course-create"),
            {"customer": self.customer.id, "date": "2026-08-27", "status": "completed"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_disable_referenced_type_preserves_existing_plan_course(self) -> None:
        """课程模板停用后不影响已经建立的周期课程。"""
        customer = Customer.objects.create(therapist=self.therapist, name="张三")
        plan = RehabPlan.objects.create(
            therapist=self.therapist, customer=customer, start_date=date.today()
        )
        course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        plan_course = RehabPlanCourse.objects.create(
            rehab_plan=plan,
            course_type=course_type,
        )
        resp = self.client.put(
            reverse("course-type-detail", args=[course_type.id]),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        plan_course.refresh_from_db()
        self.assertEqual(plan_course.course_type_id, course_type.id)

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


class RehabPlanCourseApiTests(APITestCase):
    """康复周期课程接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户、康复周期与课程模板。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.plan = RehabPlan.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            name="术后恢复周期",
            start_date=date.today(),
        )
        self.course_type = CourseType.objects.create(
            therapist=self.therapist, name="力量重建", default_session_cost="1.0", default_duration=60
        )

    def test_create_plan_course_snapshots_defaults(self) -> None:
        """添加周期课程时快照模板默认时长与消耗量。"""
        resp = self.client.post(
            reverse("rehab-plan-course-list"),
            {"rehab_plan": self.plan.id, "course_type": self.course_type.id, "planned_count": 8},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["session_cost"], Decimal("1.0"))
        self.assertEqual(data["duration"], 60)
        self.assertEqual(data["planned_count"], 8)
        self.assertEqual(data["status"], "active")

    def test_cannot_create_for_other_plan(self) -> None:
        """不能为其他康复师的周期添加课程。"""
        other_customer = Customer.objects.create(therapist=self.other, name="李四")
        other_plan = RehabPlan.objects.create(
            therapist=self.other, customer=other_customer, start_date=date.today()
        )
        resp = self.client.post(
            reverse("rehab-plan-course-list"),
            {"rehab_plan": other_plan.id, "course_type": self.course_type.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_use_other_therapist_course_type(self) -> None:
        """不能使用其他康复师的课程类型。"""
        other_type = CourseType.objects.create(therapist=self.other, name="他人类型")
        resp = self.client.post(
            reverse("rehab-plan-course-list"),
            {"rehab_plan": self.plan.id, "course_type": other_type.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_session_cost_must_be_multiple_of_half(self) -> None:
        """课时消耗量必须为 0.5 的倍数。"""
        resp = self.client.post(
            reverse("rehab-plan-course-list"),
            {
                "rehab_plan": self.plan.id,
                "course_type": self.course_type.id,
                "session_cost": "0.7",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_adjust_plan_course_count_keeps_history(self) -> None:
        """康复师可按恢复情况增减次数并保留调整记录。"""
        plan_course = RehabPlanCourse.objects.create(
            rehab_plan=self.plan, course_type=self.course_type, planned_count=8
        )
        resp = self.client.post(
            reverse("rehab-plan-course-adjust", args=[plan_course.id]),
            {"delta_count": 2, "reason": "复评后增加力量训练"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["planned_count"], 10)
        self.assertEqual(resp.data["data"]["adjustments"][0]["before_count"], 8)
        self.assertEqual(resp.data["data"]["adjustments"][0]["after_count"], 10)

    def test_direct_count_change_requires_adjustment_endpoint(self) -> None:
        """已有周期课程必须通过带原因的调整接口修改次数。"""
        plan_course = RehabPlanCourse.objects.create(
            rehab_plan=self.plan, course_type=self.course_type, planned_count=8
        )
        resp = self.client.put(
            reverse("rehab-plan-course-detail", args=[plan_course.id]),
            {"planned_count": 6},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        plan_course.refresh_from_db()
        self.assertEqual(plan_course.planned_count, 8)


class CourseSessionCourseAssociationTests(APITestCase):
    """课程排期关联周期课程测试。"""

    def setUp(self) -> None:
        """准备康复师、客户、周期与课程。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.plan = RehabPlan.objects.create(
            therapist=self.therapist, customer=self.customer, start_date=date.today()
        )
        self.course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        self.active_course = RehabPlanCourse.objects.create(
            rehab_plan=self.plan,
            course_type=self.course_type,
            status=PlanCourseStatus.ACTIVE,
        )

    def test_schedule_with_active_plan_course(self) -> None:
        """可为进行中的周期课程排课。"""
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": self.customer.id,
                "plan_course": self.active_course.id,
                "session_topic": "力量重建训练",
                "session_count": "0.5",
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["session_count"], Decimal("0.5"))
        self.assertEqual(resp.data["data"]["plan_course"], self.active_course.id)

    def test_schedule_rejects_non_active_course(self) -> None:
        """不能为暂停的周期课程排课。"""
        paused_course = RehabPlanCourse.objects.create(
            rehab_plan=self.plan,
            course_type=self.course_type,
            status=PlanCourseStatus.PAUSED,
        )
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": self.customer.id,
                "plan_course": paused_course.id,
                "session_topic": "力量重建训练",
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_schedule_rejects_course_customer_mismatch(self) -> None:
        """排期客户与康复周期客户不一致时拒绝。"""
        other_customer = Customer.objects.create(therapist=self.therapist, name="王五")
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": other_customer.id,
                "plan_course": self.active_course.id,
                "session_topic": "力量重建训练",
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_schedule_rejects_closed_rehab_plan(self) -> None:
        """周期结束后，即使子课程仍为进行中也不能继续排课。"""
        self.plan.status = "closed"
        self.plan.end_date = date.today()
        self.plan.save()
        resp = self.client.post(
            reverse("course-create"),
            {
                "customer": self.customer.id,
                "plan_course": self.active_course.id,
                "date": "2026-08-27",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SessionCompletionTests(APITestCase):
    """训练记录确认后完成课程并扣课时测试。"""

    def setUp(self) -> None:
        """准备康复师、客户、周期课程与课时包。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.course_type = CourseType.objects.create(therapist=self.therapist, name="力量重建")
        self.plan = RehabPlan.objects.create(
            therapist=self.therapist, customer=self.customer, start_date=date.today()
        )
        self.package = CoursePackage.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            name="30 次卡",
            total_sessions="30",
        )
        self.course = RehabPlanCourse.objects.create(
            rehab_plan=self.plan,
            course_type=self.course_type,
            package=self.package,
            planned_count=2,
            status=PlanCourseStatus.ACTIVE,
        )

    def test_direct_complete_without_record_rejected(self) -> None:
        """不能绕过训练记录直接完成课程。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=self.course,
            session_count="1.0",
            date=date.today(),
        )
        resp = self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 0)

    def test_confirm_record_completes_and_deducts_half_session(self) -> None:
        """确认训练记录后按排课课时完成并扣减。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=self.course,
            session_count="0.5",
            date=date.today(),
        )
        resp = self.client.post(
            reverse("training-list"),
            {
                "customer": self.customer.id,
                "course_session": session.id,
                "training_date": date.today().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.package.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(self.package.used_sessions, Decimal("0.5"))
        self.assertEqual(session.status, CourseSessionStatus.COMPLETED)
        self.assertTrue(session.session_consumed)
        self.assertNotIn("confirmed", resp.data["data"])
        adjustment = self.package.adjustments.get()
        self.assertEqual(adjustment.adjustment_type, "consumption")
        self.assertEqual(adjustment.course_session_id, session.id)

    def test_second_record_for_same_session_rejected(self) -> None:
        """同一排课不能重复创建正式记录并重复扣课。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=self.course,
            session_count="1.0",
            date=date.today(),
        )
        self.client.put(
            reverse("course-detail", args=[session.id]), {"note": "准备训练"}, format="json"
        )
        first = self.client.post(
            reverse("training-list"),
            {"customer": self.customer.id, "course_session": session.id, "training_date": date.today().isoformat()},
            format="json",
        )
        second = self.client.post(
            reverse("training-list"),
            {"customer": self.customer.id, "course_session": session.id, "training_date": date.today().isoformat()},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.package.refresh_from_db()
        self.assertEqual(self.package.used_sessions, 1)

    def test_cancel_session_does_not_deduct(self) -> None:
        """取消课程不扣课时。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=self.course,
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

    def test_insufficient_balance_rolls_back_record_and_completion(self) -> None:
        """课时不足时训练记录、排课完成与扣课全部回滚。"""
        self.package.total_sessions = Decimal("0.5")
        self.package.save(update_fields=["total_sessions"])
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=self.course,
            session_count="1.0",
            date=date.today(),
        )
        resp = self.client.post(
            reverse("training-list"),
            {
                "customer": self.customer.id,
                "course_session": session.id,
                "training_date": date.today().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(session.training_records.exists())
        session.refresh_from_db()
        self.package.refresh_from_db()
        self.assertEqual(session.status, CourseSessionStatus.SCHEDULED)
        self.assertFalse(session.session_consumed)
        self.assertEqual(self.package.used_sessions, 0)

    def test_reaching_planned_count_completes_plan_course(self) -> None:
        """确认记录达到计划次数后，周期课程自动完成。"""
        self.course.planned_count = 1
        self.course.save(update_fields=["planned_count"])
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=self.course,
            session_count="1.0",
            date=date.today(),
        )
        resp = self.client.post(
            reverse("training-list"),
            {
                "customer": self.customer.id,
                "course_session": session.id,
                "training_date": date.today().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.course.refresh_from_db()
        self.assertEqual(self.course.status, PlanCourseStatus.COMPLETED)
