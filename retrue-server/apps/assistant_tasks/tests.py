"""AssistantTask 统一任务基础设施测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.assistant_tasks.models import AssistantRun, AssistantTask, TaskEvent, ToolExecution
from apps.assistant_tasks.serializers import ToolExecutionSerializer
from apps.assistant_tasks.services import (
    ResourceOwnershipError,
    ResourceValidationError,
    TaskIdempotencyConflict,
    TaskTransitionError,
    TaskVersionConflict,
    cancel_task,
    create_task,
    get_owned_task,
    transition_task,
    update_task_state,
)
from apps.customers.models import Customer
from apps.schedules.models import CourseSession


User = get_user_model()


class AssistantTaskServiceTests(APITestCase):
    """覆盖服务层幂等、权限、资源归属和状态机。"""

    def setUp(self) -> None:
        """准备两位康复师及各自客户。"""
        self.therapist = User.objects.create_user(username="assistant_t1", password="test12345")
        self.other = User.objects.create_user(username="assistant_t2", password="test12345")
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

    def test_client_request_id_is_idempotent(self) -> None:
        """相同客户端幂等键应返回原任务而不重复写入。"""
        first = create_task(
            self.therapist,
            customer=self.customer,
            skill_code="assessment.extract",
            task_type="assessment",
            client_request_id="req-1",
        )
        second = create_task(
            self.therapist,
            customer=self.customer,
            skill_code="assessment.extract",
            task_type="assessment",
            client_request_id="req-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AssistantTask.objects.count(), 1)
        self.assertEqual(TaskEvent.objects.filter(task=first, event_type="task_created").count(), 1)

    def test_client_request_id_cannot_switch_customer_context(self) -> None:
        """同一请求号换客户时必须报冲突，不能静默返回旧任务。"""
        create_task(
            self.therapist,
            customer=self.customer,
            task_type="training_record",
            client_request_id="request-context-1",
        )
        another_customer = Customer.objects.create(therapist=self.therapist, name="同组客户")
        with self.assertRaises(TaskIdempotencyConflict):
            create_task(
                self.therapist,
                customer=another_customer,
                task_type="training_record",
                client_request_id="request-context-1",
            )

    def test_unfinished_business_key_is_reused(self) -> None:
        """同一客户的未完成业务键应复用任务，完成后才可重新创建。"""
        first = create_task(self.therapist, customer=self.customer, business_key="session:1")
        second = create_task(self.therapist, customer=self.customer, business_key="session:1")
        self.assertEqual(first.pk, second.pk)
        transition_task(first, "running")
        transition_task(first, "completed")
        third = create_task(self.therapist, customer=self.customer, business_key="session:1")
        self.assertNotEqual(first.pk, third.pk)

    def test_get_owned_task_isolated(self) -> None:
        """其他康复师不能通过任务主键读取任务。"""
        task = create_task(self.therapist, customer=self.customer)
        self.assertIsNotNone(get_owned_task(self.therapist, task.id))
        self.assertIsNone(get_owned_task(self.other, task.id))

    def test_resource_must_belong_to_therapist_and_customer(self) -> None:
        """上下文课程需同时属于当前康复师和任务客户。"""
        session = CourseSession.objects.create(
            therapist=self.other,
            customer=self.other_customer,
            date="2026-09-01",
        )
        with self.assertRaises(ResourceOwnershipError):
            create_task(
                self.therapist,
                customer=self.customer,
                context_resource_type="course_session",
                context_resource_id=session.id,
            )

    def test_resource_customer_mismatch_is_rejected(self) -> None:
        """当前康复师拥有的资源也不能绑定到另一个客户。"""
        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            date="2026-09-01",
        )
        another_customer = Customer.objects.create(therapist=self.therapist, name="王五")
        with self.assertRaises(ResourceValidationError):
            create_task(
                self.therapist,
                customer=another_customer,
                context_resource_type="course_session",
                context_resource_id=session.id,
            )

    def test_transition_records_event_and_cancel_is_idempotent(self) -> None:
        """状态转换应递增版本并留痕，重复取消不重复变更。"""
        task = create_task(self.therapist, customer=self.customer)
        transition_task(task, "waiting_user", current_step="collect_history", event_type="needs_input")
        task.refresh_from_db()
        self.assertEqual(task.status, "waiting_user")
        self.assertEqual(task.version, 2)
        self.assertTrue(TaskEvent.objects.filter(task=task, event_type="needs_input").exists())
        cancel_task(task, "用户取消")
        version = task.version
        cancel_task(task, "重复取消")
        task.refresh_from_db()
        self.assertEqual(task.status, "cancelled")
        self.assertEqual(task.version, version)

    def test_completed_task_cannot_be_cancelled(self) -> None:
        """已完成任务不允许被取消。"""
        task = create_task(self.therapist, customer=self.customer)
        transition_task(task, "running")
        transition_task(task, "completed")
        with self.assertRaises(TaskTransitionError):
            cancel_task(task)

    def test_patch_state_uses_optimistic_version(self) -> None:
        """恢复数据更新必须携带最新版本，冲突时不覆盖他人更新。"""
        task = create_task(self.therapist, customer=self.customer)
        updated = update_task_state(task, 1, current_step="step-1", state_data={"draft_id": 1})
        self.assertEqual(updated.version, 2)
        with self.assertRaises(TaskVersionConflict):
            update_task_state(updated, 1, current_step="stale")

    def test_state_data_rejects_raw_training_text(self) -> None:
        """任务恢复字段只能存摘要或资源 ID，不得重复保存健康原文。"""
        task = create_task(self.therapist, customer=self.customer)
        with self.assertRaises(ResourceValidationError):
            update_task_state(task, task.version, state_data={"input_text": "膝盖疼痛 2 分"})

    def test_pending_task_cannot_complete_without_execution(self) -> None:
        """完成必须来自运行中或待确认流程，避免客户端跳过人工确认。"""
        task = create_task(self.therapist, customer=self.customer)
        with self.assertRaises(TaskTransitionError):
            transition_task(task, "completed")

    def test_tool_execution_can_trace_task_through_run(self) -> None:
        """历史工具记录即使未填直接 task，也能通过 run 展示任务。"""
        task = create_task(self.therapist, customer=self.customer)
        run = AssistantRun.objects.create(task=task)
        execution = ToolExecution.objects.create(run=run, tool_name="customer_lookup")
        self.assertEqual(ToolExecutionSerializer(execution).data["task"], task.id)


class AssistantTaskApiTests(APITestCase):
    """覆盖任务 API 的认证、隔离、筛选和取消。"""

    def setUp(self) -> None:
        """准备登录康复师和客户。"""
        self.therapist = User.objects.create_user(username="assistant_api_t1", password="test12345")
        self.other = User.objects.create_user(username="assistant_api_t2", password="test12345")
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")
        self.client.force_login(self.therapist)

    def test_create_list_detail_and_cancel(self) -> None:
        """创建、筛选、详情和取消均使用统一响应信封。"""
        response = self.client.post(
            reverse("assistant-task-list-create"),
            {
                "customer": self.customer.id,
                "skill_code": "training.note",
                "task_type": "training_record",
                "business_key": "training:1",
                "client_request_id": "api-1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], 200)
        task_id = response.data["data"]["id"]
        repeat = self.client.post(
            reverse("assistant-task-list-create"),
            {
                "customer": self.customer.id,
                "skill_code": "training.note",
                "task_type": "training_record",
                "business_key": "training:1",
                "client_request_id": "api-1",
            },
            format="json",
        )
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.data["data"]["id"], task_id)
        listing = self.client.get(reverse("assistant-task-list-create"), {"resumable": "true"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data["data"]), 1)
        detail = self.client.get(reverse("assistant-task-detail", args=[task_id]))
        self.assertEqual(detail.status_code, 200)
        cancel = self.client.post(
            reverse("assistant-task-cancel", args=[task_id]),
            {"reason": "不再需要"},
            format="json",
        )
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.data["data"]["status"], "cancelled")

    def test_other_customer_and_task_are_isolated(self) -> None:
        """不能创建或读取其他康复师客户/任务。"""
        response = self.client.post(
            reverse("assistant-task-list-create"),
            {"customer": self.other_customer.id, "task_type": "assessment"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        other_task = create_task(self.other, customer=self.other_customer)
        response = self.client.get(reverse("assistant-task-detail", args=[other_task.id]))
        self.assertEqual(response.status_code, 404)

    def test_customer_name_lookup_returns_only_current_therapist_matches(self) -> None:
        """同名客户返回列表，其他康复师同名客户不得泄露。"""
        second = Customer.objects.create(
            therapist=self.therapist,
            name="张三",
            phone="13912345678",
            main_issue="肩部不适",
        )
        Customer.objects.create(therapist=self.other, name="张三", phone="13712345678")
        response = self.client.get(
            reverse("assistant-customer-name-lookup"),
            {"name": "张三"},
        )
        self.assertEqual(response.status_code, 200)
        matches = response.data["data"]
        self.assertEqual({item["id"] for item in matches}, {self.customer.id, second.id})
        second_result = next(item for item in matches if item["id"] == second.id)
        self.assertEqual(second_result["phone_masked"], "139****5678")

    def test_patch_rejects_status_and_checks_version(self) -> None:
        """PATCH 不能伪造状态，且过期版本返回 409。"""
        task = create_task(self.therapist, customer=self.customer)
        response = self.client.patch(
            reverse("assistant-task-detail", args=[task.id]),
            {"status": "completed", "version": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            reverse("assistant-task-detail", args=[task.id]),
            {"current_step": "step-1", "version": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(
            reverse("assistant-task-detail", args=[task.id]),
            {"current_step": "stale", "version": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
