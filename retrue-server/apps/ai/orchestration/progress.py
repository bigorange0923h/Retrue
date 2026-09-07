"""将图执行事件转换为固定业务进度，禁止输出图状态、工具参数及模型原文。"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from apps.ai.orchestration.state import OrchestrationState

ProgressSink = Callable[[dict[str, str]], None]
_sink: ContextVar[ProgressSink | None] = ContextVar("assistant_progress_sink", default=None)

# 节点名仅在服务端使用；浏览器只收到固定阶段代码、中文文案和状态。
_STAGES = {
    "classify_intent": ("understand", "正在理解您的问题"),
    "parse_multi_customer_records": ("split_records", "正在整理多位客户的记录"),
    "customer_lookup": ("match_customer", "正在匹配客户"),
    "ensure_customer": ("match_customer", "正在核对客户身份"),
    "bind_customer": ("bind_customer", "正在关联客户档案"),
    "choose_read_tools": ("prepare_query", "正在确定需要查询的资料"),
    "prepare_react_tools": ("prepare_query", "正在准备可查询的资料"),
    "react_decide": ("analyze", "正在判断需要查询哪些记录"),
    "execute_read_tools": ("query_records", "正在查询相关记录"),
    "execute_react_tool": ("query_records", "正在查询康复记录"),
    "answer_general": ("compose_reply", "正在生成回复"),
    "answer_with_context": ("compose_reply", "正在生成查询结论"),
    "react_finalize": ("compose_reply", "正在生成分析结论"),
    "create_training_draft": ("prepare_draft", "正在生成训练草稿"),
    "create_domain_draft": ("prepare_draft", "正在生成待确认草稿"),
    "risk_review": ("review_risk", "正在核查风险提示"),
}


@contextmanager
def report_progress(sink: ProgressSink) -> Iterator[None]:
    """仅在当前执行上下文注册进度接收器，退出时恢复，防止并发请求串流。"""
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def invoke_with_progress(app: Any, state: OrchestrationState) -> OrchestrationState:
    """执行同一张图；订阅时消费真实任务事件，最终状态仍由原服务持久化。"""
    sink = _sink.get()
    if sink is None:
        return app.invoke(dict(state))
    result = dict(state)
    react_decisions = 0
    for mode, payload in app.stream(dict(state), stream_mode=["tasks", "values"]):
        if mode == "values":
            result = payload
        elif mode == "tasks" and payload.get("name") in _STAGES:
            stage, label = _STAGES[payload["name"]]
            # ReAct 会在查询前决定要读什么、在查询后核对结果；两次都是同一
            # 节点，但应向用户说明不同的真实业务动作。
            if payload["name"] == "react_decide":
                if "input" in payload:
                    react_decisions += 1
                if react_decisions > 1:
                    label = "正在核对查询结果"
            if "input" in payload:
                status = "running"
            elif payload.get("error"):
                status = "failed"
            else:
                status = "completed"
            sink({"stage": stage, "label": label, "status": status})
    return result
