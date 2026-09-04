"""受控 ReAct 客户查询（阶段 A）测试。

覆盖：已绑定客户的 recent_training 查询走受控 ReAct 子图并产生 ToolExecution
审计；模型越权字段与未授权 Tool 被拒绝；同参去重；决策/调用次数上限；失败与
schema 非法时不伪造事实；训练补记等写分支不误入 ReAct 子图。
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from apps.ai.orchestration import handle_turn
from apps.ai.orchestration.intent import detect_query_goal
from apps.ai.orchestration.nodes import (
    _FORBIDDEN_REACT_ARGUMENT_FIELDS,
    _QUERY_GOAL_TOOLS,
    _is_valid_tool_decision,
    _tool_signature,
)
from apps.assistant_tasks.models import AssistantRun, AssistantTask
from apps.ai.schemas.react import ReactDecision

User = get_user_model()


class QueryGoalDetectionTests(SimpleTestCase):
    """查询目标识别测试。"""

    def test_detect_recent_training_goal(self) -> None:
        """“最近训练怎么样”被识别为 recent_training。"""
        self.assertEqual(detect_query_goal("黄伟成最近训练怎么样"), "recent_training")

    def test_detect_assessment_progress_goal(self) -> None:
        """“评估有没有改善”被识别为 assessment_progress。"""
        self.assertEqual(detect_query_goal("疼痛有没有改善，评估结果如何"), "assessment_progress")

    def test_detect_attendance_goal(self) -> None:
        """“最近有没有缺课”被识别为 attendance_or_course。"""
        self.assertEqual(detect_query_goal("她最近有没有缺课"), "attendance_or_course")

    def test_detect_customer_profile_goal(self) -> None:
        """“基础情况是什么”被识别为 customer_profile。"""
        self.assertEqual(detect_query_goal("他的基础情况是什么"), "customer_profile")

    def test_no_goal_returns_empty(self) -> None:
        """泛化进度询问不命中具体查询目标。"""
        self.assertEqual(detect_query_goal("这个客户进展怎么样"), "")

    def test_goal_tool_mapping_within_read_allowlist(self) -> None:
        """每个查询目标都映射到服务端只读白名单内的 Tool。"""
        from apps.assistant_tasks.tools import READ_ONLY_TOOL_ALLOWLIST

        for tools in _QUERY_GOAL_TOOLS.values():
            self.assertTrue(all(name in READ_ONLY_TOOL_ALLOWLIST for name in tools))


class ReactDecisionSchemaTests(SimpleTestCase):
    """ReAct 决策 schema 校验测试。"""

    def test_valid_tool_call(self) -> None:
        decision = ReactDecision(
            action="tool_call",
            tool_name="list_recent_training_records",
            arguments={"days": 14},
            reason="需要读取近期训练",
        )
        self.assertEqual(decision.action, "tool_call")

    def test_invalid_action_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ReactDecision(action="run_python", tool_name="exec")

    def test_valid_final(self) -> None:
        decision = ReactDecision(action="final", reason="已获得足够事实", insufficient_information=False)
        self.assertEqual(decision.action, "final")

    def test_final_answer_is_not_part_of_decision_contract(self) -> None:
        """最终文案由最终回答器生成，决策对象不得夹带自由文本答复。"""
        with self.assertRaises(ValueError):
            ReactDecision(action="final", answer="不应在决策阶段输出")


class ReactGuardTests(SimpleTestCase):
    """ReAct 越权/越界防护的纯逻辑测试。"""

    def test_decision_cap_degrades_to_final(self) -> None:
        """超过决策次数上限时不再调用模型，直接转入安全降级 final。"""
        from apps.ai.orchestration import limits
        from apps.ai.orchestration.nodes import react_decide_node
        from apps.ai.orchestration.state import build_initial_state

        state = build_initial_state(assistant_task_id=1, customer_id=7)
        state["intent"] = "customer_analysis"
        state["query_goal"] = "recent_training"
        state["available_react_tools"] = []
        state["react_iteration"] = limits.max_react_decisions()
        out = react_decide_node(state)
        decision = out.get("react_pending_decision") or {}
        self.assertEqual(decision.get("action"), "final")
        self.assertTrue(decision.get("insufficient_information", False))
        self.assertEqual(out.get("next_node"), "react_finalize")

    @patch("apps.ai.orchestration.nodes._chat")
    def test_final_without_observation_is_reprompted_for_tool(self, mock_chat) -> None:
        """有可用 Tool 且尚未取数时，模型过早 final 会被要求重新选择。"""
        from apps.ai.orchestration.nodes import react_decide_node
        from apps.ai.orchestration.state import build_initial_state

        mock_chat.side_effect = [
            '{"action":"final","answer":"资料不足","insufficient_information":true}',
            '{"action":"tool_call","tool_name":"list_recent_training_records",'
            '"arguments":{"days":30},"reason":"需要读取训练记录"}',
        ]
        state = build_initial_state(assistant_task_id=1, customer_id=7)
        state["intent"] = "customer_analysis"
        state["user_input"] = "黄伟成最近做了几次训练"
        state["query_goal"] = "recent_training"
        state["available_react_tools"] = [
            {
                "name": "list_recent_training_records",
                "description": "读取近期训练记录摘要",
                "input_schema": {"type": "object", "properties": {"days": {"type": "integer"}}},
            }
        ]

        out = react_decide_node(state)

        self.assertEqual(mock_chat.call_count, 2)
        self.assertEqual((out.get("react_pending_decision") or {}).get("action"), "tool_call")
        self.assertEqual((out.get("react_pending_decision") or {}).get("tool_name"), "list_recent_training_records")

    def test_forbidden_fields_are_defined(self) -> None:
        """customer_id/therapist_id 必须被列为禁止提交字段。"""
        self.assertIn("customer_id", _FORBIDDEN_REACT_ARGUMENT_FIELDS)
        self.assertIn("therapist_id", _FORBIDDEN_REACT_ARGUMENT_FIELDS)

    def test_model_submitting_customer_id_rejected(self) -> None:
        """模型提交 customer_id 的 Tool 决策被拒绝。"""
        decision = {
            "action": "tool_call",
            "tool_name": "list_recent_training_records",
            "arguments": {"customer_id": 123, "days": 14},
        }
        self.assertFalse(
            _is_valid_tool_decision(decision, ["list_recent_training_records"], frozenset({"list_recent_training_records"}))
        )

    def test_unknown_tool_rejected(self) -> None:
        """未在本轮子集的 Tool 被拒绝。"""
        decision = {
            "action": "tool_call",
            "tool_name": "search_customers",
            "arguments": {},
        }
        # 即使它在全局白名单，只要不在本轮可用子集就被拒绝。
        self.assertFalse(
            _is_valid_tool_decision(
                decision,
                ["list_recent_training_records"],
                frozenset({"list_recent_training_records", "search_customers"}),
            )
        )

    def test_same_signature_deduplicates(self) -> None:
        """相同 Tool + 相同参数产生相同去重签名。"""
        a = _tool_signature("list_recent_training_records", {"days": 14, "customer_id": 1})
        b = _tool_signature("list_recent_training_records", {"customer_id": 1, "days": 14})
        self.assertEqual(a, b)
        c = _tool_signature("list_recent_training_records", {"days": 30, "customer_id": 1})
        self.assertNotEqual(a, c)

    def test_finalize_without_facts_never_fabricates(self) -> None:
        """没有任何可用 Observation 时，最终回答如实说明资料不足，不伪造。"""
        from apps.ai.orchestration.nodes import react_finalize_node
        from apps.ai.orchestration.state import build_initial_state

        state = build_initial_state(assistant_task_id=1, customer_id=7, conversation_id=None)
        state["user_input"] = "黄伟成最近训练怎么样"
        state["query_goal"] = "recent_training"
        state["react_observations"] = []
        state["react_pending_decision"] = {"action": "final", "insufficient_information": True}
        out = react_finalize_node(state)
        reply = out.get("reply_content") or ""
        self.assertIn("资料不足", reply)
        # 绝不输出任何看似“系统记录事实”的内容。
        self.assertNotIn("训练动作", reply)
        self.assertEqual(out.get("next_node"), "react_finalized")

    @patch("apps.ai.orchestration.nodes._chat")
    def test_finalize_reprompts_when_model_discards_existing_facts(self, mock_chat) -> None:
        """已有训练记录时，data_gap=true 不得覆盖已查询的事实。"""
        from apps.ai.orchestration.nodes import react_finalize_node
        from apps.ai.orchestration.state import build_initial_state

        mock_chat.side_effect = [
            '{"answer":"资料不足","facts":[],"advice":[],"data_gap":true}',
            '{"answer":"近 30 天训练记录已查询到。","facts":["近 30 天共 3 条训练记录"],'
            '"advice":[],"data_gap":false}',
        ]
        state = build_initial_state(assistant_task_id=1, customer_id=7, conversation_id=None)
        state["user_input"] = "黄伟成最近做了几次训练"
        state["react_observations"] = [
            {"tool": "list_recent_training_records", "summary": "客户ID 7；共 3 条", "error": ""}
        ]

        out = react_finalize_node(state)

        self.assertEqual(mock_chat.call_count, 2)
        self.assertIn("近 30 天共 3 条训练记录", out.get("reply_content") or "")
        self.assertNotIn("资料不足", out.get("reply_content") or "")

    def test_compose_answer_distinguishes_facts_and_advice(self) -> None:
        """结构化最终回答渲染时区分「系统记录事实」与「建议」。"""
        from apps.ai.orchestration.nodes import _compose_react_answer

        text = _compose_react_answer(
            {
                "answer": "已查询到近期训练记录。",
                "facts": ["该客户近 14 天有 6 次训练记录。"],
                "advice": ["建议下次训练关注动作质量。"],
                "data_gap": False,
            }
        )
        self.assertIn("系统记录", text)
        self.assertIn("建议：", text)

    def test_customer_answer_prompt_separates_summary_from_auditable_facts(self) -> None:
        """提示词要求正文不再复述系统记录，避免同一事实重复展示。"""
        from apps.ai.prompts.loader import load_prompt

        prompt = load_prompt("react_customer_answer_system")

        self.assertIn("不得重复 facts 中已有的数量、日期、动作等信息", prompt)
        self.assertIn("避免语义重复", prompt)

    @patch("apps.ai.orchestration.nodes._chat")
    def test_legacy_customer_answer_uses_structured_facts_without_repetition(self, mock_chat) -> None:
        """兼容的 customer_question 路径也必须使用结构化事实回答。"""
        from apps.ai.orchestration.nodes import answer_with_context_node
        from apps.ai.orchestration.state import build_initial_state

        mock_chat.return_value = (
            '{"answer":"已查到排课信息；课程具体内容尚未记录。",'
            '"facts":["当前已安排 4 次课程，日期为 2026-09-07、2026-09-09。"],'
            '"advice":["如需训练细节，请人工核查。"],"data_gap":false}'
        )
        state = build_initial_state(assistant_task_id=1, customer_id=7, conversation_id=None)
        state["user_input"] = "课程如何安排"
        state["tool_contexts"] = [{"tool": "get_customer_context", "result": {"course_count": 4}}]

        reply = answer_with_context_node(state).get("reply_content") or ""

        self.assertEqual(reply.count("当前已安排 4 次课程"), 1)
        self.assertIn("—— 系统记录：", reply)
        self.assertIn("建议：", reply)

    @patch("apps.ai.orchestration.nodes._chat")
    def test_finalize_strips_internal_ids_from_model_output(self, mock_chat) -> None:
        """即使模型复述客户/记录 ID，最终自然语言回复也不能泄露。"""
        from apps.ai.orchestration.nodes import react_finalize_node
        from apps.ai.orchestration.state import build_initial_state

        mock_chat.return_value = (
            '{"answer":"黄伟成（客户ID 5）近期有3条记录，训练记录 ID: 18。",'
            '"facts":["客户编号为5","该客户（ID 5）当前计划有效"],'
            '"advice":["任务 ID 9 仅供内部追踪"],"data_gap":false}'
        )
        state = build_initial_state(assistant_task_id=1, customer_id=5, conversation_id=None)
        state["react_observations"] = [{"tool": "list_recent_training_records", "summary": "共 3 条", "error": ""}]

        reply = react_finalize_node(state).get("reply_content") or ""

        self.assertIn("黄伟成", reply)
        self.assertNotRegex(reply, r"(?:客户\s*)?(?:ID|编号)\s*(?:为|是|[:：#])?\s*\d+")
        self.assertNotRegex(reply, r"\bID\s*(?:为|是|[:：#])?\s*\d+")

    def test_parse_invalid_final_answer_returns_none(self) -> None:
        """模型输出非 JSON / 空内容时解析失败，走安全降级。"""
        from apps.ai.orchestration.nodes import _parse_react_final_answer

        self.assertIsNone(_parse_react_final_answer(""))
        self.assertIsNone(_parse_react_final_answer("我不是JSON"))
        parsed = _parse_react_final_answer('{"answer":"ok","facts":[],"data_gap":true}')
        self.assertTrue(parsed)
        self.assertTrue(parsed["data_gap"])


@override_settings(AI_ORCHESTRATION_ENABLED=True, AI_PROVIDER="mock", AI_CONFIG_FILE="")
class ReactAnalysisServiceTests(APITestCase):
    """受控 ReAct 客户分析端到端测试。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="react1", password="test12345")
        from apps.customers.models import Customer as _Customer

        self.customer = _Customer.objects.create(therapist=self.therapist, name="黄伟成")

    def test_recent_training_analysis_uses_read_tool_with_audit(self) -> None:
        """已绑定客户 + 最近训练怎么样 -> customer_analysis 且执行只读 Tool。"""
        result = handle_turn(
            self.therapist,
            message="黄伟成最近训练怎么样",
            customer_id=self.customer.id,
        )
        self.assertEqual(result["intent"], "customer_analysis")
        # 查询目标被回传，供前端按目标门控「查看近期训练」入口。
        self.assertEqual(result.get("query_goal"), "recent_training")
        self.assertTrue(result["reply_content"])
        task = AssistantTask.objects.get(id=result["task_id"])
        # 只读 Tool 被执行并留下审计：ToolExecution + AssistantRun。
        self.assertGreaterEqual(task.tool_executions.count(), 1)
        self.assertEqual(task.tool_executions.first().tool_name, "list_recent_training_records")
        self.assertGreaterEqual(task.runs.count(), 1)
        # 不产生任何草稿或正式记录。
        self.assertEqual(task.tool_executions.filter(is_write=True).count(), 0)

    def test_unbound_name_analysis_still_resolves_identity_first(self) -> None:
        """未绑定具名查询先做身份解析，命中后只读取该客户的数据。"""
        result = handle_turn(self.therapist, message="客户黄伟成最近的训练强度如何")
        self.assertEqual(result["intent"], "customer_analysis")
        self.assertEqual(result["customer_id"], self.customer.id)
        task = AssistantTask.objects.get(id=result["task_id"])
        self.assertGreaterEqual(task.tool_executions.count(), 1)

    def test_write_draft_branch_not_routed_into_react(self) -> None:
        """训练补记等写分支不进入 customer_analysis ReAct 子图。"""
        result = handle_turn(
            self.therapist,
            message="今天做了臀桥 3 组 12 次",
            customer_id=self.customer.id,
        )
        self.assertEqual(result["intent"], "training_record")
        self.assertEqual(result["current_step"], "wait_draft_confirmation")
        # 未执行 ReAct 只读 Tool。
        task = AssistantTask.objects.get(id=result["task_id"])
        self.assertEqual(task.tool_executions.count(), 0)

    def test_analysis_returns_query_goal_for_frontend_gating(self) -> None:
        """训练类分析回复携带 recent_training，供前端门控「查看近期训练」。"""
        result = handle_turn(
            self.therapist,
            message="黄伟成最近训练怎么样",
            customer_id=self.customer.id,
        )
        self.assertEqual(result["intent"], "customer_analysis")
        self.assertEqual(result.get("query_goal"), "recent_training")


class AnalysisMetricsTests(SimpleTestCase):
    """阶段 C 质量监控埋点（脱敏计数）测试。"""

    def setUp(self) -> None:
        from apps.ai.orchestration import metrics

        self.records: list[dict] = []

        # 通过模块级 set_recorder 注入内存 recorder，collect 到 self.records。
        def record(_self: object, data: dict) -> None:
            self.records.append(dict(data))

        self._old = metrics.set_recorder(
            type("RecordingRecorder", (), {"record": record})()
        )

    def tearDown(self) -> None:
        from apps.ai.orchestration import metrics

        metrics.set_recorder(self._old)

    def test_no_execution_reports_zeros(self) -> None:
        """未执行工具的分析回合上报零值计数。"""
        from apps.ai.orchestration import metrics

        metrics.record_turn_metrics(
            {"intent": "customer_analysis", "react_observations": [], "react_tool_signatures": []}
        )
        self.assertEqual(len(self.records), 1)
        rec = self.records[0]
        self.assertEqual(rec[metrics.KEY_TOOL_CALLS], 0)
        self.assertEqual(rec[metrics.KEY_TOOL_FAILURES], 0)
        self.assertFalse(rec[metrics.KEY_CAPPED])

    def test_tool_calls_and_failures_counted(self) -> None:
        """记录实际工具次数与失败次数，且不落原文/参数。"""
        from apps.ai.orchestration import metrics

        metrics.record_turn_metrics(
            {
                "intent": "customer_analysis",
                "react_tool_signatures": ["a:1", "b:2"],
                "react_observations": [
                    {"tool": "list_recent_training_records", "summary": "共 2 条", "error": ""},
                    {"tool": "get_customer_context", "summary": "", "error": "查询失败"},
                ],
            }
        )
        rec = self.records[0]
        self.assertEqual(rec[metrics.KEY_TOOL_CALLS], 2)
        self.assertEqual(rec[metrics.KEY_TOOL_FAILURES], 1)
        # 摘要绝不进入指标。
        self.assertTrue("共 2 条" not in str(rec))

    def test_invalid_decision_and_capped_flagged(self) -> None:
        """模型输出非法或触发上限被标记，供非法调用率/上限率统计。"""
        from apps.ai.orchestration import metrics

        metrics.record_turn_metrics(
            {
                "intent": "customer_analysis",
                "react_last_error": "模型输出非法，已拒绝并降级回答",
                "react_pending_decision": {},
            }
        )
        rec = self.records[0]
        self.assertEqual(rec[metrics.KEY_INVALID_DECISIONS], 1)
        metrics.record_turn_metrics(
            {
                "intent": "customer_analysis",
                "react_last_error": "已超过本轮分析次数上限",
                "react_pending_decision": {"action": "final", "insufficient_information": True},
            }
        )
        self.assertTrue(self.records[1][metrics.KEY_CAPPED])
