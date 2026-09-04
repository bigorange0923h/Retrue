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
        multi_customer_items: 多客户补记拆分结果（仅内存），仅在当前图运行中
            交给批量任务领域服务创建有序子项，绝不写入任务状态。
        requires_customer_context: 本意图是否需要读取客户目录（仅内存，由
            classify 后判定）。
        customer_directory: 当前康复师最小客户目录（仅内存，绝不持久化）。
        customer_matches: 原文目录匹配结果（仅内存，绝不持久化）。
        preselected_customer_id: 目录精确命中待康复师确认的预选客户主键
            （仅内存，绝不持久化；确认前不作为正式绑定）。
        identity_resolution: 身份解析的最小持久化摘要
            {status: preselected|waiting_selection|unresolved,
             matched_customer_ids: [...], source: "directory_exact"}；
            不含任何姓名原文，恢复时须按目录重算、不信任历史。
        query_goal: 客户分析的查询目标（如 recent_training、customer_profile、
            assessment_progress、attendance_or_course、comprehensive_progress），
            由分类阶段决定（仅内存，绝不持久化）。
        react_iteration: 受控 ReAct 子图当前迭代次数（仅内存，绝不持久化）。
        react_actions: 本轮模型已作出的 Tool 调用决策摘要（仅内存，绝不持久化）。
        react_observations: 已取得的脱敏 Tool 观察结果（仅内存，绝不持久化）。
        react_final_answer: ReAct 子图生成的最终回答（仅内存，绝不持久化）。
        available_react_tools: prepare_react_tools 按 query_goal 注入的本轮可用
            Tool 子集安全描述（仅内存，绝不持久化）。
        react_tool_signatures: 本轮已执行「Tool 名+规范化参数」去重签名（仅内存）。
        react_last_error: 最近一次 Tool 失败的脱敏信息（仅内存，绝不持久化）。
        conversation_context: 从 Conversation 读取的受控跨轮工作上下文（仅内存，
            不含原始对话、病史或 Tool 输出）。用于理解“那近三个月呢”等追问。
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
    multi_customer_items: list[dict[str, Any]]
    requires_customer_context: bool
    customer_directory: list[dict[str, Any]]
    customer_matches: list[dict[str, Any]]
    preselected_customer_id: int | None
    identity_resolution: dict[str, Any]
    query_goal: str
    react_iteration: int
    react_actions: list[dict[str, Any]]
    react_observations: list[dict[str, Any]]
    react_final_answer: str
    available_react_tools: list[dict[str, Any]]
    react_tool_signatures: list[str]
    react_last_error: str
    react_pending_decision: dict[str, Any]
    conversation_context: dict[str, Any]


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
        "identity_resolution",
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
        multi_customer_items=[],
        requires_customer_context=False,
        customer_directory=[],
        customer_matches=[],
        preselected_customer_id=None,
        identity_resolution={},
        query_goal="",
        react_iteration=0,
        react_actions=[],
        react_observations=[],
        react_final_answer="",
        available_react_tools=[],
        react_tool_signatures=[],
        react_last_error="",
        react_pending_decision={},
        conversation_context={},
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
        multi_customer_items=[],
        requires_customer_context=False,
        customer_directory=[],
        customer_matches=[],
        preselected_customer_id=None,
        identity_resolution=dict(data.get("identity_resolution") or {}),
        query_goal="",
        react_iteration=0,
        react_actions=[],
        react_observations=[],
        react_final_answer="",
        available_react_tools=[],
        react_tool_signatures=[],
        react_last_error="",
        react_pending_decision={},
        conversation_context={},
    )
