"""受控只读 Tool 的归属、白名单、脱敏和参数限制测试。"""

from __future__ import annotations

import json

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.assistant_tasks.models import AssistantRunStatus, ToolExecution, ToolExecutionStatus
from apps.assistant_tasks.services import create_task
from apps.assistant_tasks.tools import (
    MAX_TOOL_LIMIT,
    ToolContextMismatchError,
    ToolInputError,
    ToolNotAllowedError,
    ToolPermissionError,
    TOOL_ALLOWLIST,
    execute_tool,
)
from apps.assessments.models import Assessment, AssessmentType
from apps.customers.models import Customer
from apps.schedules.models import CourseSession
from apps.training.models import TrainingRecord
from django.contrib.auth import get_user_model


User = get_user_model()


class ReadOnlyToolServiceTests(APITestCase):
    """覆盖工具注册、客户边界和执行日志。"""

    def setUp(self) -> None:
        """准备两个康复师及互相隔离的客户资源。"""
        self.therapist = User.objects.create_user(username="tool_t1", password="test12345")
        self.other = User.objects.create_user(username="tool_t2", password="test12345")
        self.customer = Customer.objects.create(
            therapist=self.therapist,
            name="张三",
            phone="13812345678",
            main_issue="左膝疼痛",
        )
        self.other_customer = Customer.objects.create(
            therapist=self.other,
            name="李四",
            phone="13987654321",
        )
        self.task = create_task(self.therapist, customer=self.customer, task_type="training_record")

    def test_allowlist_has_only_declared_read_tools(self) -> None:
        """白名单只暴露五个固定只读工具。"""
        self.assertEqual(
            TOOL_ALLOWLIST,
            {
                "search_customers",
                "get_customer_context",
                "list_customer_course_sessions",
                "list_recent_training_records",
                "get_initial_assessment_status",
            },
        )
        with self.assertRaises(ToolNotAllowedError):
            execute_tool(self.task, "os.system", {"command": "id"})

    def test_search_is_scoped_and_logs_only_redacted_summary(self) -> None:
        """客户搜索只能看到任务康复师数据，执行日志不保存手机号或关键词。"""
        result = execute_tool(self.task, "search_customers", {"keyword": "张", "limit": 1})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["phone_masked"], "138****5678")
        run = result.run
        execution = result.tool_execution
        self.assertEqual(run.status, AssistantRunStatus.SUCCEEDED)
        self.assertEqual(execution.status, ToolExecutionStatus.SUCCEEDED)
        serialized_log = json.dumps(
            {"run": run.input_summary, "output": run.output_summary, "tool": execution.input_summary},
            ensure_ascii=False,
        )
        self.assertNotIn("13812345678", serialized_log)
        self.assertNotIn("张", serialized_log)

    def test_customer_mismatch_and_foreign_resource_are_rejected_and_logged(self) -> None:
        """任务客户不一致和跨康复师课程均被拒绝并保留失败日志。"""
        with self.assertRaises(ToolContextMismatchError):
            execute_tool(self.task, "get_customer_context", {"customer_id": self.other_customer.id})
        self.assertEqual(ToolExecution.objects.filter(status=ToolExecutionStatus.FAILED).count(), 1)

        foreign_session = CourseSession.objects.create(
            therapist=self.other,
            customer=self.other_customer,
            date="2026-09-01",
        )
        with self.assertRaises(ToolPermissionError):
            execute_tool(
                self.task,
                "list_customer_course_sessions",
                {"course_session_id": foreign_session.id},
            )
        self.assertEqual(ToolExecution.objects.filter(status=ToolExecutionStatus.FAILED).count(), 2)

    def test_parameter_limits_create_failed_run_without_raw_input(self) -> None:
        """limit 超上限时拒绝，并且失败日志只保留参数键。"""
        with self.assertRaises(ToolInputError):
            execute_tool(
                self.task,
                "list_recent_training_records",
                {"limit": MAX_TOOL_LIMIT + 1, "keyword": "不应写入日志"},
            )
        execution = self.task.tool_executions.order_by("-id").first()
        self.assertIsNotNone(execution)
        self.assertEqual(execution.status, ToolExecutionStatus.FAILED)
        self.assertNotIn("不应写入日志", json.dumps(execution.input_summary, ensure_ascii=False))

    def test_context_and_initial_assessment_status_are_read_only(self) -> None:
        """客户上下文和首次评估状态查询不返回完整病史，也不写业务表。"""
        Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type=AssessmentType.INITIAL,
            assessment_date="2026-08-20",
            status="draft",
            medical_history="完整病史不应进入工具日志",
        )
        result = execute_tool(self.task, "get_customer_context")
        self.assertEqual(result["customer"]["phone_masked"], "138****5678")
        self.assertNotIn("medical_history", result["initial_assessment"])
        status_result = execute_tool(self.task, "get_initial_assessment_status")
        self.assertTrue(status_result["exists"])
        self.assertEqual(status_result["status"], "draft")
        self.assertEqual(self.task.runs.count(), 2)


class ReadOnlyToolApiTests(APITestCase):
    """覆盖只读 Tool API 的任务归属和统一响应。"""

    def setUp(self) -> None:
        """准备登录康复师及其任务。"""
        self.therapist = User.objects.create_user(username="tool_api_t1", password="test12345")
        self.other = User.objects.create_user(username="tool_api_t2", password="test12345")
        self.customer = Customer.objects.create(therapist=self.therapist, name="王五")
        self.task = create_task(self.therapist, customer=self.customer, task_type="assessment")
        self.client.force_login(self.therapist)

    def test_api_executes_owned_task_only(self) -> None:
        """API 成功返回统一信封，其他康复师任务不可执行。"""
        response = self.client.post(
            reverse("assistant-task-tool-execute", args=[self.task.id]),
            {"tool_name": "get_initial_assessment_status", "arguments": {}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["code"], 200)
        self.assertEqual(response.data["data"]["result"]["customer_id"], self.customer.id)
        self.assertEqual(response.data["data"]["tool_execution"]["is_write"], False)

        foreign_task = create_task(self.other, customer=Customer.objects.create(therapist=self.other, name="赵六"))
        response = self.client.post(
            reverse("assistant-task-tool-execute", args=[foreign_task.id]),
            {"tool_name": "search_customers", "arguments": {}},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
