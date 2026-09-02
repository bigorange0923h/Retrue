"""LangGraph 编排图构建。

图只负责流程编排：意图识别、分支路由、Tool 调用顺序与等待节点。权限、
任务状态迁移、正式业务写入和审计仍由 Django 领域服务负责。

节点拓扑（见执行计划第 3 节）：
    receive_turn -> classify_intent
      ├─ general_knowledge -> answer_general -> END
      ├─ customer_lookup  -> customer_lookup_node
      │     ├─ no_match        -> wait_customer_name -> END
      │     ├─ one_match       -> bind_customer -> END
      │     └─ multiple_matches-> wait_customer_selection -> END
      ├─ customer_question -> choose_read_tools -> execute_read_tools
      │     -> answer_with_context -> END
      ├─ training_record   -> ensure_customer
      │     ├─ unresolved -> wait_customer_selection -> END
      │     └─ resolved   -> create_training_draft -> wait_draft_confirmation -> END
      ├─ assessment / training_revision / followup -> ensure_customer
      │     ├─ unresolved -> wait_customer_selection -> END
      │     └─ resolved   -> create_domain_draft -> wait_draft_confirmation -> END
      └─ risk_review      -> risk_review_node -> END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from apps.ai.orchestration import nodes
from apps.ai.orchestration.state import OrchestrationState, build_initial_state


def invoke_empty_graph(**context: object) -> OrchestrationState:
    """运行一次编排图（兼容阶段 1 命名），返回最终安全状态。"""
    state = build_initial_state(assistant_task_id=context.get("assistant_task_id", 0))
    for key in ("conversation_id", "customer_id", "intent"):
        if key in context:
            state[key] = context[key]  # type: ignore[literal-required]
    return compile_graph().invoke(dict(state))


def resume_from_state(state: OrchestrationState) -> OrchestrationState:
    """从已恢复的安全状态继续执行图（兼容阶段 1 命名）。"""
    return compile_graph().invoke(dict(state))


def _route_after_receive(state: OrchestrationState) -> str:
    """入口路由：首轮进入分类；恢复场景按已持久化意图继续。"""
    next_node = state.get("next_node") or ""
    if next_node == "classify_intent":
        return "classify_intent"
    intent = state.get("intent") or ""
    if intent:
        return _route_after_intent(state)
    return "classify_intent"


def _route_after_intent(state: OrchestrationState) -> str:
    """按意图路由到对应分支。"""
    intent = state.get("intent") or "general_knowledge"
    return {
        "general_knowledge": "answer_general",
        "customer_lookup": "customer_lookup",
        "customer_question": "choose_read_tools",
        "training_record": "ensure_customer",
        "assessment": "ensure_customer",
        "training_revision": "ensure_customer",
        "followup": "ensure_customer",
        "risk_review": "risk_review",
    }.get(intent, "answer_general")


def _route_after_lookup(state: OrchestrationState) -> str:
    """按同名客户查询结果路由。"""
    return state.get("next_node") or "wait_customer_name"


def _route_after_ensure_customer(state: OrchestrationState) -> str:
    """客户未绑定则等待选择；已绑定则按意图选择草稿节点。"""
    if state.get("customer_id") is None:
        return "wait_customer_selection"
    intent = state.get("intent") or "training_record"
    if intent == "training_record":
        return "create_training_draft"
    return "create_domain_draft"


def build_graph() -> StateGraph:
    """构建完整的多分支编排图。"""
    graph = StateGraph(OrchestrationState)

    graph.add_node("receive_turn", nodes.receive_turn_node)
    graph.add_node("classify_intent", nodes.classify_intent_node)
    graph.add_node("answer_general", nodes.answer_general_node)
    graph.add_node("customer_lookup", nodes.customer_lookup_node)
    graph.add_node("bind_customer", nodes.bind_customer_node)
    graph.add_node("wait_customer_name", nodes.wait_customer_name_node)
    graph.add_node("wait_customer_selection", nodes.wait_customer_selection_node)
    graph.add_node("choose_read_tools", nodes.choose_read_tools_node)
    graph.add_node("execute_read_tools", nodes.execute_read_tools_node)
    graph.add_node("answer_with_context", nodes.answer_with_context_node)
    graph.add_node("ensure_customer", nodes.ensure_customer_node)
    graph.add_node("create_training_draft", nodes.create_training_draft_node)
    graph.add_node("create_domain_draft", nodes.create_domain_draft_node)
    graph.add_node("wait_draft_confirmation", nodes.wait_draft_confirmation_node)
    graph.add_node("risk_review", nodes.risk_review_node)

    graph.add_edge(START, "receive_turn")
    graph.add_conditional_edges(
        "receive_turn",
        _route_after_receive,
        {
            "classify_intent": "classify_intent",
            "answer_general": "answer_general",
            "customer_lookup": "customer_lookup",
            "choose_read_tools": "choose_read_tools",
            "ensure_customer": "ensure_customer",
            "risk_review": "risk_review",
        },
    )
    graph.add_conditional_edges(
        "classify_intent",
        _route_after_intent,
        {
            "answer_general": "answer_general",
            "customer_lookup": "customer_lookup",
            "choose_read_tools": "choose_read_tools",
            "ensure_customer": "ensure_customer",
            "risk_review": "risk_review",
        },
    )

    graph.add_edge("answer_general", END)

    graph.add_conditional_edges(
        "customer_lookup",
        _route_after_lookup,
        {
            "wait_customer_name": "wait_customer_name",
            "bind_customer": "bind_customer",
            "wait_customer_selection": "wait_customer_selection",
        },
    )
    graph.add_edge("bind_customer", END)
    graph.add_edge("wait_customer_name", END)
    graph.add_edge("wait_customer_selection", END)

    graph.add_edge("choose_read_tools", "execute_read_tools")
    graph.add_edge("execute_read_tools", "answer_with_context")
    graph.add_edge("answer_with_context", END)

    graph.add_conditional_edges(
        "ensure_customer",
        _route_after_ensure_customer,
        {
            "wait_customer_selection": "wait_customer_selection",
            "create_training_draft": "create_training_draft",
            "create_domain_draft": "create_domain_draft",
        },
    )
    graph.add_edge("create_training_draft", "wait_draft_confirmation")
    graph.add_edge("create_domain_draft", "wait_draft_confirmation")
    graph.add_edge("wait_draft_confirmation", END)

    graph.add_edge("risk_review", END)
    return graph


def compile_graph(graph: StateGraph | None = None):
    """编译 StateGraph 为可 invoke 的应用。"""
    return (graph or build_graph()).compile()


__all__ = ["build_graph", "compile_graph", "invoke_empty_graph", "resume_from_state"]
