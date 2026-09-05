"""将图执行事件转换为固定业务进度，禁止输出图状态、工具参数及模型原文。"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from apps.ai.orchestration.state import OrchestrationState

ProgressSink = Callable[[dict[str, str]], None]
_sink: ContextVar[ProgressSink | None] = ContextVar("assistant_progress_sink", default=None)

# 节点名仅在服务端使用；浏览器只收到固定阶段代码、中文文案和状态。
_STAGES = {
    "classify_intent": ("understand", "正在识别需求"),
    "parse_multi_customer_records": ("split_records", "正在整理多位客户的记录"),
    "customer_lookup": ("match_customer", "正在匹配客户"),
    "ensure_customer": ("match_customer", "正在核对客户身份"),
    "bind_customer": ("bind_customer", "正在关联客户档案"),
    "choose_read_tools": ("prepare_query", "正在准备查询"),
    "prepare_react_tools": ("prepare_query", "正在准备查询"),
    "react_decide": ("analyze", "正在分析资料与查询需求"),
    "execute_read_tools": ("query_records", "正在查询相关记录"),
    "execute_react_tool": ("query_records", "正在查询相关记录"),
    "answer_general": ("compose_reply", "正在整理回复"),
    "answer_with_context": ("compose_reply", "正在整理回复"),
    "react_finalize": ("compose_reply", "正在整理回复"),
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
    for mode, payload in app.stream(dict(state), stream_mode=["tasks", "values"]):
        if mode == "values":
            result = payload
        elif mode == "tasks" and payload.get("name") in _STAGES:
            stage, label = _STAGES[payload["name"]]
            if "input" in payload:
                status = "running"
            elif payload.get("error"):
                status = "failed"
            else:
                status = "completed"
            sink({"stage": stage, "label": label, "status": status})
    return result
