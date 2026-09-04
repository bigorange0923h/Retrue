"""编排执行路径追踪日志（脱敏、结构化）。

用于回答「这次回合 AI 选了哪一步、走了哪条分支、判定了什么」：在图节点、
路由与判定点的每个关键步骤输出统一前缀的结构化日志，便于按 task 还原一次
回合的执行路径。

约定与边界：
- 只记录内部判定码、节点名、分支名与脱敏计数；绝不记录客户姓名、手机号、
  病史、聊天原文、完整工具输出或提示词。判定字段由调用方确保已脱敏。
- 与 ``metrics`` 的区别：metrics 是回合级聚合指标（收口一次）；本模块是
  执行路径级追踪，随图推进逐条输出，用于定位/还原某一轮走了哪条分支。
- 追踪失败不影响业务：内部捕获异常，仅在最坏情况下丢一条追踪。

用法（节点 / 路由 / 服务层内）：
    trace_event(state, "node.enter", node="classify_intent")
    trace_event(state, "route.choice", branch="general_knowledge", reason="intent")
    trace_event(state, "decision.react", action="tool_call", tool_name="...", iteration=1)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

# 使用 ``__name__``（即 apps.ai.orchestration.trace）以便命中 settings LOGGING 中
# 的 ``apps`` 命名空间 logger（INFO 可见）。若用独立的 ``retrue.assistant_*`` 名，
# 会回落到 root 级 WARNING，导致 INFO 追踪日志不可见。
logger = logging.getLogger(__name__)


class TraceRecorder(Protocol):
    """执行路径追踪 recorder 协议；测试可注入内存 recorder 断言。"""

    def record(self, event: dict[str, Any]) -> None:  # pragma: no cover - protocol
        ...


class LoggingTraceRecorder:
    """默认 recorder：以脱敏结构化日志输出每步追踪。"""

    def record(self, event: dict[str, Any]) -> None:
        logger.info("assistant_trace %s", _json_compact(event))


def _json_compact(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)


#: 当前生效的 tracer。测试可替换为内存 tracer 断言。
_recorder: TraceRecorder | None = None


def set_recorder(recorder: TraceRecorder | None) -> TraceRecorder | None:
    """注入自定义 tracer（返回旧值，便于测试还原）。"""
    global _recorder
    old = _recorder
    _recorder = recorder
    return old


def _current_recorder() -> TraceRecorder:
    if _recorder is not None:
        return _recorder
    return LoggingTraceRecorder()


def trace_event(state: dict[str, Any] | None, event: str, **fields: Any) -> None:
    """输出一次执行路径追踪。

    参数：
        state: 当前图状态（取其 assistant_task_id / conversation_id 作为上下文）。
        event: 事件类型，形如 ``node.enter`` / ``route.choice`` / ``decision.react``。
        fields: 已脱敏的判定字段；只允许基本类型与可控结构。
    """
    payload: dict[str, Any] = {"event": event}
    if state:
        task_id = state.get("assistant_task_id")
        if task_id:
            payload["task"] = task_id
    payload.update(fields)
    try:
        _current_recorder().record(payload)
    except Exception:  # noqa: BLE001 - 追踪失败不应阻断业务
        logger.exception("assistant_trace_failed event=%s", event)
