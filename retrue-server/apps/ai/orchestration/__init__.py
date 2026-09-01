"""LangGraph 多分支 AI 助理编排。

本包只负责对话流程编排：意图识别、分支路由、Tool 调用顺序与等待节点。
权限校验、任务状态迁移、正式业务写入和审计仍由 ``apps.assistant_tasks``、
``apps.ai`` 等领域服务统一负责。图状态只保存任务、会话、客户、意图、
下一步与必要引用 ID，不保存完整聊天记录、手机号、原始敏感资料、
完整工具输出或提示词。
"""

from apps.ai.orchestration.state import (
    OrchestrationState,
    build_initial_state,
    restore_state_from_task,
    serialize_state,
)
from apps.ai.orchestration.graph import (
    build_graph,
    compile_graph,
    invoke_empty_graph,
    resume_from_state,
)
from apps.ai.orchestration.intent import IntentResult, classify_intent
from apps.ai.orchestration.limits import (
    NodeLimitError,
    StepLimitTracker,
    ToolCallLimitTracker,
)
from apps.ai.orchestration.adapter import sync_node_event, sync_state
from apps.ai.orchestration.service import (
    OrchestrationDisabledError,
    handle_turn,
    resume_task,
    submit_customer_selection,
)

__all__ = [
    "OrchestrationState",
    "build_initial_state",
    "restore_state_from_task",
    "serialize_state",
    "build_graph",
    "compile_graph",
    "invoke_empty_graph",
    "resume_from_state",
    "IntentResult",
    "classify_intent",
    "NodeLimitError",
    "StepLimitTracker",
    "ToolCallLimitTracker",
    "sync_node_event",
    "sync_state",
    "handle_turn",
    "resume_task",
    "submit_customer_selection",
    "OrchestrationDisabledError",
]
