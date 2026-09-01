"""ai：AI 草稿接口单元测试。

覆盖草稿解析、确认创建正式记录、取消、状态流转与数据隔离。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft, AiDraftStatus
from apps.assistant_tasks.models import (
    AssistantRunStatus,
    AssistantTask,
    AssistantTaskStatus,
    ToolExecutionStatus,
)
from apps.assessments.models import Assessment, AssessmentMetric
from apps.customers.models import Customer
from apps.rehab.models import RehabPlan
from apps.schedules.models import (
    CourseSession,
    CourseSessionStatus,
    CourseType,
    RehabPlanCourse,
)
from apps.training.models import TrainingRecord

User = get_user_model()


class AiDraftApiTests(APITestCase):
    """AI 草稿接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与草稿。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

        self.draft = AiDraft.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            input_text="做了臀桥 3 组 12 次，左膝疼痛 2 分",
            ai_result={"exercises": [{"exercise_name": "臀桥", "sets": 3, "reps": 12}]},
            status=AiDraftStatus.PENDING,
        )

    def test_parse_creates_pending_draft(self) -> None:
        """解析文本生成待确认草稿。"""
        resp = self.client.post(
            reverse("ai-parse"),
            {"input_text": "今天做了臀桥 3 组 12 次，靠墙静蹲 30 秒", "customer_id": self.customer.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["status"], "pending")
        self.assertEqual(len(data["ai_result"]["exercises"]), 2)

    def test_parse_empty_text_returns_400(self) -> None:
        """空文本被参数校验拒绝，返回 400。"""
        resp = self.client.post(reverse("ai-parse"), {"input_text": ""}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_creates_training_record(self) -> None:
        """确认草稿创建正式训练记录。"""
        confirmed = {
            "training_date": "2026-08-26",
            "customer_feedback": "左膝疼痛 NRS 2",
            "exercises": [{"exercise_name": "臀桥", "sets": 3, "reps": 12}],
        }
        resp = self.client.post(
            reverse("ai-confirm", args=[self.draft.id]),
            {"customer_id": self.customer.id, "confirmed": confirmed},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "confirmed")
        # 正式记录已创建
        self.assertEqual(TrainingRecord.objects.filter(customer=self.customer).count(), 1)
        record = TrainingRecord.objects.get(customer=self.customer)
        self.assertEqual(record.customer_feedback, "左膝疼痛 NRS 2")
        self.assertEqual(record.exercises.count(), 1)

    def test_parse_task_requires_owner_type_and_customer_context(self) -> None:
        """统一任务必须属于当前康复师、类型正确且客户上下文一致。"""
        task = AssistantTask.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            task_type="training_record",
        )
        response = self.client.post(
            reverse("ai-parse"),
            {
                "input_text": "今天做了臀桥",
                "assistant_task_id": task.id,
                "customer_id": self.other.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AiDraft.objects.filter(assistant_task=task).count(), 0)

        task.task_type = "assessment"
        task.save(update_fields=["task_type"])
        response = self.client.post(
            reverse("ai-parse"),
            {"input_text": "今天做了臀桥", "assistant_task_id": task.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_parse_task_updates_status_and_saves_redacted_run(self) -> None:
        """训练补记解析会推进任务，并保存脱敏执行与草稿工具记录。"""
        task = AssistantTask.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            task_type="training_record",
        )
        response = self.client.post(
            reverse("ai-parse"),
            {
                "input_text": "今天做了臀桥 3 组 12 次",
                "assistant_task_id": task.id,
                "customer_id": self.customer.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, AssistantTaskStatus.WAITING_CONFIRMATION)
        self.assertEqual(task.current_step, "waiting_confirmation")
        draft = AiDraft.objects.get(id=response.data["data"]["id"])
        self.assertEqual(draft.assistant_task_id, task.id)
        self.assertEqual(task.draft_resource_type, "ai_draft")
        self.assertEqual(task.draft_resource_id, str(draft.id))

        run = task.runs.get()
        self.assertEqual(run.status, AssistantRunStatus.SUCCEEDED)
        self.assertEqual(run.input_summary["input_length"], len("今天做了臀桥 3 组 12 次"))
        self.assertNotIn("input_text", run.input_summary)
        tool = run.tool_executions.get()
        self.assertEqual(tool.tool_name, "create_training_draft")
        self.assertEqual(tool.status, ToolExecutionStatus.SUCCEEDED)
        self.assertTrue(tool.requires_confirmation)

    def test_confirm_idempotency_returns_same_record_and_completes_task(self) -> None:
        """重复确认只返回首次正式记录，并完成统一任务。"""
        task = AssistantTask.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            task_type="training_record",
        )
        draft = AiDraft.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assistant_task=task,
            input_text="训练补记",
            status=AiDraftStatus.PENDING,
        )
        confirmed = {
            "training_date": "2026-08-26",
            "customer_feedback": "左膝疼痛 NRS 2",
            "exercises": [],
        }
        payload = {
            "customer_id": self.customer.id,
            "confirmed": confirmed,
            "idempotency_key": "confirm-key-1",
        }
        first = self.client.post(
            reverse("ai-confirm", args=[draft.id]),
            payload,
            format="json",
        )
        second = self.client.post(
            reverse("ai-confirm", args=[draft.id]),
            payload,
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["data"]["training_record"], second.data["data"]["training_record"])
        self.assertEqual(TrainingRecord.objects.filter(customer=self.customer).count(), 1)

        draft.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(draft.confirmation_key, "confirm-key-1")
        self.assertEqual(draft.training_record_id, first.data["data"]["training_record"])
        self.assertEqual(task.status, AssistantTaskStatus.COMPLETED)
        self.assertEqual(task.result_resource_type, "training_record")
        self.assertEqual(task.result_resource_id, str(draft.training_record_id))
        confirm_tool = task.runs.order_by("-id").first().tool_executions.get()
        self.assertEqual(confirm_tool.tool_name, "confirm_training_record")
        self.assertEqual(confirm_tool.status, ToolExecutionStatus.SUCCEEDED)
        self.assertEqual(confirm_tool.confirmed_by_id, self.therapist.id)

    def test_confirm_binds_customer_to_task_that_started_without_one(self) -> None:
        """确认时选择客户应补齐原本无客户的任务上下文。"""
        task = AssistantTask.objects.create(
            therapist=self.therapist,
            task_type="training_record",
        )
        draft = AiDraft.objects.create(
            therapist=self.therapist,
            assistant_task=task,
            input_text="待识别客户的训练补记",
            status=AiDraftStatus.PENDING,
        )
        response = self.client.post(
            reverse("ai-confirm", args=[draft.id]),
            {
                "customer_id": self.customer.id,
                "confirmed": {"training_date": "2026-08-26", "exercises": []},
                "idempotency_key": "bind-customer-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.customer_id, self.customer.id)
        self.assertEqual(task.status, AssistantTaskStatus.COMPLETED)

    def test_confirm_binds_course_context_to_task_that_started_without_one(self) -> None:
        """确认时选择排课应补齐原本无课程资源的任务上下文。"""
        plan = RehabPlan.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            start_date="2026-08-01",
        )
        course_type = CourseType.objects.create(therapist=self.therapist, name="活动度恢复")
        plan_course = RehabPlanCourse.objects.create(
            rehab_plan=plan,
            course_type=course_type,
            planned_count=1,
        )
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=plan_course,
            date="2026-08-26",
        )
        task = AssistantTask.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            task_type="training_record",
        )
        draft = AiDraft.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assistant_task=task,
            input_text="待确认课程训练补记",
            status=AiDraftStatus.PENDING,
        )
        response = self.client.post(
            reverse("ai-confirm", args=[draft.id]),
            {
                "customer_id": self.customer.id,
                "course_session_id": session.id,
                "confirmed": {"training_date": "2026-08-26", "exercises": []},
                "idempotency_key": "bind-course-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.context_resource_type, "course_session")
        self.assertEqual(task.context_resource_id, str(session.id))

    def test_cancel_task_draft_cancels_unfinished_task(self) -> None:
        """取消补记草稿时同步取消尚未结束的统一任务。"""
        task = AssistantTask.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            task_type="training_record",
            status=AssistantTaskStatus.WAITING_CONFIRMATION,
        )
        draft = AiDraft.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assistant_task=task,
            input_text="训练补记",
            status=AiDraftStatus.PENDING,
        )
        response = self.client.post(reverse("ai-cancel", args=[draft.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, AssistantTaskStatus.CANCELLED)
        self.assertEqual(task.current_step, "cancelled")

    def test_confirm_linked_session_closes_course(self) -> None:
        """确认排课来源的 AI 草稿时同步完成排课。"""
        plan = RehabPlan.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            start_date="2026-08-01",
        )
        course_type = CourseType.objects.create(
            therapist=self.therapist,
            name="力量重建",
        )
        plan_course = RehabPlanCourse.objects.create(
            rehab_plan=plan,
            course_type=course_type,
            planned_count=1,
        )
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            plan_course=plan_course,
            date="2026-08-26",
        )
        resp = self.client.post(
            reverse("ai-confirm", args=[self.draft.id]),
            {
                "customer_id": self.customer.id,
                "course_session_id": session.id,
                "confirmed": {"training_date": "2026-08-26", "exercises": []},
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        plan_course.refresh_from_db()
        record = TrainingRecord.objects.get(course_session=session)
        self.assertEqual(record.customer_id, self.customer.id)
        self.assertEqual(session.status, CourseSessionStatus.COMPLETED)
        self.assertEqual(plan_course.status, "completed")
        cancel_resp = self.client.put(
            reverse("course-detail", args=[session.id]),
            {"status": "cancelled"},
            format="json",
        )
        self.assertEqual(cancel_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_cannot_confirm_other_therapist_draft(self) -> None:
        """不能确认其他康复师的草稿。"""
        other_draft = AiDraft.objects.create(
            therapist=self.other,
            input_text="x",
            status=AiDraftStatus.PENDING,
        )
        resp = self.client.post(
            reverse("ai-confirm", args=[other_draft.id]),
            {"customer_id": self.customer.id, "confirmed": {"training_date": "2026-08-26"}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_draft(self) -> None:
        """取消草稿不创建正式记录。"""
        resp = self.client.post(reverse("ai-cancel", args=[self.draft.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["status"], "cancelled")
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_customer_candidates(self) -> None:
        """按姓名提示返回客户候选。"""
        resp = self.client.get(reverse("ai-candidates"), {"name": "张"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in resp.data["data"]]
        self.assertIn("张三", names)
        # 候选不返回完整手机号
        self.assertIn("phone_masked", resp.data["data"][0])

    def test_prepare_lesson_returns_summary_and_suggestions(self) -> None:
        """备课助手返回客户汇总与 AI 建议。"""
        from apps.training.models import TrainingRecord

        TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 6",
            next_plan="增加单腿稳定训练",
        )
        resp = self.client.get(reverse("ai-prepare-lesson"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIn("customer_summary", data)
        self.assertIn("ai_suggestions", data)
        # 疼痛 NRS 6 应触发风险提醒
        self.assertTrue(len(data["ai_suggestions"]["risk_reminders"]) >= 1)
        self.assertEqual(data["customer_summary"]["next_plan"], "增加单腿稳定训练")

    def test_prepare_lesson_requires_customer_id(self) -> None:
        """备课缺少 customer_id 返回 400。"""
        resp = self.client.get(reverse("ai-prepare-lesson"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RiskAlertApiTests(APITestCase):
    """风险提醒接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与训练记录。"""
        from apps.training.models import TrainingRecord

        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-25",
            customer_feedback="左膝疼痛 NRS 7",
        )
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 6",
        )

    def test_detect_risk_high_level(self) -> None:
        """连续 NRS>=6 触发高风险提醒。"""
        resp = self.client.post(
            reverse("ai-risk-detect"),
            {"customer_id": self.customer.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIsNotNone(data)
        self.assertEqual(data["risk_level"], "high")

    def test_risk_list_and_update(self) -> None:
        """风险列表与确认更新。"""
        from apps.ai.models import RiskAlert

        alert = RiskAlert.objects.create(
            therapist=self.therapist, customer=self.customer, risk_level="high", suggested_action="pause",
        )
        resp = self.client.get(reverse("ai-risk-list"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

        resp = self.client.put(
            reverse("ai-risk-update", args=[alert.id]),
            {"is_confirmed": True, "outcome": "已安排复查"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["is_confirmed"], True)
        self.assertEqual(resp.data["data"]["outcome"], "已安排复查")


class ProgressApiTests(APITestCase):
    """阶段进展参考接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与训练记录。"""
        from apps.training.models import TrainingRecord

        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-24",
            customer_feedback="左膝疼痛 NRS 6",
        )
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 2",
        )

    def test_analyze_progress_improvement(self) -> None:
        """疼痛降低识别为改善。"""
        resp = self.client.get(reverse("ai-progress"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["pain_trend"], "改善")
        self.assertTrue(any("NRS 6 降至 NRS 2" in obs for obs in data["observations"]))

    def test_analyze_progress_requires_customer_id(self) -> None:
        """缺少 customer_id 返回 400。"""
        resp = self.client.get(reverse("ai-progress"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assessment_trend_matches_identity_and_ignores_draft(self) -> None:
        """评估趋势只比较同一身份键的已完成指标。"""
        previous = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="reassessment",
            status="completed",
            assessment_date="2026-08-01",
        )
        AssessmentMetric.objects.create(
            assessment=previous,
            metric_type="rom",
            body_part="膝关节",
            side="right",
            movement="屈曲",
            measurement_mode="active",
            unit="degree",
            score=90,
        )
        current = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="reassessment",
            status="completed",
            assessment_date="2026-08-15",
        )
        AssessmentMetric.objects.create(
            assessment=current,
            metric_type="rom",
            body_part="膝关节",
            side="right",
            movement="屈曲",
            measurement_mode="active",
            unit="degree",
            score=105,
        )
        draft = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="reassessment",
            status="draft",
            assessment_date="2026-08-20",
        )
        AssessmentMetric.objects.create(
            assessment=draft,
            metric_type="rom",
            body_part="膝关节",
            side="right",
            movement="屈曲",
            measurement_mode="active",
            unit="degree",
            score=160,
        )

        resp = self.client.get(reverse("ai-progress"), {"customer_id": self.customer.id})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        observations = resp.data["data"]["observations"]
        self.assertTrue(any("角度由 90° 变为 105°" in item for item in observations))
        self.assertFalse(any("160" in item for item in observations))


class QaApiTests(APITestCase):
    """专业问答接口测试。"""

    def setUp(self) -> None:
        """准备康复师与官方动作。"""
        from apps.exercises.models import Exercise

        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        Exercise.objects.create(
            name="臀桥", body_part="髋", description="仰卧位臀桥训练", precautions="腰背发力时注意", is_official=True,
        )

    def test_qa_returns_exercise_knowledge(self) -> None:
        """问答返回动作库知识。"""
        resp = self.client.post(reverse("ai-qa"), {"question": "臀桥怎么做"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIn("臀桥", data["answer"])
        self.assertTrue(len(data["sources"]) >= 1)

    def test_qa_requires_question(self) -> None:
        """缺少问题返回 400。"""
        resp = self.client.post(reverse("ai-qa"), {"question": ""}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
