"""受控 ReAct 客户分析的质量监控埋点骨架（阶段 C）。

设计说明：
- 阶段 C 的聚合口径需要生产真实数据驱动，因此这里先落「埋点骨架」：定义统一
  的脱敏指标键、一份可插拔的 recorder 协议，并在唯一收口 `record_turn_metrics`
  处计算每回合指标。默认 recorder 以结构化日志输出（不丢数据、便于按日志聚合），
  生产阶段可将 recorder 换成数据库/消息队列实现，无需改动调用方。
- 所有指标均为脱敏计数/布尔：不记录客户 id、姓名、原文、工具参数或任何病史。
- 指标口径：
    tool_calls        本回合实际执行的只读 Tool 次数（0 表示未执行）
    tool_failures     其中失败/被拒的次数
    invalid_decisions 模型输出非法（无法通过 schema 校验）导致的降级次数
    capped            是否触发决策或工具次数上限而强制结束
    intents           该回合命中的客户分析意图分布（按意图计数，仅内部名）
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

# 使用 ``__name__``（即 apps.ai.orchestration.metrics）以便命中 settings LOGGING 中
# 的 ``apps`` 命名空间 logger（INFO 可见）。独立的 ``retrue.assistant_*`` 名会回落
# 到 root 级 WARNING，导致 INFO 指标日志不可见。
logger = logging.getLogger(__name__)

#: 指标键（供 recorder 与测试引用）。
KEY_TOOL_CALLS = "tool_calls"
KEY_TOOL_FAILURES = "tool_failures"
KEY_INVALID_DECISIONS = "invalid_decisions"
KEY_CAPPED = "capped"
KEY_INTENTS = "intents"


class MetricsRecorder(Protocol):
    """质量指标 recorder 协议；生产可实现为写库/推消息队列。"""

    def record(self, metrics: dict[str, Any]) -> None:  # pragma: no cover - protocol
        ...


class LoggingMetricsRecorder:
    """默认 recorder：以脱敏结构化日志输出每回合指标，供按天/按键聚合。"""

    def record(self, metrics: dict[str, Any]) -> None:
        logger.info("assistant_turn_metrics %s", _json_compact(metrics))


def _json_compact(metrics: dict[str, Any]) -> str:
    import json

    return json.dumps(metrics, ensure_ascii=False, sort_keys=True)


#: 当前生效的 recorder。测试可替换为内存 recorder 断言。
#: 生产接线（DB/队列）建议放在 Django ready() 或 settings 装配处。
_recorder: MetricsRecorder | None = None


def set_recorder(recorder: MetricsRecorder | None) -> MetricsRecorder | None:
    """注入自定义 recorder（返回旧值，便于测试还原）。"""
    global _recorder
    old = _recorder
    _recorder = recorder
    return old


def _current_recorder() -> MetricsRecorder:
    if _recorder is not None:
        return _recorder
    return LoggingMetricsRecorder()


def record_turn_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """从回合终态计算并上报脱敏指标，返回本次指标字典。

    ``state`` 为服务层收敛后的最终 state（含 react_* 内存字段）。本函数对任何
    意图都安全：未执行的字段按空处理。调用方在回合收尾（handle_turn /
    resume_task / submit_customer_selection）统一调用一次。
    """
    observations = state.get("react_observations") or []
    tool_failures = sum(1 for item in observations if item.get("error"))
    invalid_decisions = 1 if _invalid_decision(state) else 0
    metrics: dict[str, Any] = {
        KEY_TOOL_CALLS: len(state.get("react_tool_signatures") or []),
        KEY_TOOL_FAILURES: tool_failures,
        KEY_INVALID_DECISIONS: invalid_decisions,
        KEY_CAPPED: _capped(state),
    }
    intent = str(state.get("intent") or "")
    if intent:
        metrics[KEY_INTENTS] = {intent: 1}
    try:
        _current_recorder().record(metrics)
    except Exception:  # noqa: BLE001 - 指标上报失败不应阻断业务
        logger.exception("assistant_metrics_record_failed")
    return metrics


def _invalid_decision(state: dict[str, Any]) -> bool:
    """是否因模型输出非法而安全降级。"""
    error = str(state.get("react_last_error") or "")
    decision = state.get("react_pending_decision") or {}
    return "非法" in error or (decision.get("reason") == "模型输出非法")


def _capped(state: dict[str, Any]) -> bool:
    """是否触发决策或工具次数上限而强制结束。"""
    error = str(state.get("react_last_error") or "")
    decision = state.get("react_pending_decision") or {}
    return ("上限" in error) or (decision.get("action") == "final" and "上限" in error)
