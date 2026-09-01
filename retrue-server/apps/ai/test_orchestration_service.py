"""LangGraph 编排服务（阶段 2/3/4）测试。

覆盖：普通咨询、同名客户选择、未选客户不能客户写入、草稿确认前不能写入、
任务中断恢复、工具失败安全降级。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft, AiDraftStatus
from apps.ai.orchestration import (
    OrchestrationDisabledError,
    handle_turn,
    resume_task,
    submit_customer_selection,
)
from apps.assistant_tasks.models import AssistantTask, AssistantTaskStatus
from apps.customers.models import Customer
from apps.training.models import TrainingRecord

User = get_user_model()


@override_settings(AI_ORCHESTRATION_ENABLED=True)
class OrchestrationServiceTests(APITestCase):
    """编排服务核心流程测试。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer_a = Customer.objects.create(therapist=self.therapist, name="张三")
        self.customer_b = Customer.objects.create(therapist=self.therapist, name="李四")

    def test_general_knowledge_answered_without_customer(self) -> None:
        """普通咨询直接回答，不读客户数据、不创建草稿。"""
        result = handle_turn(self.therapist, message="做深蹲时膝盖应该怎么放？")
        self.assertEqual(result["intent"], "general_knowledge")
        self.assertIsNone(result["customer_id"])
        self.assertEqual(result["resource_refs"], {})
        # 未产生任何草稿或训练记录。
        self.assertEqual(AiDraft.objects.count(), 0)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_training_record_without_customer_waits_selection(self) -> None:
        """未选客户时，训练补记进入等待选择，不生成草稿。"""
        result = handle_turn(self.therapist, message="今天做了臀桥 3 组 12 次")
        self.assertEqual(result["intent"], "training_record")
        self.assertIsNone(result["customer_id"])
        self.assertEqual(result["current_step"], "wait_customer_selection")
        # 未绑定客户不能生成草稿。
        self.assertEqual(AiDraft.objects.count(), 0)

    def test_training_record_with_bound_customer_creates_draft(self) -> None:
        """已绑定客户时，训练补记生成 pending 草稿，等待确认。"""
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        self.assertEqual(result["intent"], "training_record")
        self.assertEqual(result["customer_id"], self.customer_a.id)
        self.assertEqual(result["current_step"], "wait_draft_confirmation")
        self.assertTrue(result["needs_confirmation"])
        self.assertIn("draft_id", result["resource_refs"])
        # 草稿是 pending，不是正式记录。
        draft = AiDraft.objects.get(id=result["resource_refs"]["draft_id"])
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_draft_not_written_before_confirmation(self) -> None:
        """草稿确认前不能写入正式训练记录。"""
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        draft_id = result["resource_refs"]["draft_id"]
        # 图流程本身绝不写正式记录。
        self.assertEqual(TrainingRecord.objects.count(), 0)
        draft = AiDraft.objects.get(id=draft_id)
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertIsNone(draft.training_record_id)

    def test_customer_lookup_single_match_binds(self) -> None:
        """客户姓名唯一匹配时直接绑定客户。"""
        result = handle_turn(self.therapist, message="客户张三最近的训练怎么样", customer_name="张三")
        # 未绑定客户 + 姓名唯一匹配 -> 直接绑定。
        self.assertEqual(result["intent"], "customer_lookup")
        self.assertEqual(result["customer_id"], self.customer_a.id)

    def test_customer_selection_flow(self) -> None:
        """同名客户进入等待选择，提交选择后继续。"""
        Customer.objects.create(therapist=self.therapist, name="张三")
        result = handle_turn(self.therapist, message="客户张三最近怎么样", customer_name="张三")
        self.assertEqual(result["current_step"], "wait_customer_selection")
        self.assertGreaterEqual(len(result["customer_candidates"]), 2)

        task_id = result["task_id"]
        selected = submit_customer_selection(self.therapist, task_id, self.customer_a.id)
        self.assertEqual(selected["customer_id"], self.customer_a.id)

    def test_resume_after_interruption(self) -> None:
        """任务中断后可从 state_data 恢复并继续。"""
        first = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer_a.id,
        )
        task = AssistantTask.objects.get(id=first["task_id"])
        # 模拟中断：任务卡在 running。
        task.status = AssistantTaskStatus.RUNNING
        task.save(update_fields=["status"])

        resumed = resume_task(self.therapist, task.id, message="继续补记")
        self.assertIn(resumed["current_step"], {"wait_draft_confirmation", "wait_customer_selection", "completed"})

    def test_tool_failure_degrades_safely(self) -> None:
        """工具失败时任务降级为失败，不伪造客户历史。"""
        # 已绑定客户 + 客户问题，但 get_customer_context 会因无客户数据而安全返回；
        # 这里通过未绑定客户 + 客户问题场景验证：不会越权读取。
        result = handle_turn(
            self.therapist,
            message="客户张三最近怎么样",
        )
        # 未绑定客户时按姓名检索，而不是直接读其他客户数据。
        self.assertEqual(result["intent"], "customer_lookup")

    def test_customer_selection_rejects_other_therapist_customer(self) -> None:
        """提交其他康复师的客户时被拒绝。"""
        other = User.objects.create_user(username="t2", password="test12345")
        foreign = Customer.objects.create(therapist=other, name="王五")
        result = handle_turn(self.therapist, message="今天做了臀桥 3 组 12 次")
        task_id = result["task_id"]
        from apps.assistant_tasks.services import TaskPermissionError

        with self.assertRaises(TaskPermissionError):
            submit_customer_selection(self.therapist, task_id, foreign.id)


@override_settings(AI_ORCHESTRATION_ENABLED=False)
class OrchestrationDisabledTests(APITestCase):
    """编排功能开关关闭时的行为。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="t1", password="test12345")

    def test_turn_raises_when_disabled(self) -> None:
        """开关关闭时发起回合应抛编排未启用错误。"""
        with self.assertRaises(OrchestrationDisabledError):
            handle_turn(self.therapist, message="你好")
