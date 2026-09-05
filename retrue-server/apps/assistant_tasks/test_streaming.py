"""SSE 回归：真实节点进度、传输时序、权限、草稿边界和终态。"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.handlers.asgi import ASGIRequest
from django.test import RequestFactory, SimpleTestCase, TransactionTestCase, override_settings
from langgraph.graph import END, START, StateGraph
from rest_framework.test import APIClient

from apps.ai.models import AiDraft
from apps.ai.orchestration.progress import invoke_with_progress, report_progress
from apps.ai.orchestration.state import OrchestrationState
from apps.assistant_tasks.streaming import turn_stream_response
from apps.common.response import ApiResponse
from apps.conversations.models import Conversation, Message
from apps.customers.models import Customer
from apps.training.models import TrainingRecord


def decode_events(chunks):
    """只解析测试响应的数据帧，忽略连接与心跳注释。"""
    events = []
    for frame in b"".join(chunks).decode().split("\n\n"):
        lines = frame.splitlines()
        event = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if event and data:
            events.append((event, json.loads(data)))
    return events


class ProgressTests(SimpleTestCase):
    """进度来自真实图任务，输出严格固定且接收器在调用结束后释放。"""

    def test_node_events_do_not_expose_state(self):
        graph = StateGraph(OrchestrationState)
        graph.add_node("classify_intent", lambda state: {"reply_content": "测试内部资料"})
        graph.add_edge(START, "classify_intent")
        graph.add_edge("classify_intent", END)
        app = graph.compile()
        events = []
        with report_progress(events.append):
            result = invoke_with_progress(app, {"user_input": "测试敏感输入", "customer_id": 123})
        self.assertEqual(result["reply_content"], "测试内部资料")
        self.assertEqual([event["status"] for event in events], ["running", "completed"])
        self.assertEqual(set(events[0]), {"stage", "label", "status"})
        self.assertNotIn("测试", json.dumps(events, ensure_ascii=False))
        self.assertNotIn("123", json.dumps(events))
        invoke_with_progress(app, {})
        self.assertEqual(len(events), 2)

    def test_concurrent_progress_receivers_are_isolated(self):
        barrier = Barrier(2)

        def execute(name):
            graph = StateGraph(OrchestrationState)
            graph.add_node(name, lambda state: {"reply_content": "测试完成"})
            graph.add_edge(START, name)
            graph.add_edge(name, END)
            events = []
            with report_progress(events.append):
                barrier.wait(timeout=5)
                invoke_with_progress(graph.compile(), {})
            return events

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(execute, "classify_intent")
            second = executor.submit(execute, "answer_general")
            self.assertEqual({event["stage"] for event in first.result()}, {"understand"})
            self.assertEqual({event["stage"] for event in second.result()}, {"compose_reply"})

    def test_capacity_rejection_does_not_start_execution(self):
        with patch("apps.assistant_tasks.streaming._slots") as slots:
            slots.acquire.return_value = False
            with patch("apps.assistant_tasks.streaming.Thread") as thread:
                response = turn_stream_response(RequestFactory().post("/"), lambda: {}, lambda exc: None)
            self.assertEqual(response.status_code, 503)
            thread.assert_not_called()

    def test_wsgi_progress_arrives_before_execution_finishes(self):
        release = Event()
        finished = Event()

        def execute():
            graph = StateGraph(OrchestrationState)
            graph.add_node("answer_general", lambda state: release.wait(5) and {"reply_content": "完成"})
            graph.add_edge(START, "answer_general")
            graph.add_edge("answer_general", END)
            try:
                invoke_with_progress(graph.compile(), {})
                return {"task_id": 1}
            finally:
                finished.set()

        response = turn_stream_response(RequestFactory().post("/"), execute, lambda exc: ApiResponse.error("失败", 500))
        stream = iter(response.streaming_content)
        try:
            self.assertIn(b"connected", next(stream))
            self.assertIn(b"running", next(stream))
            self.assertFalse(finished.is_set())
            release.set()
            events = decode_events(list(stream))
            self.assertEqual(events[-1][0], "result")
        finally:
            release.set()
            finished.wait(5)
            response.close()

    def test_asgi_iterator_and_error_terminal(self):
        request = ASGIRequest({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b""}, None)

        def execute():
            raise RuntimeError("测试内部错误")

        response = turn_stream_response(request, execute, lambda exc: ApiResponse.error("处理失败", 500))
        self.assertTrue(response.is_async)

        async def read():
            return [chunk async for chunk in response.streaming_content]

        events = decode_events(asyncio.run(read()))
        self.assertEqual(events, [("error", {"code": 500, "message": "处理失败", "data": None})])
        response.close()

    def test_heartbeat_and_timeout_do_not_reexecute(self):
        release = Event()
        finished = Event()
        calls = []

        def execute():
            calls.append(1)
            try:
                release.wait(5)
                return {"task_id": 1}
            finally:
                finished.set()

        with patch("apps.assistant_tasks.streaming.HEARTBEAT_SECONDS", 0.01), patch("apps.assistant_tasks.streaming.STREAM_SECONDS", 0.03):
            response = turn_stream_response(RequestFactory().post("/"), execute, lambda exc: ApiResponse.error("失败", 500))
            try:
                chunks = list(response.streaming_content)
                self.assertIn(b": heartbeat", b"".join(chunks))
                self.assertEqual(decode_events(chunks)[-1][1]["code"], 504)
                self.assertEqual(calls, [1])
            finally:
                release.set()
                finished.wait(5)
                response.close()


@override_settings(AI_ORCHESTRATION_ENABLED=True, AI_PROVIDER="mock", AI_CONFIG_FILE="")
class StreamingApiTests(TransactionTestCase):
    """工作线程使用独立数据库连接，所以使用提交可见的事务测试数据。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="sse_test_therapist", password="test-only-password")
        self.client = APIClient()
        self.client.force_login(self.user)
        self.conversation = Conversation.objects.create(therapist=self.user)

    def post_stream(self, **overrides):
        """以浏览器相同的 Accept 与请求结构发起一次 SSE。"""
        return self.client.post("/api/assistant/turns/stream/", {
            "message": "你好", "conversation_id": self.conversation.id, **overrides,
        }, format="json", HTTP_ACCEPT="text/event-stream, application/json")

    def test_general_turn_persists_reply_and_emits_progress(self):
        response = self.post_stream(message="做深蹲时膝盖应该怎么放？")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/event-stream"))
        self.assertEqual(response["X-Accel-Buffering"], "no")
        events = decode_events(list(response.streaming_content))
        response.close()
        self.assertTrue(any(event == "progress" for event, _ in events))
        self.assertEqual(events[-1][0], "result")
        self.assertTrue(events[-1][1]["data"]["reply_content"])
        self.assertEqual(Message.objects.filter(conversation=self.conversation, role="assistant").count(), 1)
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_training_stream_only_creates_pending_draft(self):
        customer = Customer.objects.create(therapist=self.user, name="测试客户甲")
        response = self.post_stream(message="今天做了臀桥3组12次", customer_id=customer.id)
        events = decode_events(list(response.streaming_content))
        response.close()
        self.assertEqual(events[-1][0], "result")
        result = events[-1][1]["data"]
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(AiDraft.objects.get(pk=result["resource_refs"]["draft_id"]).status, "pending")
        self.assertEqual(TrainingRecord.objects.count(), 0)

    def test_other_therapist_conversation_rejected_before_stream(self):
        other = get_user_model().objects.create_user(username="sse_other_therapist")
        conversation = Conversation.objects.create(therapist=other)
        response = self.post_stream(conversation_id=conversation.id)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.streaming)
        self.assertEqual(Message.objects.count(), 0)

    def test_unauthenticated_and_invalid_input_rejected(self):
        self.assertEqual(self.post_stream(message="").status_code, 400)
        self.client.logout()
        self.assertIn(self.post_stream().status_code, (401, 403))

    def test_session_csrf_is_required(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post("/api/assistant/turns/stream/", {"message": "你好"}, format="json")
        self.assertEqual(response.status_code, 403)
