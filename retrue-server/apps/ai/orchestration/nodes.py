"""编排图节点实现。

节点只通过 ``OrchestrationState`` 交换编排事实，不直接持有 therapist 或
任务对象。需要访问领域数据时，通过 ``assistant_task_id`` 从数据库恢复任务，
再由 ``task.therapist_id`` 派生可信身份；绝不接收客户端提供的 therapist_id。

真实 AI 回复由节点调用 provider 生成并写入 Conversation；回复正文只放在
``state.reply_content``（仅内存）中返回给 API，绝不写入任务状态或 checkpoint。

每个节点返回对 state 的增量更新（dict），图负责合并。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from apps.ai.orchestration.intent import classify_intent
from apps.ai.orchestration.limits import (
    NodeLimitError,
    max_react_decisions,
    max_steps,
    max_tool_calls,
)
from apps.ai.orchestration.state import OrchestrationState
from apps.ai.orchestration.trace import trace_event


def _bump_step(state: OrchestrationState) -> None:
    """节点入口自增步数并检查上限。"""
    current = int(state.get("step_count") or 0) + 1
    if current > max_steps():
        raise NodeLimitError(
            f"单轮图节点执行次数超过上限 {max_steps()}",
            error_code="orchestration_step_limit_exceeded",
        )
    state["step_count"] = current


def _task_from_state(state: OrchestrationState):
    """从状态恢复任务（可信身份来源）。"""
    from apps.assistant_tasks.models import AssistantTask

    task_id = state.get("assistant_task_id")
    if not task_id:
        raise NodeLimitError("缺少任务上下文", error_code="task_missing")
    task = AssistantTask.objects.filter(pk=task_id).first()
    if task is None:
        raise NodeLimitError("任务不存在", error_code="task_not_found")
    return task


def _save_assistant_message(conversation_id: int | None, content: str) -> int | None:
    """把生成的回复写入会话（不可变消息），返回消息主键。

    会话是对话记录，不是正式业务数据；写入仅发生在编排生成回复后。
    """
    if not conversation_id or not content:
        return None
    from apps.conversations.models import Message, MessageRole

    message = Message.objects.create(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=content,
    )
    return message.id


def _chat(system: str, prompt: str) -> str:
    """通过 provider 生成回复，失败时抛出，由上层做安全降级。"""
    from apps.ai.providers.factory import get_provider

    return get_provider().chat(prompt, system=system)


def receive_turn_node(state: OrchestrationState) -> dict:
    """回合入口：首轮进入分类；恢复场景保持原 next_node 以便按暂停节点路由。"""
    _bump_step(state)
    # 恢复场景（state_data 已含 intent 且 next_node 非空）不重新分类，
    # 由 service 层按 next_node 定向继续，图不再按 intent 重跑。
    if state.get("intent") and state.get("next_node"):
        trace_event(state, "node.enter", node="receive_turn", mode="resume")
        return {}
    trace_event(state, "node.enter", node="receive_turn", mode="new_turn")
    return {"next_node": "classify_intent"}


def classify_intent_node(state: OrchestrationState) -> dict:
    """意图与风险初筛节点：安全规则后统一由结构化模型理解自然语言。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="classify_intent")
    result = classify_intent(
        state.get("user_input", ""),
        customer_bound=state.get("customer_id") is not None,
        customer_name=state.get("customer_name", ""),
        conversation_context=state.get("conversation_context") or {},
        use_model=True,
    )
    trace_event(
        state,
        "decision.classify",
        intent=result.intent,
        confidence=result.confidence,
        query_goal=result.query_goal or "",
        needs_confirmation=result.needs_confirmation,
        requires_customer_context=result.requires_customer_context,
    )
    return {
        "intent": result.intent,
        "needs_confirmation": result.needs_confirmation,
        "customer_name": result.customer_name,
        "required_tools": result.required_tools or [],
        "query_goal": result.query_goal,
        "requires_customer_context": result.requires_customer_context,
        "missing_fields": result.missing_slots or [],
    }


def parse_multi_customer_records_node(state: OrchestrationState) -> dict:
    """在图内拆分多客户训练描述，保留原文出现顺序。

    本节点只产生当前运行所需的结构化子项；正式的批量子项仍由训练领域服务
    创建并持久化。这样姓名解析、计划拆分均属于 LangGraph 编排流程，而非
    由 view 或普通 service 绕过图直接调用模型。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="parse_multi_customer_records")
    from apps.ai.providers.factory import get_provider
    from apps.ai.schemas.multi_customer import MultiCustomerTrainingSplit

    raw = get_provider().parse_multi_customer_text(state.get("user_input", ""))
    parsed = MultiCustomerTrainingSplit(**raw)
    if not parsed.items:
        trace_event(state, "decision.multi_customer", outcome="parse_failed", item_count=0)
        raise NodeLimitError("未能识别出客户训练记录", error_code="multi_customer_parse_failed")
    trace_event(state, "decision.multi_customer", outcome="parsed", item_count=len(parsed.items))
    return {
        "multi_customer_items": [item.model_dump() for item in parsed.items],
        "next_node": "create_multi_customer_batch",
    }


def answer_general_node(state: OrchestrationState) -> dict:
    """通用知识咨询直接回答，不读客户数据。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="answer_general", intent=state.get("intent", ""))
    from apps.ai.prompts.loader import load_prompt

    try:
        reply = _chat(load_prompt("general_answer_system"), state.get("user_input", ""))
    except Exception:  # noqa: BLE001 - 模型失败降级为固定提示，不伪造内容
        reply = "抱歉，暂时无法生成回答，请稍后重试。"
    message_id = _save_assistant_message(state.get("conversation_id"), reply)
    return {
        "next_node": "answer_general",
        "reply_content": reply,
        "assistant_message_id": message_id,
    }


def customer_lookup_node(state: OrchestrationState) -> dict:
    """未绑定客户咨询：用当前康复师目录对原文做确定性匹配。

    exact 且唯一 -> 绑定该客户并继续（bind_customer，之后才允许读取其只读数据）。
    ambiguous/多候选 -> wait_customer_selection 展示候选，绝不自动绑定。
    unmatched/无姓名 -> wait_customer_name 请康复师补充或主动搜索。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="customer_lookup")
    task = _task_from_state(state)
    from apps.customers.catalog import resolve_customers_from_text

    raw_text = state.get("user_input", "") or _latest_user_message(task)
    result = resolve_customers_from_text(task.therapist, raw_text)
    if result.is_ambiguous:
        trace_event(
            state,
            "decision.customer_lookup",
            outcome="ambiguous",
            candidate_count=len(result.candidates),
        )
        candidates = [
            _directory_candidate(task.therapist, c.customer_id)
            for c in result.candidates
            if c.customer_id is not None
        ]
        return {
            "next_node": "wait_customer_selection",
            "missing_fields": ["customer_id"],
            "customer_candidates": candidates,
            "preselected_customer_id": None,
            "identity_resolution": {
                "status": "waiting_selection",
                "matched_customer_ids": [c.customer_id for c in result.candidates if c.customer_id],
                "source": "directory_ambiguous",
            },
        }
    if result.is_unmatched:
        trace_event(state, "decision.customer_lookup", outcome="unmatched", candidate_count=0)
        return {
            "next_node": "wait_customer_name",
            "missing_fields": ["customer_name"],
            "preselected_customer_id": None,
            "identity_resolution": {"status": "unresolved", "matched_customer_ids": [], "source": "directory_unmatched"},
        }
    # exact：唯一命中，绑定后由 bind_customer 完成归属并允许只读读取。
    trace_event(state, "decision.customer_lookup", outcome="exact", candidate_count=1)
    return {
        "customer_id": result.customer_id,
        "preselected_customer_id": result.customer_id,
        "identity_resolution": {
            "status": "preselected",
            "matched_customer_ids": [result.customer_id],
            "source": "directory_exact",
        },
        "next_node": "bind_customer",
    }


def bind_customer_node(state: OrchestrationState) -> dict:
    """绑定已唯一确定的客户。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="bind_customer", customer_id=state.get("customer_id"))
    return {"next_node": "bound"}


def choose_read_tools_node(state: OrchestrationState) -> dict:
    """根据客户问题选择只读 Tool（首期固定为上下文查询）。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="choose_read_tools")
    return {"required_tools": ["get_customer_context"], "next_node": "execute_read_tools"}


def _tool_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    """生成工具调用的去重签名，不保存参数原文（仅哈希）。"""
    canonical = hashlib.sha256(repr(sorted(arguments.items())).encode("utf-8")).hexdigest()[:16]
    return f"{tool_name}:{canonical}"


def execute_read_tools_node(state: OrchestrationState) -> dict:
    """执行选定的只读 Tool，落实单轮上限、去重、有限重试与失败降级。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="execute_read_tools")
    task = _task_from_state(state)
    from apps.assistant_tasks import tools
    from apps.assistant_tasks.services import TaskBusinessError

    tool_contexts: list[dict[str, Any]] = []
    tool_refs: list[str] = []
    signatures: list[str] = list(state.get("tool_signatures") or [])

    for tool_name in state.get("required_tools", []):
        if len(tool_refs) >= max_tool_calls():
            trace_event(state, "limit.tool_calls_reached", node="execute_read_tools")
            break
        arguments = {"customer_id": state.get("customer_id")}
        signature = _tool_signature(tool_name, arguments)
        if signature in signatures:
            # 同一 Run 中相同 Tool + 相同参数组合只执行一次。
            continue
        signatures.append(signature)

        result = None
        last_error: Exception | None = None
        # 最多尝试 2 次（首次 + 1 次重试）。
        for _attempt in range(2):
            try:
                result = tools.execute_tool(task, tool_name, arguments)
                break
            except (TaskBusinessError, tools.ToolBusinessError) as exc:
                last_error = exc
            except Exception as exc:  # noqa: BLE001 - 未知错误也安全降级
                last_error = exc
                break

        if result is not None:
            trace_event(state, "decision.tool_ok", node="execute_read_tools", tool=tool_name)
            tool_refs.append(f"tool_execution:{result.tool_execution.id}")
            tool_contexts.append({"tool": tool_name, "result": dict(result)})
        else:
            # 失败后记录失败并安全降级，不伪造客户历史。
            trace_event(
                state,
                "decision.tool_failed",
                node="execute_read_tools",
                tool=tool_name,
                error=_safe_error(last_error),
            )
            tool_refs.append(f"tool_failed:{tool_name}")
            tool_contexts.append({"tool": tool_name, "error": _safe_error(last_error)})

    return {
        "tool_result_refs": tool_refs,
        "tool_signatures": signatures,
        "tool_contexts": tool_contexts,
        "next_node": "answer_with_context",
    }


def _safe_error(exc: Exception | None) -> str:
    """把异常压缩为不可推断业务细节的短消息。"""
    if exc is None:
        return "查询失败"
    text = str(exc)
    return text[:120] if text else "查询失败"


# =====================================================================
# 受控 ReAct 客户查询子图（customer_analysis）
#
# 只读客户分析被建模为有限、可审计的 ReAct 查询子图：根据已经获得的事实，
# 由模型决定是否需要继续调用「服务端已注入的只读 Tool 子集」。模型绝不
# 能提交 customer_id / therapist_id 等归属字段，也绝不能调用写 Tool。
#
# 安全终止条件：
#   - 单回合最多 max_react_decisions() 次模型决策；
#   - 单个回合相同 Tool + 相同规范化参数只执行一次；
#   - Tool 失败、达到上限或模型输出非法时转入安全降级回答。
# =====================================================================

#: 查询目标 -> 允许的只读 Tool 名称（必须全部来自服务端只读注册表）。
#: 未列入的目标不开放任何 Tool，模型只能给出最终回答。
_QUERY_GOAL_TOOLS: dict[str, tuple[str, ...]] = {
    "customer_profile": ("get_customer_context",),
    "recent_training": ("list_recent_training_records",),
    "assessment_progress": ("get_initial_assessment_status",),
    "attendance_or_course": ("list_customer_course_sessions",),
    "comprehensive_progress": (
        "get_customer_context",
        "list_recent_training_records",
        "get_initial_assessment_status",
        "list_customer_course_sessions",
    ),
}

#: 模型不得提交的越权/归属字段，一律由服务端注入。
_FORBIDDEN_REACT_ARGUMENT_FIELDS = frozenset({"customer_id", "therapist_id", "task_id"})


def _react_allowed_tool_names(goal: str, allowlist: frozenset[str]) -> list[str]:
    """按查询目标返回本轮允许的只读 Tool 名称（且必须是服务端白名单）。"""
    candidate = _QUERY_GOAL_TOOLS.get(goal or "")
    if not candidate:
        return []
    return [name for name in candidate if name in allowlist]


def _safe_tool_descriptions(tool_names: list[str]) -> list[dict[str, Any]]:
    """从服务端 list_tool_definitions() 取出本轮 Tool 的安全描述，不暴露 handler。"""
    from apps.assistant_tasks.tools import list_tool_definitions

    by_name = {item["name"]: item for item in list_tool_definitions()}
    return [by_name[name] for name in tool_names if name in by_name]


def prepare_react_tools_node(state: OrchestrationState) -> dict:
    """按查询目标把服务端只读 Tool 子集注入本轮状态，并重置 ReAct 循环。

    只有客户已唯一确定（路由保证）后才进入本节点；可用 Tool 清单来自服务端
    ``list_tool_definitions()`` 的安全描述，绝不从提示词、前端或模型输出构建。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="prepare_react_tools", query_goal=state.get("query_goal", ""))
    from apps.assistant_tasks import tools as task_tools

    goal = state.get("query_goal") or "comprehensive_progress"
    allow_names = _react_allowed_tool_names(goal, task_tools.READ_ONLY_TOOL_ALLOWLIST)
    trace_event(state, "decision.tool_scope", query_goal=goal, tools=allow_names)
    return {
        "available_react_tools": _safe_tool_descriptions(allow_names),
        "query_goal": goal,
        "react_iteration": 0,
        "react_actions": [],
        "react_observations": [],
        "react_final_answer": "",
        "react_tool_signatures": [],
        "react_last_error": "",
        "react_pending_decision": {},
        "next_node": "react_decide",
    }


def _parse_react_decision(raw_content: str) -> dict[str, Any] | None:
    """把模型输出解析并校验为一次受控 ReactDecision；非法返回 None。"""
    from apps.ai.schemas.react import ReactDecision

    if not raw_content or not raw_content.strip():
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        # 兜底提取最外层 JSON 对象。
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    try:
        decision = ReactDecision(**data)
    except Exception:  # noqa: BLE001 - schema 校验失败即视为非法决策
        return None
    return decision.model_dump()


def _is_valid_tool_decision(
    decision: dict[str, Any],
    available_names: list[str],
    allowlist: frozenset[str],
) -> bool:
    """校验模型 Tool 决策：工具名在本轮子集且为只读白名单，参数无越权字段。"""
    tool_name = str(decision.get("tool_name") or "").strip()
    if tool_name not in available_names or tool_name not in allowlist:
        return False
    arguments = decision.get("arguments") or {}
    if not isinstance(arguments, dict):
        return False
    forbidden = sorted(set(arguments) & _FORBIDDEN_REACT_ARGUMENT_FIELDS)
    if forbidden:
        return False
    return True


def _needs_initial_evidence(available_tools: list[dict[str, Any]], observations: list[dict[str, Any]]) -> bool:
    """判断本轮是否仍必须先取得一次受控查询结果。

    客户分析已被分类为需要读取客户事实，且服务端也已经注入了对应 Tool 时，
    模型不能在没有任何 Observation 的情况下直接以「资料不足」结束。此处只
    要求模型重新选择，不替模型指定具体工具或参数。
    """
    return bool(available_tools) and not observations


def react_decide_node(state: OrchestrationState) -> dict:
    """调用模型作一次受 schema 约束的决策：调用只读 Tool 或给出最终回答。

    失败、达到决策上限或模型输出非法时转入安全降级回答，绝不伪造客户事实。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="react_decide")
    from apps.ai.prompts.loader import load_prompt, render_prompt
    from apps.assistant_tasks import tools as task_tools

    iteration = int(state.get("react_iteration") or 0) + 1
    if iteration > max_react_decisions():
        trace_event(
            state,
            "limit.react_decisions_reached",
            node="react_decide",
            iteration=iteration,
            max_decisions=max_react_decisions(),
        )
        return {
            "react_iteration": iteration,
            "react_last_error": "已超过本轮分析次数上限",
            "react_pending_decision": {"action": "final", "insufficient_information": True},
            "next_node": "react_finalize",
        }

    available_tools = state.get("available_react_tools") or []
    observations = state.get("react_observations") or []
    allow_names = [str(item.get("name") or "") for item in available_tools]

    observations_text = _render_observations(observations)
    executed_tools = len(state.get("react_tool_signatures") or [])
    prompt = render_prompt(
        "react_tool_decision",
        question=state.get("user_input", ""),
        query_goal=state.get("query_goal", ""),
        tools=_render_available_tools(available_tools),
        observations=observations_text,
        remaining_decisions=max(max_react_decisions() - (iteration - 1), 0),
        remaining_tools=max(max_tool_calls() - executed_tools, 0),
    )
    try:
        raw = _chat(load_prompt("react_tool_decision_system"), prompt)
    except Exception:  # noqa: BLE001
        raw = ""
    decision = _parse_react_decision(raw)

    action = ""
    if decision is None:
        action = "final"
        trace_event(state, "decision.react_invalid", iteration=iteration)
        decision = {"action": "final", "insufficient_information": True, "reason": "模型输出非法"}
    else:
        action = str(decision.get("action") or "")

    # 有可用的受控查询 Tool、但尚未取得任何事实时，拒绝模型过早结束，并
    # 用同一份可用工具上下文要求它重新作一次选择。重试仍由模型决定调用哪个
    # Tool 和业务参数；若它再次不合规，后续安全降级而不伪造客户事实。
    if action == "final" and _needs_initial_evidence(available_tools, observations):
        trace_event(state, "decision.react_final_rejected", iteration=iteration, reason="evidence_not_requested")
        retry_prompt = (
            f"{prompt}\n\n系统校验：你尚未取得任何客户查询结果，且本轮存在可用的只读工具。"
            "此时不能输出 final；请从上方允许列表中选择一个最能取得所需事实的工具，"
            "并只输出合法的 tool_call JSON。"
        )
        try:
            retried = _parse_react_decision(_chat(load_prompt("react_tool_decision_system"), retry_prompt))
        except Exception:  # noqa: BLE001
            retried = None
        if retried is not None:
            decision = retried
            action = str(decision.get("action") or "")
            trace_event(state, "decision.react_retry", iteration=iteration, action=action)

    if action == "tool_call":
        if not _is_valid_tool_decision(decision, allow_names, task_tools.READ_ONLY_TOOL_ALLOWLIST):
            trace_event(
                state,
                "decision.react_rejected",
                iteration=iteration,
                tool_name=str(decision.get("tool_name") or ""),
                reason="not_allowed_or_forbidden_argument",
            )
            return {
                "react_iteration": iteration,
                "react_last_error": "模型提出了不被允许的调用，已拒绝并降级回答",
                "react_pending_decision": {"action": "final", "insufficient_information": True},
                "next_node": "react_finalize",
            }
        trace_event(
            state,
            "decision.react",
            action="tool_call",
            iteration=iteration,
            tool_name=str(decision.get("tool_name") or ""),
        )
        return {
            "react_iteration": iteration,
            "react_actions": (state.get("react_actions") or []) + [_decision_summary(decision)],
            "react_pending_decision": decision,
            "react_last_error": "",
            "next_node": "execute_react_tool",
        }

    # action == final：由 react_finalize 校验/精炼，不可直接采信完整原文。
    trace_event(
        state,
        "decision.react",
        action="final",
        iteration=iteration,
        insufficient_information=bool(decision.get("insufficient_information", False)),
    )
    return {
        "react_iteration": iteration,
        "react_actions": (state.get("react_actions") or []) + [_decision_summary(decision)],
        "react_pending_decision": {"action": "final", **{k: decision.get(k) for k in ("answer", "insufficient_information")}},
        "react_last_error": "",
        "next_node": "react_finalize",
    }


def _decision_summary(decision: dict[str, Any]) -> dict[str, Any]:
    """把一次决策压缩为可审计、不含参数原文的摘要。"""
    action = str(decision.get("action") or "")
    if action == "tool_call":
        raw_arguments = decision.get("arguments") or {}
        # 仅保留查询范围这类非身份、非正文的标量；供下一轮理解“近三个月”等
        # 追问。customer_id 等归属字段仍永远不进会话上下文。
        safe_arguments = {
            key: value
            for key, value in raw_arguments.items()
            if key in {"days", "from_date", "to_date", "limit"}
            and isinstance(value, (str, int, float, bool))
        } if isinstance(raw_arguments, dict) else {}
        return {
            "action": "tool_call",
            "tool_name": str(decision.get("tool_name") or ""),
            "argument_keys": sorted(str(k) for k in (decision.get("arguments") or {}).keys()),
            "safe_arguments": safe_arguments,
        }
    return {
        "action": "final",
        "insufficient_information": bool(decision.get("insufficient_information", False)),
    }


def execute_react_tool_node(state: OrchestrationState) -> dict:
    """校验模型决策并执行一次只读 Tool，保存脱敏 Observation 与审计引用。

    服务端忽略/拒绝模型提交的 customer_id，改为从已持久化的任务客户注入可信
    上下文；仅调用 read_only=True 的 Tool；失败时记录错误并降级。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="execute_react_tool")
    task = _task_from_state(state)
    decision = state.get("react_pending_decision") or {}

    tool_name = str(decision.get("tool_name") or "").strip()
    model_arguments = decision.get("arguments") or {}
    if not isinstance(model_arguments, dict):
        model_arguments = {}

    # 服务端注入可信客户上下文，忽略模型提交的任何归属字段。
    arguments: dict[str, Any] = dict(model_arguments)
    for field in _FORBIDDEN_REACT_ARGUMENT_FIELDS:
        arguments.pop(field, None)
    if state.get("customer_id") is not None:
        arguments["customer_id"] = state.get("customer_id")

    signature = _tool_signature(tool_name, arguments)
    signatures = list(state.get("react_tool_signatures") or [])
    tool_result_refs = list(state.get("tool_result_refs") or [])

    if signature in signatures:
        # 相同 Tool + 相同规范化参数在同一回合只执行一次。
        trace_event(state, "decision.tool_dedup_skipped", tool=tool_name)
        return {
            "react_tool_signatures": signatures,
            "react_pending_decision": {},
            "next_node": "react_decide",
        }

    from apps.assistant_tasks import tools as task_tools

    result = None
    last_error: Exception | None = None
    # 单个 Tool 最多执行 2 次（首次 + 1 次重试）。
    for _attempt in range(2):
        try:
            result = task_tools.execute_tool(task, tool_name, arguments)
            break
        except (task_tools.ToolBusinessError,) as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - 未知错误也安全降级
            last_error = exc
            break

    signatures.append(signature)
    observations = list(state.get("react_observations") or [])
    if result is not None:
        trace_event(state, "decision.react_tool_ok", tool=tool_name)
        tool_result_refs.append(f"tool_execution:{result.tool_execution.id}")
        observations.append(_observation_for_tool(tool_name, dict(result)))
        error_text = ""
    else:
        trace_event(
            state,
            "decision.react_tool_failed",
            tool=tool_name,
            error=_safe_error(last_error),
        )
        tool_result_refs.append(f"tool_failed:{tool_name}")
        observations.append(_observation_for_error(tool_name, last_error))
        error_text = _safe_error(last_error)

    return {
        "react_tool_signatures": signatures,
        "react_observations": observations,
        "tool_result_refs": tool_result_refs,
        "react_last_error": error_text,
        "react_pending_decision": {},
        "next_node": "react_decide",
    }


def _render_available_tools(tools: list[dict[str, Any]]) -> str:
    """把本轮可用 Tool 的安全描述渲染给模型。"""
    if not tools:
        return "（本轮没有可用的数据查询工具，请直接给出回答）"
    lines: list[str] = []
    for item in tools:
        schema = item.get("input_schema") or {}
        lines.append(
            "- {name}: {description}；参数：{schema}".format(
                name=item.get("name", ""),
                description=item.get("description", ""),
                schema=json.dumps(schema, ensure_ascii=False),
            )
        )
    return "\n".join(lines)


def _render_observations(observations: list[dict[str, Any]]) -> str:
    """把已取得的脱敏 Observation 渲染给模型。"""
    if not observations:
        return "（暂无已查询结果）"
    parts: list[str] = []
    for index, item in enumerate(observations, start=1):
        if item.get("error"):
            parts.append(f"{index}. {item['tool']}：查询失败，{item['error']}")
        else:
            parts.append(f"{index}. {item['tool']}：{item['summary']}")
    return "\n".join(parts)


def _observation_for_tool(tool_name: str, result: Any) -> dict[str, Any]:
    """把只读 Tool 结果压缩为限长的脱敏 Observation。"""
    summary = _summarize_react_result(result)
    return {"tool": tool_name, "summary": summary[:600], "error": ""}


def _observation_for_error(tool_name: str, exc: Exception | None) -> dict[str, Any]:
    return {"tool": tool_name, "summary": "", "error": _safe_error(exc)}


def _summarize_react_result(result: Any) -> str:
    """针对不同 Tool 结果输出安全的紧凑事实摘要，绝不泄露病史/手机号原文。"""
    if not isinstance(result, dict):
        return "已获取"
    parts: list[str] = []
    # customer_id 只用于服务端归属校验，不能进入给模型的 Observation，更不能
    # 出现在面向康复师的自然语言回答中。
    if "total" in result:
        parts.append(f"共 {result['total']} 条")
    items = result.get("items")
    if isinstance(items, list) and items:
        # 仅保留每条的结构化极小摘要（日期 + 已脱敏文本的前缀）。
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            date = item.get("course_date") or item.get("training_date") or item.get("date")
            sub = "；".join(
                str(item.get(k))[:80]
                for k in ("customer_feedback", "therapist_observation", "next_plan", "note")
                if item.get(k)
            )
            name = ""
            if item.get("exercises"):
                ex_names = [
                    (ex.get("exercise_name") or "")
                    for ex in item.get("exercises")[:10]
                    if isinstance(ex, dict) and ex.get("exercise_name")
                ]
                name = "；训练动作：" + "、".join(ex_names)
            parts.append(f"[{date or '-'}] {sub}{name}")
    assessment = result.get("assessment") or {}
    if isinstance(assessment, dict) and assessment.get("exists"):
        parts.append(f"首次评估：{assessment.get('status_display') or assessment.get('status') or '已完成'}")
    elif result.get("has_initial_assessment"):
        parts.append(f"首次评估：{result.get('status') or '已完成'}")
    plan = result.get("active_plan") or {}
    if isinstance(plan, dict) and plan.get("name"):
        parts.append(f"当前计划：{plan['name']}")
    if not parts:
        return "已获取"
    return "；".join(parts)


def react_finalize_node(state: OrchestrationState) -> dict:
    """基于已取得事实生成最终答复，区分系统事实与建议，资料不足则如实说明。

    模型须输出结构化的 {answer, facts, advice, data_gap}；本节点只采信 facts 中有
    记录依据的部分。硬性校验：
      - 当没有任何可用 Observation 时，模型若仍给出声称基于记录的积极回答，
        一律降级为如实说明资料不足，绝不把未核实内容当作事实呈现给康复师。
      - data_gap=true 时如实说明，不编造。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="react_finalize")
    from apps.ai.prompts.loader import load_prompt, render_prompt

    observations = state.get("react_observations") or []
    usable = [item for item in observations if _observation_contains_fact(item)]
    has_usable_fact = bool(usable)

    context_text = _render_observations(observations)
    try:
        prompt = render_prompt(
            "react_customer_answer",
            question=state.get("user_input", ""),
            context=context_text,
        )
        raw = _chat(load_prompt("react_customer_answer_system"), prompt)
        parsed = _parse_react_final_answer(raw)
    except Exception:  # noqa: BLE001 - 解析/模型失败均走安全降级，不伪造
        parsed = None

    # Tool 已返回可回答的事实时，模型不能以 data_gap=true 丢弃这些事实。
    # 先把相同的受控摘要带回模型要求重答；重试失败时，直接返回服务端已验证的
    # 简要事实，避免“查到了记录却说没有资料”。
    if parsed is not None and has_usable_fact and parsed.get("data_gap", False):
        trace_event(state, "decision.final_data_gap_rejected", reason="usable_fact_exists")
        retry_prompt = (
            f"{prompt}\n\n系统校验：上方摘要中已有可验证的系统记录。不得把 data_gap 设为 true，"
            "请依据这些记录重新作答；若记录不足以进行完整判断，可在 answer 中说明限制，"
            "但仍须在 facts 中陈述已知事实。"
        )
        try:
            retried = _parse_react_final_answer(_chat(load_prompt("react_customer_answer_system"), retry_prompt))
        except Exception:  # noqa: BLE001
            retried = None
        if retried is not None and not retried.get("data_gap", False):
            parsed = retried
            trace_event(state, "decision.final_retry", outcome="accepted")
        else:
            parsed = {
                "answer": _fact_only_reply(usable),
                "facts": [],
                "advice": [],
                "data_gap": False,
            }
            trace_event(state, "decision.final_retry", outcome="fact_fallback")

    # 没有可用事实却仍尝试编造内容：一律转为如实说明，避免伪造。
    degraded = False
    if parsed is not None:
        reply = _compose_react_answer(parsed)
        if (not has_usable_fact) and (not parsed.get("data_gap", False)):
            parsed = {**parsed, "data_gap": True}
            reply = _insufficient_reply()
            degraded = True
    else:
        reply = _insufficient_reply()
        degraded = True
    trace_event(
        state,
        "decision.finalize",
        has_usable_fact=has_usable_fact,
        parsed=parsed is not None,
        degraded_to_insufficient=degraded,
        data_gap=bool(parsed.get("data_gap", False)) if parsed else True,
    )

    message_id = _save_assistant_message(state.get("conversation_id"), reply)
    return {
        "next_node": "react_finalized",
        "reply_content": reply,
        "assistant_message_id": message_id,
        "react_final_answer": reply,
        "customer_summary": _customer_summary_from_observations(state),
    }


def _insufficient_reply() -> str:
    """资料不足时的固定降级表述（可核实、不虚构）。"""
    return "（资料不足）目前没有足够的系统记录来可靠回答该问题，建议结合该客户的档案与评估资料核实后再继续。"


def _observation_contains_fact(item: dict[str, Any]) -> bool:
    """判断 Observation 是否含可直接向康复师陈述的事实，而非仅表示调用成功。"""
    if item.get("error"):
        return False
    summary = str(item.get("summary") or "").strip()
    # Tool 可能只返回内部客户 ID 或“已获取”，这两种都不能独立构成业务事实。
    summary = _sanitize_user_facing_text(summary)
    return bool(summary and summary != "已获取")


def _fact_only_reply(observations: list[dict[str, Any]]) -> str:
    """模型在已有事实下仍拒答时，返回脱敏 Observation 的确定性摘要。"""
    summaries: list[str] = []
    for item in observations:
        summary = str(item.get("summary") or "").strip()
        summary = _sanitize_user_facing_text(summary)
        if summary and summary != "已获取":
            summaries.append(summary)
    if not summaries:
        return _insufficient_reply()
    return _sanitize_user_facing_text("已查询到系统记录：" + "；".join(summaries))


_INTERNAL_IDENTIFIER_PATTERNS = (
    # 括号形式，如“黄伟成（客户ID 5）”“该客户 (ID: 5)”。
    re.compile(
        r"[（(]\s*(?:(?:客户|病人|患者|训练记录|评估|计划|任务)\s*)?"
        r"(?:ID|编号)\s*(?:为|是|[:：#])?\s*\d+\s*[）)]",
        re.IGNORECASE,
    ),
    # 文字形式，如“客户ID 5”“客户编号为5”“训练记录 ID: 12”。
    re.compile(
        r"(?:客户|病人|患者|训练记录|训练|评估|计划|任务|工具执行|customer|record|assessment|plan|task)"
        r"\s*(?:ID|编号)\s*(?:为|是|[:：#])?\s*\d+",
        re.IGNORECASE,
    ),
    # 模型偶发省略资源名称，仅回显“ID 5”时也必须去除。
    re.compile(r"\bID\s*(?:为|是|[:：#])?\s*\d+", re.IGNORECASE),
)


def _sanitize_user_facing_text(value: Any) -> str:
    """移除模型意外回显的内部资源标识，保留可读业务事实。

    权限校验所需的 ID 仍在任务、会话和 Tool 审计记录中；这里仅限制自然语言
    回答。该服务端兜底不能只依赖提示词，因为模型可复述 Observation 或猜测 ID。
    """
    text = str(value or "")
    for pattern in _INTERNAL_IDENTIFIER_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"[（(]\s*[）)]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[；;]\s*[；;]", "；", text)
    return text.strip(" \t；;")


def _parse_react_final_answer(raw_content: str) -> dict | None:
    """把模型结构化最终回答解析为 {answer, facts, advice, data_gap}；非法返回 None。"""
    if not raw_content or not raw_content.strip():
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    answer = _sanitize_user_facing_text(data.get("answer"))[:4000]
    facts = [_sanitize_user_facing_text(x)[:500] for x in (data.get("facts") or []) if _sanitize_user_facing_text(x)][:10]
    advice = [_sanitize_user_facing_text(x)[:500] for x in (data.get("advice") or []) if _sanitize_user_facing_text(x)][:10]
    data_gap = bool(data.get("data_gap", False))
    if not answer and not facts:
        return None
    return {"answer": answer, "facts": facts, "advice": advice, "data_gap": data_gap}


def _compose_react_answer(parsed: dict) -> str:
    """把结构化最终回答渲染为业务语言文本，明确区分「记录事实」与「建议」。"""
    facts = [str(x) for x in parsed.get("facts") or []]
    advice = [str(x) for x in parsed.get("advice") or []]
    answer = str(parsed.get("answer") or "").strip()

    if parsed.get("data_gap"):
        return _insufficient_reply()

    parts: list[str] = []
    if answer:
        parts.append(answer)
    if facts:
        parts.append("—— 系统记录：" + "；".join(facts))
    if advice:
        parts.append("建议：" + "；".join(advice))
    if not parts:
        return _insufficient_reply()
    return "\n".join(parts)


def _customer_summary_from_observations(state: OrchestrationState) -> dict[str, Any] | None:
    """从已取得的 Observation 提炼客户信息摘要（若本轮调用了上下文工具）。"""
    for item in state.get("react_observations") or []:
        if item.get("tool") == "get_customer_context" and not item.get("error"):
            result_summary = item.get("summary") or ""
            return {
                "customer_id": state.get("customer_id"),
                "name": "",
                "recent_note": result_summary[:120],
            }
    return None


def answer_with_context_node(state: OrchestrationState) -> dict:
    """基于只读事实组织脱敏上下文并生成回复，明确区分系统记录与建议。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="answer_with_context")
    from apps.ai.prompts.loader import load_prompt, render_prompt

    context_parts: list[str] = []
    customer_summary: dict[str, Any] | None = None
    for item in state.get("tool_contexts", []):
        tool_name = item.get("tool")
        if "error" in item:
            context_parts.append(f"- {tool_name}：查询失败，未能获取该项信息")
            continue
        result = item.get("result")
        context_parts.append(f"- {tool_name}：{_summarize_context(result)}")
        if tool_name == "get_customer_context" and customer_summary is None:
            customer_summary = _extract_customer_summary(result)

    context_text = "\n".join(context_parts) if context_parts else "（暂无系统记录）"
    prompt = render_prompt(
        "customer_answer",
        context=context_text,
        question=state.get("user_input", ""),
    )
    try:
        parsed = _parse_react_final_answer(_chat(load_prompt("customer_answer_system"), prompt))
        reply = _compose_react_answer(parsed) if parsed is not None else _insufficient_reply()
    except Exception:  # noqa: BLE001
        reply = "暂时无法读取客户信息，请稍后重试。"
    message_id = _save_assistant_message(state.get("conversation_id"), reply)
    return {
        "next_node": "answer_with_context",
        "reply_content": reply,
        "assistant_message_id": message_id,
        "customer_summary": customer_summary,
    }


def _extract_customer_summary(result: Any) -> dict[str, Any] | None:
    """把 get_customer_context 结果提炼为脱敏摘要，供客户信息摘要卡片渲染。"""
    if not isinstance(result, dict):
        return None
    customer = result.get("customer")
    initial = result.get("initial_assessment") or {}
    plan = result.get("active_plan") or {}
    stage = result.get("current_stage") or {}
    return {
        "customer_id": result.get("customer_id"),
        "name": (customer or {}).get("name", ""),
        "phone_masked": (customer or {}).get("phone_masked", ""),
        "gender_display": (customer or {}).get("gender_display", ""),
        "main_issue": (customer or {}).get("main_issue", ""),
        "recent_training_count": result.get("recent_training_count", 0),
        "initial_assessment": {
            "exists": bool(initial.get("exists")),
            "status_display": initial.get("status_display", ""),
        },
        "active_plan": {
            "name": plan.get("name", ""),
            "goals": plan.get("goals", ""),
        } if plan else None,
        "current_stage": {
            "stage_type_display": stage.get("stage_type_display", ""),
        } if stage else None,
    }


def _summarize_context(result: Any) -> str:
    """把只读 Tool 结果压缩为受限的脱敏摘要，避免把完整资料带入提示词。"""
    if not isinstance(result, dict):
        return "已获取"
    parts: list[str] = []
    customer = result.get("customer")
    if isinstance(customer, dict):
        parts.append(f"客户 {customer.get('name', '')}")
    initial = result.get("initial_assessment") or result.get("assessment")
    if isinstance(initial, dict):
        status = initial.get("status_display") or initial.get("status") or ""
        if initial.get("exists"):
            parts.append(f"首次评估：{status or '已完成'}")
        else:
            parts.append("首次评估：尚未完成")
    if "recent_training_count" in result:
        parts.append(f"训练记录 {result['recent_training_count']} 条")
    if "total" in result and "items" in result:
        parts.append(f"共 {result['total']} 条记录")
    plan = result.get("active_plan")
    if isinstance(plan, dict) and plan.get("name"):
        parts.append(f"当前计划：{plan['name']}")
    return "；".join(parts) if parts else "已获取"


def ensure_customer_node(state: OrchestrationState) -> dict:
    """训练补记/评估/修订/随访前确保客户已绑定。

    未绑定客户时，用当前康复师目录对原文做确定性匹配：
        exact 且唯一   -> 预选该客户并继续生成待确认草稿（草稿仍需人工确认，
                          同时记录 preselected_customer_id 供前端展示“可更换”）。
        ambiguous/多候选 -> wait_customer_selection 展示候选。
        unmatched      -> wait_customer_name 请康复师补充或主动搜索。
    客户已绑定则按原意图回到各自草稿生成分支。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="ensure_customer")
    if state.get("customer_id") is not None:
        intent = state.get("intent") or ""
        branch = "prepare_react_tools" if intent == "customer_analysis" else (
            "create_training_draft" if intent == "training_record" else "create_domain_draft"
        )
        trace_event(state, "decision.customer_bound", intent=intent, branch=branch)
        if intent == "customer_analysis":
            return {"next_node": "prepare_react_tools"}
        if intent == "training_record":
            return {"next_node": "create_training_draft"}
        return {"next_node": "create_domain_draft"}

    task = _task_from_state(state)
    from apps.customers.catalog import resolve_customers_from_text

    raw_text = state.get("user_input", "") or _latest_user_message(task)
    result = resolve_customers_from_text(task.therapist, raw_text)
    if result.is_ambiguous:
        trace_event(
            state,
            "decision.customer_lookup",
            outcome="ambiguous",
            candidate_count=len(result.candidates),
        )
        # 只返回命中候选；供前端选择，绝不自动绑定。
        candidates = [
            _directory_candidate(task.therapist, c.customer_id)
            for c in result.candidates
            if c.customer_id is not None
        ]
        return {
            "next_node": "wait_customer_selection",
            "missing_fields": ["customer_id"],
            "customer_candidates": candidates,
            "preselected_customer_id": None,
            "identity_resolution": {
                "status": "waiting_selection",
                "matched_customer_ids": [c.customer_id for c in result.candidates if c.customer_id],
                "source": "directory_ambiguous",
            },
        }
    if result.is_unmatched:
        trace_event(state, "decision.customer_lookup", outcome="unmatched", candidate_count=0)
        return {
            "next_node": "wait_customer_name",
            "missing_fields": ["customer_name"],
            "preselected_customer_id": None,
            "identity_resolution": {"status": "unresolved", "matched_customer_ids": [], "source": "directory_unmatched"},
        }
    # exact：预选客户并继续生成草稿（草稿仍需康复师确认保存）。
    intent = state.get("intent") or ""
    if intent == "customer_analysis":
        next_step = "prepare_react_tools"
    elif intent == "training_record":
        next_step = "create_training_draft"
    else:
        next_step = "create_domain_draft"
    trace_event(state, "decision.customer_lookup", outcome="exact", candidate_count=1, branch=next_step)
    return {
        "customer_id": result.customer_id,
        "preselected_customer_id": result.customer_id,
        "identity_resolution": {
            "status": "preselected",
            "matched_customer_ids": [result.customer_id],
            "source": "directory_exact",
        },
        "next_node": next_step,
    }


def _directory_candidate(therapist: Any, customer_id: int | None) -> dict[str, Any] | None:
    """把目录命中的客户主键转成前端可展示的最小脱敏候选。

    严格限定在当前康复师作用域，命中客户不归属则返回 None（安全兜底），
    绝不因别称或误读跨康复师返回资料。
    """
    if customer_id is None:
        return None
    from apps.customers.models import Customer

    customer = Customer.objects.filter(pk=customer_id, therapist=therapist).first()
    if customer is None:
        return None
    return {
        "id": customer.id,
        "name": customer.name,
        "phone_masked": customer.phone_masked or "",
        "gender": customer.gender,
        "status": customer.status,
        "status_display": customer.get_status_display(),
    }


def create_domain_draft_node(state: OrchestrationState) -> dict:
    """按意图生成对应领域草稿（评估/训练修订/随访），等待康复师确认。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="create_domain_draft", intent=state.get("intent", ""))
    task = _task_from_state(state)

    existing_draft_id = (state.get("resource_refs") or {}).get("draft_id")
    if existing_draft_id:
        return {
            "resource_refs": state.get("resource_refs"),
            "next_node": "wait_draft_confirmation",
            "needs_confirmation": True,
        }

    from apps.ai.services import domain_drafts

    intent = state.get("intent") or ""
    input_text = state.get("user_input", "") or _latest_user_message(task)
    if not input_text.strip():
        return {"next_node": "wait_customer_name", "missing_fields": ["draft_text"]}

    if intent == "assessment":
        draft = domain_drafts.parse_assessment_draft(
            task.therapist, input_text, customer_id=state.get("customer_id"), assistant_task_id=task.id
        )
    elif intent == "training_revision":
        draft = domain_drafts.parse_training_revision_draft(
            task.therapist, input_text, customer_id=state.get("customer_id"), assistant_task_id=task.id
        )
    elif intent == "followup":
        draft = domain_drafts.parse_followup_draft(
            task.therapist, input_text, customer_id=state.get("customer_id"), assistant_task_id=task.id
        )
    else:
        return {"next_node": "wait_customer_name", "missing_fields": ["draft_text"]}

    return {
        "resource_refs": {"draft_id": draft.id, "task_id": task.id, "draft_type": draft.draft_type},
        "next_node": "wait_draft_confirmation",
        "needs_confirmation": True,
    }


def create_training_draft_node(state: OrchestrationState) -> dict:
    """生成训练补记草稿（pending），等待康复师确认。

    若已有草稿（恢复场景），不重复生成，只返回已有 draft_id。
    """
    _bump_step(state)
    trace_event(state, "node.enter", node="create_training_draft")
    orchestration_task = _task_from_state(state)

    existing_draft_id = (state.get("resource_refs") or {}).get("draft_id")
    if existing_draft_id:
        return {
            "resource_refs": state.get("resource_refs"),
            "next_node": "wait_draft_confirmation",
            "needs_confirmation": True,
        }

    from apps.ai.services import training_parser
    from apps.assistant_tasks import services as task_services

    input_text = state.get("user_input", "") or _latest_user_message(orchestration_task)
    if not input_text.strip():
        return {"next_node": "wait_customer_name", "missing_fields": ["training_text"]}

    business_task = task_services.create_task(
        orchestration_task.therapist,
        customer=state.get("customer_id"),
        task_type="training_record",
        skill_code="training_record",
        origin="assistant_turns",
        business_key=f"training_record:{orchestration_task.id}",
    )

    draft = training_parser.parse_training_draft(
        orchestration_task.therapist,
        input_text,
        customer_id=state.get("customer_id"),
        assistant_task_id=business_task.id,
    )
    return {
        "resource_refs": {"draft_id": draft.id, "task_id": business_task.id, "draft_type": draft.draft_type},
        "next_node": "wait_draft_confirmation",
        "needs_confirmation": True,
    }


def _latest_user_message(task: Any) -> str:
    """从任务关联会话读取最后一条用户消息原文（恢复训练补记输入）。"""
    conversation_id = getattr(task, "conversation_id", None)
    if not conversation_id:
        return ""
    from apps.conversations.models import Message

    message = (
        Message.objects.filter(conversation_id=conversation_id, role="user")
        .order_by("-created_at", "-id")
        .first()
    )
    return message.content if message else ""


def wait_draft_confirmation_node(state: OrchestrationState) -> dict:
    """进入等待康复师确认节点。"""
    _bump_step(state)
    trace_event(state, "node.wait", node="wait_draft_confirmation")
    return {"next_node": "wait_draft_confirmation"}


def wait_customer_name_node(state: OrchestrationState) -> dict:
    """等待补充客户姓名。"""
    _bump_step(state)
    trace_event(state, "node.wait", node="wait_customer_name")
    return {"next_node": "wait_customer_name"}


def wait_customer_selection_node(state: OrchestrationState) -> dict:
    """等待同名客户选择。"""
    _bump_step(state)
    trace_event(state, "node.wait", node="wait_customer_selection")
    return {"next_node": "wait_customer_selection"}


def risk_review_node(state: OrchestrationState) -> dict:
    """风险核查：生成非技术化的人工核查提醒，不自动诊断、不生成正式记录。"""
    _bump_step(state)
    trace_event(state, "node.enter", node="risk_review")
    from apps.ai.prompts.loader import load_prompt

    try:
        notice = _chat(load_prompt("risk_review_system"), state.get("user_input", ""))
    except Exception:  # noqa: BLE001
        notice = "这段描述可能涉及需要人工核查的风险或禁忌情况，请结合客户资料确认后再继续，系统不会自动生成任何正式记录。"
    message_id = _save_assistant_message(state.get("conversation_id"), notice)
    return {
        "next_node": "risk_review",
        "risk_notice": notice,
        "reply_content": notice,
        "assistant_message_id": message_id,
    }
