"""rehab：康复计划与阶段接口单元测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer
from apps.rehab.models import (
    RehabPlan,
    RehabPlanTemplate,
    RehabPlanTemplateCourse,
    RehabStage,
)
from apps.schedules.models import CourseType, RehabPlanCourse

User = get_user_model()


class RehabApiTests(APITestCase):
    """康复计划与阶段接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与计划。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.plan = RehabPlan.objects.create(
            therapist=self.therapist, customer=self.customer, start_date="2026-08-01"
        )

    def test_create_plan(self) -> None:
        """结束旧周期后可创建新的康复周期。"""
        self.plan.status = "closed"
        self.plan.save()
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {
                "customer": self.customer.id,
                "start_date": "2026-09-01",
                "end_date": "2026-11-01",
                "name": "膝关节康复",
                "goals": "恢复无痛下蹲",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["name"], "膝关节康复")
        self.assertEqual(resp.data["data"]["goals"], "恢复无痛下蹲")

    def test_rejects_second_active_plan(self) -> None:
        """同一客户不能同时创建两个进行中的周期。"""
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {"customer": self.customer.id, "start_date": "2026-09-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_plan_dates_and_goals(self) -> None:
        """康复师可更新周期日期和总体目标。"""
        resp = self.client.put(
            reverse("rehab-plan-detail", args=[self.plan.id]),
            {"end_date": "2026-10-31", "goals": "恢复跑跳能力"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["end_date"], "2026-10-31")
        self.assertEqual(resp.data["data"]["goals"], "恢复跑跳能力")

    def test_cannot_create_plan_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建计划。"""
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {"customer": self.other_customer.id, "start_date": "2026-08-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_set_stage_closes_previous(self) -> None:
        """设置新阶段自动关闭上一阶段。"""
        RehabStage.objects.create(
            plan=self.plan, stage_type="acute", start_date="2026-08-01"
        )
        resp = self.client.post(
            reverse("rehab-stage"),
            {"customer": self.customer.id, "stage_type": "strength", "start_date": "2026-08-26"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # 上一阶段应已关闭
        old = RehabStage.objects.get(stage_type="acute", plan=self.plan)
        self.assertIsNotNone(old.end_date)
        # 新阶段有效
        current = RehabStage.objects.get(stage_type="strength", plan=self.plan)
        self.assertIsNone(current.end_date)
        self.assertEqual(current.plan_id, self.plan.id)

    def test_get_current_stage(self) -> None:
        """查询当前阶段。"""
        RehabStage.objects.create(
            plan=self.plan, stage_type="recovery", start_date="2026-08-10"
        )
        resp = self.client.get(reverse("rehab-stage"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["stage_type"], "recovery")

    def test_stage_requires_active_plan(self) -> None:
        """没有进行中周期时不能设置游离阶段。"""
        self.plan.status = "closed"
        self.plan.end_date = "2026-08-20"
        self.plan.save()
        resp = self.client.post(
            reverse("rehab-stage"),
            {"customer": self.customer.id, "stage_type": "strength", "start_date": "2026-08-10"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_database_rejects_duplicate_active_plan(self) -> None:
        """数据库约束也阻止并发场景下出现两个进行中周期。"""
        with self.assertRaises(IntegrityError), transaction.atomic():
            RehabPlan.objects.create(
                therapist=self.therapist,
                customer=self.customer,
                start_date="2026-09-01",
            )

    def test_list_plans_isolated(self) -> None:
        """只能看到本人客户的计划。"""
        RehabPlan.objects.create(therapist=self.other, customer=self.other_customer, start_date="2026-08-01")
        resp = self.client.get(reverse("rehab-plan-list"), {"customer_id": self.customer.id})
        self.assertEqual(len(resp.data["data"]), 1)


class RehabPlanTemplateApiTests(APITestCase):
    """康复周期模板和客户周期复制接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户和单课程模板。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.course_type = CourseType.objects.create(
            therapist=self.therapist,
            name="活动度恢复",
            default_duration=60,
            default_session_cost="1.0",
            default_goals="恢复关节活动度",
        )

    def _create_template(self, planned_count: int = 8) -> RehabPlanTemplate:
        """创建一条带课程组成的测试周期模板。"""
        template = RehabPlanTemplate.objects.create(
            therapist=self.therapist,
            name="膝关节术后恢复",
            suggested_duration_weeks=12,
            goals="恢复无痛行走",
        )
        RehabPlanTemplateCourse.objects.create(
            template=template,
            course_type=self.course_type,
            planned_count=planned_count,
            duration=60,
            session_cost="1.0",
            goals="恢复活动度",
        )
        return template

    def test_create_template_with_nested_courses(self) -> None:
        """康复师可维护包含多种课程及默认次数的周期模板。"""
        resp = self.client.post(
            reverse("rehab-plan-template-list"),
            {
                "name": "膝关节术后恢复",
                "description": "适用于术后恢复",
                "suggested_duration_weeks": 12,
                "goals": "恢复无痛行走",
                "courses": [
                    {
                        "course_type": self.course_type.id,
                        "planned_count": 8,
                        "duration": 60,
                        "session_cost": "1.0",
                        "goals": "恢复活动度",
                        "sort_order": 0,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["courses"][0]["planned_count"], 8)
        self.assertEqual(resp.data["data"]["total_planned_count"], 8)

    def test_list_templates_isolates_therapist(self) -> None:
        """周期模板按康复师隔离。"""
        self._create_template()
        RehabPlanTemplate.objects.create(
            therapist=self.other,
            name="他人模板",
            is_active=False,
        )
        resp = self.client.get(reverse("rehab-plan-template-list"))
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["name"], "膝关节术后恢复")

    def test_create_customer_plan_copies_template_snapshot(self) -> None:
        """选择模板创建客户周期时复制课程，不与模板课程持续绑定。"""
        template = self._create_template(planned_count=8)
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {
                "customer": self.customer.id,
                "source_template": template.id,
                "name": "张三术后周期",
                "start_date": "2026-09-01",
                "end_date": "2026-11-23",
                "goals": "恢复跑跳",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        plan = RehabPlan.objects.get(id=resp.data["data"]["id"])
        plan_course = RehabPlanCourse.objects.get(rehab_plan=plan)
        self.assertEqual(plan.source_template_id, template.id)
        self.assertEqual(plan_course.planned_count, 8)
        self.assertEqual(plan_course.goals, "恢复活动度")

        template_course = template.courses.get()
        template_course.planned_count = 4
        template_course.save(update_fields=["planned_count"])
        plan_course.refresh_from_db()
        self.assertEqual(plan_course.planned_count, 8)

    def test_create_customer_plan_accepts_preview_overrides(self) -> None:
        """应用模板前可按客户情况调整课程次数和快照字段。"""
        template = self._create_template(planned_count=8)
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {
                "customer": self.customer.id,
                "source_template": template.id,
                "name": "个性化周期",
                "start_date": "2026-09-01",
                "courses": [
                    {
                        "course_type": self.course_type.id,
                        "planned_count": 5,
                        "duration": 45,
                        "session_cost": "0.5",
                        "goals": "按本次评估调整",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        plan_course = RehabPlanCourse.objects.get(rehab_plan_id=resp.data["data"]["id"])
        self.assertEqual(plan_course.planned_count, 5)
        self.assertEqual(plan_course.duration, 45)
        self.assertEqual(plan_course.session_cost, 0.5)

    def test_cannot_use_other_or_inactive_template(self) -> None:
        """不能用他人或停用的模板创建客户周期。"""
        other_template = RehabPlanTemplate.objects.create(
            therapist=self.other,
            name="他人模板",
            is_active=True,
        )
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {
                "customer": self.customer.id,
                "source_template": other_template.id,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        inactive = self._create_template()
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        resp = self.client.post(
            reverse("rehab-plan-list"),
            {
                "customer": self.customer.id,
                "source_template": inactive.id,
                "start_date": "2026-09-01",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
