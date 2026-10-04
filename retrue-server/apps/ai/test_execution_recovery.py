"""验证持久辅助任务、执行归属与请求重试，不调用真实模型。"""

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.orchestration.auxiliary import enqueue_memory, process_memory_task
from apps.ai.orchestration.execution import execution_scope, GuardedProvider
from apps.ai.orchestration.service import _start_run, _finalize_attempt, handle_turn
from apps.assistant_tasks.models import AssistantTask, AssistantRun, AssistantRunStatus
from apps.assistant_tasks.services import TaskVersionConflict
from apps.conversations.models import Conversation, Message
from apps.customers.models import Customer


@override_settings(AI_PROVIDER="mock", AI_CONFIG_FILE="", AI_ORCHESTRATION_ENABLED=True)
class ExecutionRecoveryTests(TestCase):
    """异步只是排队，候选仍需人工确认；失效尝试不能复活任务。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="recovery_test")
        self.customer = Customer.objects.create(therapist=self.user, name="模拟客户")
        self.conversation = Conversation.objects.create(therapist=self.user, customer=self.customer)
        self.task = AssistantTask.objects.create(therapist=self.user, customer=self.customer, conversation=self.conversation)

    def test_only_one_live_attempt(self):
        """同一任务不能并行恢复两次。"""
        _start_run(self.task)
        with self.assertRaises(TaskVersionConflict):
            _start_run(self.task)
        self.assertEqual(AssistantRun.objects.count(), 1)

    def test_read_tools_reuse_live_attempt_and_advance_sequence(self):
        """多个只读工具不结束外层执行，序号零之后仍递增。"""
        from apps.assistant_tasks.tools import execute_tool
        run = _start_run(self.task)
        with execution_scope(run):
            first = execute_tool(self.task, "get_customer_context", {})
            second = execute_tool(self.task, "get_customer_context", {})
        run.refresh_from_db()
        self.assertEqual(run.status, AssistantRunStatus.RUNNING)
        self.assertEqual(AssistantRun.objects.count(), 1)
        self.assertEqual((first.run.id, second.run.id), (run.id, run.id))
        self.assertEqual((first.tool_execution.sequence, second.tool_execution.sequence), (0, 1))

    def test_old_completion_and_failure_do_not_overwrite_retry(self):
        """旧尝试晚完成或报错，都保留最新执行状态。"""
        old = _start_run(self.task)
        AssistantRun.objects.filter(pk=old.id).update(status=AssistantRunStatus.TIMED_OUT)
        new = _start_run(self.task)
        with self.assertRaises(TaskVersionConflict):
            _finalize_attempt(self.task, old, {"next_node": "answer_general"})
        _finalize_attempt(self.task, old, error=RuntimeError("模拟旧错误"))
        new.refresh_from_db()
        self.assertEqual(new.status, AssistantRunStatus.RUNNING)

    def test_provider_result_discarded_after_attempt_invalidated(self):
        """模型返回前失效，不把晚返回内容交给草稿写入。"""
        run = _start_run(self.task)
        class DelayedProvider:
            def chat(self):
                AssistantRun.objects.filter(pk=run.id).update(status=AssistantRunStatus.TIMED_OUT)
                return "模拟晚返回结果"
        with self.assertRaises(TaskVersionConflict), execution_scope(run):
            GuardedProvider(DelayedProvider()).chat()

    def queued(self):
        """来源消息只以 ID 排队，队列不复制健康原文。"""
        message = Message.objects.create(conversation=self.conversation, role="user", content="模拟长期偏好")
        state = {"assistant_task_id": self.task.id, "conversation_id": self.conversation.id,
                 "customer_id": self.customer.id, "user_message_id": message.id}
        enqueue_memory(state)
        enqueue_memory(state)
        return AssistantTask.objects.get(origin="deferred_memory")

    def test_queue_is_persistent_and_idempotent(self):
        """同一来源只排队一次；工作命令可以在另一次请求中完成。"""
        task = self.queued()
        self.assertNotIn("模拟长期偏好", str(task.state_data))
        with patch("apps.knowledge.memory_evaluator.evaluate_message_for_memory", return_value=[]) as evaluate:
            self.assertTrue(process_memory_task(task.id))
            self.assertFalse(process_memory_task(task.id))
        evaluate.assert_called_once()
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")

    def test_failed_worker_can_retry(self):
        """外部调用失败保留任务，重试成功后不再次评估。"""
        task = self.queued()
        with patch("apps.knowledge.memory_evaluator.evaluate_message_for_memory", side_effect=RuntimeError("模拟服务中断")):
            self.assertFalse(process_memory_task(task.id))
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")
        with patch("apps.knowledge.memory_evaluator.evaluate_message_for_memory", return_value=[]):
            self.assertTrue(process_memory_task(task.id))
        self.assertEqual(task.runs.count(), 2)

    def test_request_replay_does_not_repeat_messages_or_runs(self):
        """相同 request_id 查现有结果，不再次调用模型或新增消息。"""
        kwargs = dict(message="深蹲动作如何做？", conversation_id=self.conversation.id,
                      customer_id=self.customer.id, client_request_id="recovery_same_request")
        first = handle_turn(self.user, **kwargs)
        counts = (Message.objects.count(), AssistantRun.objects.count())
        second = handle_turn(self.user, **kwargs)
        self.assertEqual(second["task_id"], first["task_id"])
        self.assertEqual(second["reply_content"], first["reply_content"])
        self.assertEqual((Message.objects.count(), AssistantRun.objects.count()), counts)
