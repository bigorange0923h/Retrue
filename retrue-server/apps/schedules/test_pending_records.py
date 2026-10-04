"""跨日待回填课程接口的归属、范围和分页回归。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.customers.models import Customer
from apps.schedules.models import CourseSession, CourseSessionStatus
from apps.training.models import TrainingRecord


class PendingTrainingCoursesApiTests(APITestCase):
    """待回填覆盖全部历史遗漏，取消/完成/有记录/未来排课均不混入。"""

    def setUp(self):
        """准备两个账号和当日、很久以前的待回填课程。"""
        self.therapist = get_user_model().objects.create_user(username="pending_owner")
        self.other = get_user_model().objects.create_user(username="pending_other")
        self.customer = Customer.objects.create(therapist=self.therapist, name="测试客户")
        self.other_customer = Customer.objects.create(therapist=self.other, name="其他客户")
        self.client.force_login(self.therapist)
        self.today = timezone.localdate()
        self.old = self._session(self.today - timedelta(days=800))
        self.current = self._session(self.today)

    def _session(self, session_date, **kwargs):
        """创建本人排课用于范围断言。"""
        return CourseSession.objects.create(
            therapist=self.therapist, customer=self.customer, date=session_date, **kwargs,
        )

    def test_all_history_isolated_and_excludes_ineligible_courses(self):
        """不猜测最近天数；只返回本人截止今日且无正式记录的待上课课程。"""
        self._session(self.today + timedelta(days=1))
        self._session(self.today, status=CourseSessionStatus.CANCELLED)
        self._session(self.today, status=CourseSessionStatus.ABSENT)
        self._session(self.today, status=CourseSessionStatus.COMPLETED)
        recorded = self._session(self.today)
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer,
            course_session=recorded, training_date=self.today,
        )
        CourseSession.objects.create(
            therapist=self.other, customer=self.other_customer, date=self.today,
        )
        response = self.client.get(reverse("pending-training-courses"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["total"], 2)
        self.assertEqual(
            [item["id"] for item in response.data["data"]["items"]],
            [self.old.id, self.current.id],
        )

    def test_pagination_preserves_total_and_validates_limits(self):
        """前端可以看到总数并逐页获取，不将首页展示条数当全部待办。"""
        response = self.client.get(reverse("pending-training-courses"), {"page": 2, "page_size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["total"], 2)
        self.assertEqual(response.data["data"]["items"][0]["id"], self.current.id)
        for params in ({"page": 0}, {"page_size": 201}, {"page": "x"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(reverse("pending-training-courses"), params).status_code, 400)
