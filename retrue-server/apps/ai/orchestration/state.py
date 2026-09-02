"""编排图的安全状态定义与任务状态序列化。

图状态（``OrchestrationState``）只保存编排所需的最小引用信息，绝不保存
原始对话正文、手机号、完整健康信息、完整工具输出或提示词。需要持久化的
字段通过白名单与 ``AssistantTask.state_data`` 互转；其他运行时字段（如
单轮用户输入摘要）只在本次 ``invoke`` 内存中存在，不进入数据库或 checkpoint。

字段白名单与 ``apps.assistant_tasks.services._validate_state_data`` 的
``FORBIDDEN_STATE_KEYS`` 形成双重防线：即使这里遗漏了某个敏感字段，
任务服务层也会在写入 ``state_data`` 时拒绝。
"""

from __future__ import annotations

from typing import Any, TypedDict


class OrchestrationState(TypedDict, total=False):
    """LangGraph 编排图的安全状态。

    字段说明：
        assistant_task_id: 统一助手任务主键，业务恢复的权威来源。
        conversation_id: 会话主键，原始对话仍保存在 Conversation 表。
        customer_id: 已确认客户主键；未确认时为 None。
        intent: 已识别的意图代码（如 general_knowledge、customer_question）。
        next_node: 中断时下一步应进入的节点名，用于恢复。
        missing_fields: 待补充字段，如 ["customer_id"]。
        resource_refs: 草稿/结果等业务资源的引用，形如 {"draft_id": 12}。
        tool_result_refs: 已执行 Tool 的日志引用，形如 ["tool_execution:81"]。
        step_count: 本轮已执行节点次数，用于节点次数上限（仅内存）。
        tool_call_count: 本轮已执行只读 Tool 次数（仅内存）。
        user_input: 单轮用户输入（仅内存，绝不持久化）。
        customer_name: 从输入识别的客户姓名提示（仅内存）。
        required_tools: 本分支待执行的只读 Tool 名称列表（仅内存）。
        needs_confirmation: 是否需要康复师确认（仅内存）。
        customer_candidates: 同名客户候选（仅内存，不持久化）。
        reply_content: 本轮生成的回复文本（仅内存，绝不持久化）。
        assistant_message_id: 写入会话的 assistant 消息主键（仅内存）。
        tool_contexts: 只读 Tool 结果的脱敏上下文，仅用于本轮生成回复（仅内存）。
        tool_signatures: 本轮已执行的「工具名+参数摘要」签名集合，用于去重（仅内存）。
        risk_notice: 风险分支的人工核查提醒文案（仅内存）。
        customer_summary: 客户信息摘要（脱敏，仅内存），供客户信息摘要卡片渲染。
    """

    assistant_task_id: int
    conversation_id: int | None
    customer_id: int | None
    intent: str
    next_node: str
    missing_fields: list[str]
    resource_refs: dict[str, int | None]
    tool_result_refs: list[str]
    step_count: int
    tool_call_count: int
    user_input: str
    customer_name: str
    required_tools: list[str]
    needs_confirmation: bool
    customer_candidates: list[dict[str, Any]]
    reply_content: str
    assistant_message_id: int | None
    tool_contexts: list[dict[str, Any]]
    tool_signatures: list[str]
    risk_notice: str
    customer_summary: dict[str, Any] | None


# 允许写入 AssistantTask.state_data 的字段白名单。其余运行时字段一律排除。
PERSISTED_STATE_KEYS = frozenset(
    {
        "assistant_task_id",
        "conversation_id",
        "customer_id",
        "intent",
        "next_node",
        "missing_fields",
        "resource_refs",
        "tool_result_refs",
    }
)


def build_initial_state(
    *,
    assistant_task_id: int,
    conversation_id: int | None = None,
    customer_id: int | None = None,
    intent: str = "",
    next_node: str = "",
) -> OrchestrationState:
    """构建一轮图执行的初始安全状态。"""
    return OrchestrationState(
        assistant_task_id=assistant_task_id,
        conversation_id=conversation_id,
        customer_id=customer_id,
        intent=intent,
        next_node=next_node,
        missing_fields=[],
        resource_refs={},
        tool_result_refs=[],
        step_count=0,
        tool_call_count=0,
        user_input="",
        customer_name="",
        required_tools=[],
        needs_confirmation=False,
        customer_candidates=[],
        reply_content="",
        assistant_message_id=None,
        tool_contexts=[],
        tool_signatures=[],
        risk_notice="",
        customer_summary=None,
    )


def serialize_state(state: OrchestrationState) -> dict[str, Any]:
    """把图状态精简为可持久化白名单，供写入 AssistantTask.state_data。

    只保留 ``PERSISTED_STATE_KEYS`` 中的字段；任何不在白名单内的字段
    （包括 user_input、step_count 等运行时值）都不会被序列化。
    """
    return {key: state[key] for key in PERSISTED_STATE_KEYS if key in state}


def restore_state_from_task(state_data: dict[str, Any] | None) -> OrchestrationState:
    """从 AssistantTask.state_data 恢复图状态，缺失字段使用安全默认值。

    恢复时只读取白名单字段，忽略任务状态中可能存在的任何额外或未知键，
    避免把历史脏数据带入图执行。
    """
    data = state_data if isinstance(state_data, dict) else {}
    return OrchestrationState(
        assistant_task_id=data.get("assistant_task_id", 0),
        conversation_id=data.get("conversation_id"),
        customer_id=data.get("customer_id"),
        intent=str(data.get("intent") or ""),
        next_node=str(data.get("next_node") or ""),
        missing_fields=list(data.get("missing_fields") or []),
        resource_refs=dict(data.get("resource_refs") or {}),
        tool_result_refs=list(data.get("tool_result_refs") or []),
        step_count=0,
        tool_call_count=0,
        user_input="",
        customer_name="",
        required_tools=[],
        needs_confirmation=False,
        customer_candidates=[],
        reply_content="",
        assistant_message_id=None,
        tool_contexts=[],
        tool_signatures=[],
        risk_notice="",
        customer_summary=None,
    )
