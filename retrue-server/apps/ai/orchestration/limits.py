"""编排图的节点次数与 Tool 调用次数限制。

图执行可能因模型异常或路由配置错误陷入环路。这里提供简单的计数追踪器，
在每次进入节点 / 执行 Tool 时递增计数，超过上限即抛出 ``NodeLimitError``，
由上层转换为任务 ``blocked`` 或降级回答，绝不无限循环。
"""

from __future__ import annotations

from django.conf import settings


class NodeLimitError(RuntimeError):
    """图节点或 Tool 调用次数超过单轮上限。"""

    def __init__(self, message: str, *, error_code: str = "orchestration_limit_exceeded") -> None:
        super().__init__(message)
        self.error_code = error_code


def max_steps() -> int:
    """单轮对话允许的最大图节点执行次数。"""
    return max(int(getattr(settings, "AI_ORCHESTRATION_MAX_STEPS", 8)), 1)


def max_tool_calls() -> int:
    """单轮对话允许的最大只读 Tool 调用次数。"""
    return max(int(getattr(settings, "AI_ORCHESTRATION_MAX_TOOL_CALLS", 3)), 1)


def max_react_decisions() -> int:
    """受控 ReAct 子图单回合允许的最大模型决策（decide）次数。

    与 max_tool_calls 一起形成双保险：即使节点调度异常也不会无限循环。
    """
    return max(int(getattr(settings, "AI_ORCHESTRATION_MAX_REACT_DECISIONS", 3)), 1)


class StepLimitTracker:
    """追踪单轮图执行中的节点步数与 Tool 调用次数。

    追踪器是纯内存对象，只参与本轮 ``invoke``，不写入数据库或 checkpoint。
    """

    def __init__(self, *, max_steps: int | None = None, max_tool_calls: int | None = None) -> None:
        self._max_steps = max_steps if max_steps is not None else max_steps()
        self._max_tool_calls = max_tool_calls if max_tool_calls is not None else max_tool_calls()
        self._steps = 0
        self._tool_calls = 0

    def record_step(self) -> None:
        """记录一次节点执行；超过上限抛出 NodeLimitError。"""
        self._steps += 1
        if self._steps > self._max_steps:
            raise NodeLimitError(
                f"单轮图节点执行次数超过上限 {self._max_steps}",
                error_code="orchestration_step_limit_exceeded",
            )

    def record_tool_call(self) -> None:
        """记录一次只读 Tool 调用；超过上限抛出 NodeLimitError。"""
        self._tool_calls += 1
        if self._tool_calls > self._max_tool_calls:
            raise NodeLimitError(
                f"单轮只读 Tool 调用次数超过上限 {self._max_tool_calls}",
                error_code="orchestration_tool_limit_exceeded",
            )

    @property
    def steps(self) -> int:
        return self._steps

    @property
    def tool_calls(self) -> int:
        return self._tool_calls


class ToolCallLimitTracker(StepLimitTracker):
    """兼容旧命名的别名：单轮只读 Tool 调用次数追踪。"""


__all__ = [
    "NodeLimitError",
    "StepLimitTracker",
    "ToolCallLimitTracker",
    "max_steps",
    "max_tool_calls",
    "max_react_decisions",
]
