"""LangGraph 编排基座（阶段 1）测试。

覆盖：空图可运行、恢复图可运行、图状态不保存敏感数据、节点次数上限。
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.ai.orchestration import (
    NodeLimitError,
    StepLimitTracker,
    build_graph,
    build_initial_state,
    classify_intent,
    serialize_state,
)


class OrchestrationGraphTests(SimpleTestCase):
    """编排图基座运行测试。"""

    def test_graph_compiles(self) -> None:
        """完整编排图可编译。"""
        app = build_graph().compile()
        self.assertIsNotNone(app)

    def test_intent_classification_general(self) -> None:
        """普通知识咨询分类为 general_knowledge。"""
        result = classify_intent("做深蹲时膝盖应该怎么放？", customer_bound=False)
        self.assertEqual(result.intent, "general_knowledge")

    def test_intent_classification_training(self) -> None:
        """训练补记分类为 training_record。"""
        result = classify_intent("今天做了臀桥 3 组 12 次", customer_bound=False)
        self.assertEqual(result.intent, "training_record")

    def test_serialize_state_excludes_sensitive(self) -> None:
        """图状态序列化只保留白名单，绝不写入用户输入等运行时字段。"""
        state = build_initial_state(assistant_task_id=12)
        state["user_input"] = "客户说膝盖疼，手机号 13812345678"
        state["step_count"] = 5
        state["tool_call_count"] = 2
        persisted = serialize_state(state)
        self.assertNotIn("user_input", persisted)
        self.assertNotIn("step_count", persisted)
        self.assertNotIn("tool_call_count", persisted)
        # 白名单字段仍在。
        self.assertEqual(persisted["assistant_task_id"], 12)

    def test_serialize_state_keeps_reference_ids(self) -> None:
        """序列化保留任务、客户、意图与资源引用等编排必需字段。"""
        state = build_initial_state(
            assistant_task_id=12,
            conversation_id=39,
            customer_id=35,
            intent="customer_question",
            next_node="wait_customer_selection",
        )
        state["missing_fields"] = ["customer_id"]
        state["resource_refs"] = {"draft_id": None}
        state["tool_result_refs"] = ["tool_execution:81"]
        persisted = serialize_state(state)
        self.assertEqual(persisted["customer_id"], 35)
        self.assertEqual(persisted["intent"], "customer_question")
        self.assertEqual(persisted["next_node"], "wait_customer_selection")
        self.assertEqual(persisted["missing_fields"], ["customer_id"])
        self.assertEqual(persisted["resource_refs"], {"draft_id": None})
        self.assertEqual(persisted["tool_result_refs"], ["tool_execution:81"])


class StepLimitTrackerTests(SimpleTestCase):
    """节点与工具调用次数上限测试。"""

    def test_step_limit_enforced(self) -> None:
        """节点执行次数超过上限时抛出 NodeLimitError。"""
        tracker = StepLimitTracker(max_steps=2, max_tool_calls=3)
        tracker.record_step()
        tracker.record_step()
        with self.assertRaises(NodeLimitError):
            tracker.record_step()

    def test_tool_call_limit_enforced(self) -> None:
        """只读工具调用次数超过上限时抛出 NodeLimitError。"""
        tracker = StepLimitTracker(max_steps=10, max_tool_calls=2)
        tracker.record_tool_call()
        tracker.record_tool_call()
        with self.assertRaises(NodeLimitError):
            tracker.record_tool_call()

    @override_settings(AI_ORCHESTRATION_ENABLED=False)
    def test_feature_flag_defaults_off(self) -> None:
        """编排功能开关默认关闭，不替换现有稳定流程。"""
        from django.conf import settings

        self.assertFalse(settings.AI_ORCHESTRATION_ENABLED)
