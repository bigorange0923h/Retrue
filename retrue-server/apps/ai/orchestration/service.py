"""统一回合编排服务。

把一次用户输入统一送入受控图流程，并在图执行前后同步任务状态与审计事件。
本服务是 LangGraph 与 Django 领域服务之间的适配层：

- 权限：从登录康复师与任务归属校验，绝不信任客户端 therapist_id。
- 状态：任务状态迁移由 ``assistant_tasks.services`` 状态机负责。
- 写入：只读 Tool 与草稿生成由领域服务执行；正式写入始终要求康复师确认。
- 恢复：任务中断后从暂停节点定向继续，绝不重跑整张图重新猜测意图。

图状态只保存任务、会话、客户、意图、下一步与引用 ID；不保存聊天原文、手机号、
病史、完整工具输出或提示词。
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.ai.orchestration import nodes
from apps.ai.orchestration.graph import build_graph, build_intake_graph, compile_graph
from apps.ai.orchestration.state import (
    OrchestrationState,
    build_initial_state,
    restore_state_from_task,
    serialize_state,
)
from apps.ai.orchestration.trace import trace_event
from apps.assistant_tasks import services as task_services
from apps.assistant_tasks.models import (
    AssistantRun,
    AssistantRunStatus,
    AssistantTask,
    AssistantTaskStatus,
)


class OrchestrationDisabledError(RuntimeError):
    """编排功能被功能开关关闭。"""


class ConversationContextConflictError(task_services.TaskBusinessError):
    """同一客户会话被请求切换到另一客户时，要求显式新开会话。"""

    code = "conversation_customer_conflict"


def _ensure_enabled() -> None:
    if not getattr(settings, "AI_ORCHESTRATION_ENABLED", False):
        raise OrchestrationDisabledError("AI 助理编排功能未启用")


def _save_message(conversation_id: int, role: str, content: str, metadata: dict | None = None):
    """保存一条不可变消息到会话，返回消息对象。"""
    from apps.conversations.models import Message

    return Message.objects.create(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata=metadata or {},
    )


def _resolve_effective_customer_id(
    therapist: Any,
    *,
    conversation_id: int | None,
    requested_customer_id: int | None,
) -> int | None:
    """解析本回合客户：显式参数优先，否则从同一会话恢复。

    一个普通会话只承载一个客户上下文。请求若显式提交了另一客户，拒绝静默
    切换；多客户训练补记由独立 BatchTaskItem 管理，不经过这里覆盖会话客户。
    """
    from apps.conversations.models import Conversation

    conversation = None
    if conversation_id is not None:
        conversation = Conversation.objects.filter(pk=conversation_id, therapist_id=therapist.id).first()
        if conversation is None:
            raise task_services.TaskPermissionError("会话不存在或无权访问")

    if requested_customer_id is not None:
        if task_services._load_customer(therapist, requested_customer_id) is None:
            raise task_services.TaskPermissionError("客户不存在或无权访问")
        if conversation and conversation.customer_id and conversation.customer_id != requested_customer_id:
            raise ConversationContextConflictError(
                "当前会话已绑定其他客户；请新建会话或先明确切换客户",
                error_code="conversation_customer_conflict",
            )
        return requested_customer_id

    if conversation and conversation.customer_id:
        # 客户可能在历史会话后被转移，必须按当前归属重新验证。
        if task_services._load_customer(therapist, conversation.customer_id) is not None:
            return conversation.customer_id
    return None


def _load_conversation_context(therapist: Any, conversation_id: int | None) -> dict[str, Any]:
    """读取并白名单化受控会话上下文，绝不信任任意 JSON 字段。"""
    if conversation_id is None:
        return {}
    from apps.conversations.models import Conversation

    conversation = Conversation.objects.filter(pk=conversation_id, therapist_id=therapist.id).first()
    raw = conversation.context_data if conversation and isinstance(conversation.context_data, dict) else {}
    context: dict[str, Any] = {}
    for key in ("mode", "last_intent", "last_query_goal", "last_tool", "brief_turn_summary"):
        value = raw.get(key)
        if isinstance(value, str):
            context[key] = value[:128]
    if isinstance(raw.get("active_customer_id"), int):
        context["active_customer_id"] = raw["active_customer_id"]
    if isinstance(raw.get("last_tool_arguments"), dict):
        context["last_tool_arguments"] = {
            key: value
            for key, value in raw["last_tool_arguments"].items()
            if key in {"days", "from_date", "to_date", "limit"}
            and isinstance(value, (str, int, float, bool))
        }
    return context


def _conversation_context_from_state(state: OrchestrationState) -> dict[str, Any]:
    """生成可跨轮保存的最小上下文，不保存原文、病史或完整 Tool 输出。"""
    intent = str(state.get("intent") or "")
    goal = str(state.get("query_goal") or "")
    tool_names = [
        str(item.get("tool_name") or "")
        for item in (state.get("react_actions") or [])
        if str(item.get("tool_name") or "")
    ]
    last_safe_arguments: dict[str, Any] = {}
    for item in reversed(state.get("react_actions") or []):
        if isinstance(item.get("safe_arguments"), dict):
            last_safe_arguments = item["safe_arguments"]
            break
    context: dict[str, Any] = {
        "mode": "single",
        "active_customer_id": state.get("customer_id"),
        "last_intent": intent,
        "last_query_goal": goal,
        "last_tool": tool_names[-1] if tool_names else "",
        "last_tool_execution_refs": list(state.get("tool_result_refs") or [])[-5:],
    }
    if last_safe_arguments:
        context["last_tool_arguments"] = last_safe_arguments
    if intent == "customer_analysis" and goal:
        context["brief_turn_summary"] = f"已完成 {goal} 的受控查询"
    elif intent:
        context["brief_turn_summary"] = f"当前处理意图：{intent}"
    return context


def _sync_conversation_context(task: AssistantTask, state: OrchestrationState) -> None:
    """同步单客户会话的客户身份与最小工作上下文。"""
    conversation_id = state.get("conversation_id")
    customer_id = state.get("customer_id")
    if not conversation_id or not customer_id:
        return
    from apps.conversations.models import Conversation
    from apps.customers.models import Customer

    if not Customer.objects.filter(pk=customer_id, therapist_id=task.therapist_id).exists():
        return
    conversation = Conversation.objects.filter(pk=conversation_id, therapist_id=task.therapist_id).first()
    if conversation is None:
        return
    if conversation.customer_id not in (None, customer_id):
        # 绝不把另一客户覆盖到既有单客户会话。
        return
    conversation.customer_id = customer_id
    conversation.context_data = _conversation_context_from_state(state)
    conversation.save(update_fields=["customer", "context_data", "updated_at"])


def _start_run(task: AssistantTask, *, client_request_id: str = "") -> AssistantRun:
    """创建或复用一次可追溯的 AssistantRun。"""
    from apps.assistant_tasks.models import AssistantRun

    attempt = (
        AssistantRun.objects.filter(task_id=task.id).count() + 1
    )
    return AssistantRun.objects.create(
        task_id=task.id,
        client_request_id=str(client_request_id or "").strip()[:128],
        attempt=attempt,
        status=AssistantRunStatus.RUNNING,
        started_at=timezone.now(),
    )


def _finish_run(run: AssistantRun, *, error: Exception | None = None) -> None:
    """结束一次执行，写状态与脱敏错误信息。"""
    run.finished_at = timezone.now()
    if error is None:
        run.status = AssistantRunStatus.SUCCEEDED
    else:
        run.status = AssistantRunStatus.FAILED
        run.error_code = str(getattr(error, "error_code", "orchestration_failed"))[:64]
        run.error_message = str(error)[:500]
    run.save(update_fields=["status", "error_code", "error_message", "finished_at", "updated_at"])


def _sync_task_after_graph(task: AssistantTask, state: OrchestrationState) -> AssistantTask:
    """把图产出的安全状态同步回任务，并安全绑定唯一解析出的客户。"""
    next_node = state.get("next_node") or ""
    resolved_customer_id = state.get("customer_id")
    if resolved_customer_id:
        # customer_id 只能由目录匹配或已校验的选择写入 state；仍再次限制到当前
        # 康复师，以防历史状态被篡改。关联的是助手任务/会话，不是正式训练数据。
        from apps.conversations.models import Conversation
        from apps.customers.models import Customer

        if Customer.objects.filter(pk=resolved_customer_id, therapist_id=task.therapist_id).exists():
            task.customer_id = resolved_customer_id
            # 只绑定尚未绑定客户的当前会话，绝不覆盖已有客户上下文。
            if state.get("conversation_id"):
                Conversation.objects.filter(
                    pk=state["conversation_id"],
                    therapist_id=task.therapist_id,
                    customer_id__isnull=True,
                ).update(customer_id=resolved_customer_id)
    task.current_step = next_node
    task.missing_fields = list(state.get("missing_fields") or [])
    task.state_data = serialize_state(state)
    task.last_activity_at = timezone.now()
    task.version = (task.version or 0) + 1
    task.save(
        update_fields=[
            "current_step",
            "customer",
            "missing_fields",
            "state_data",
            "last_activity_at",
            "version",
            "updated_at",
        ]
    )
    _sync_conversation_context(task, state)
    return task


def _waiting_status_for_node(next_node: str) -> str:
    """把等待节点映射为任务状态。"""
    if next_node in {"wait_draft_confirmation"}:
        return AssistantTaskStatus.WAITING_CONFIRMATION
    if next_node in {"wait_customer_name", "wait_customer_selection"}:
        return AssistantTaskStatus.WAITING_USER
    if next_node in {"risk_review", "react_decide", "execute_react_tool", "prepare_react_tools"}:
        # 风险核查需人工介入；受控 ReAct 中间节点不应暴露为终态。
        return AssistantTaskStatus.BLOCKED if next_node == "risk_review" else AssistantTaskStatus.COMPLETED
    return AssistantTaskStatus.COMPLETED


def _transition_from_waiting(task: AssistantTask, event_type: str) -> AssistantTask:
    """把等待态先转回 running，再继续执行。"""
    if task.status in {
        AssistantTaskStatus.WAITING_USER,
        AssistantTaskStatus.WAITING_CONFIRMATION,
        AssistantTaskStatus.BLOCKED,
        AssistantTaskStatus.FAILED,
    }:
        return task_services.transition_task(
            task,
            AssistantTaskStatus.RUNNING,
            event_type=event_type,
        )
    return task


def _run_graph(state: OrchestrationState) -> OrchestrationState:
    """运行完整图（仅首轮使用）。"""
    app = compile_graph(build_graph())
    result: OrchestrationState = app.invoke(dict(state))
    return result


def handle_turn(
    therapist: Any,
    *,
    message: str,
    conversation_id: int | None = None,
    customer_id: int | None = None,
    customer_name: str = "",
    client_request_id: str = "",
) -> dict[str, Any]:
    """发起一轮对话：保存消息、创建任务与执行、跑图、同步状态。"""
    _ensure_enabled()

    effective_customer_id = _resolve_effective_customer_id(
        therapist,
        conversation_id=conversation_id,
        requested_customer_id=customer_id,
    )
    conversation_context = _load_conversation_context(therapist, conversation_id)

    if conversation_id is not None:
        _save_message(conversation_id, "user", message)

    # 首句理解也必须通过 LangGraph：它负责意图识别，并在多客户场景解析
    # 姓名提示与有序子项。这里不再在 service/view 层裸调分类或 provider。
    intake_state = build_initial_state(assistant_task_id=0, customer_id=effective_customer_id)
    intake_state["user_input"] = message
    intake_state["customer_name"] = customer_name
    intake_state["conversation_context"] = conversation_context
    intake_result: OrchestrationState = build_intake_graph().compile().invoke(dict(intake_state))
    if intake_result.get("intent") == "multi_customer_training_record":
        return _handle_multi_customer_turn(
            therapist,
            message=message,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
            items_data=list(intake_result.get("multi_customer_items") or []),
        )

    task = task_services.create_task(
        therapist,
        customer=effective_customer_id,
        conversation=conversation_id,
        task_type="assistant_turn",
        skill_code="unified_assistant",
        origin="assistant_turns",
        client_request_id=client_request_id,
        status=AssistantTaskStatus.RUNNING,
    )

    run = _start_run(task, client_request_id=client_request_id)

    state = build_initial_state(
        assistant_task_id=task.id,
        conversation_id=conversation_id,
        customer_id=effective_customer_id,
    )
    state["user_input"] = message
    state["customer_name"] = customer_name
    state["conversation_context"] = conversation_context
    trace_event(state, "turn.start", run_id=run.id, origin="handle_turn")

    try:
        result = _run_graph(state)
    except Exception as exc:
        _finish_run(run, error=exc)
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
            event_data={"run_id": run.id},
        )
        raise

    _finish_run(run)
    task = _sync_task_after_graph(task, result)
    next_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(next_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=next_node,
        event_type="orchestration_turn_completed",
        event_data={"next_node": next_node, "intent": result.get("intent", ""), "run_id": run.id},
        run=run,
    )

    return _turn_payload(task, result)


def resume_task(therapist: Any, task_id: int, *, message: str = "") -> dict[str, Any]:
    """恢复未完成任务：严格从暂停节点继续，不重跑整张图。"""
    _ensure_enabled()
    task = task_services.get_owned_task(therapist, task_id)
    if task is None:
        raise task_services.TaskPermissionError("助手任务不存在或无权访问")

    task_services.recover_stale_running_tasks(therapist, task_id)
    state = restore_state_from_task(task.state_data)

    if message:
        state["user_input"] = message
        if task.conversation_id is not None:
            _save_message(task.conversation_id, "user", message)

    task = _transition_from_waiting(task, "orchestration_resumed")
    run = _start_run(task)
    next_node = state.get("next_node") or ""
    trace_event(state, "turn.start", run_id=run.id, origin="resume_task", from_node=next_node)

    try:
        result = _continue_from_node(state, next_node, run, task)
    except Exception as exc:
        _finish_run(run, error=exc)
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
            event_data={"run_id": run.id},
            run=run,
        )
        raise

    _finish_run(run)
    task = _sync_task_after_graph(task, result)
    target_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(target_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=target_node,
        event_type="orchestration_turn_resumed",
        event_data={"next_node": target_node, "run_id": run.id},
        run=run,
    )
    return _turn_payload(task, result)


def submit_customer_selection(therapist: Any, task_id: int, customer_id: int) -> dict[str, Any]:
    """提交同名客户选择：重新校验归属后按原意图定向继续。"""
    _ensure_enabled()
    task = task_services.get_owned_task(therapist, task_id)
    if task is None:
        raise task_services.TaskPermissionError("助手任务不存在或无权访问")

    customer = task_services._load_customer(therapist, customer_id)
    if customer is None:
        raise task_services.TaskPermissionError("客户不存在或无权访问")

    state = restore_state_from_task(task.state_data)
    state["customer_id"] = customer.id

    task = _transition_from_waiting(task, "orchestration_customer_selection_started")
    run = _start_run(task)
    trace_event(state, "turn.start", run_id=run.id, origin="submit_customer_selection", customer_id=customer.id)

    # 选择客户后按原意图定向：跳过姓名查询。
    intent = state.get("intent") or ""
    try:
        if intent == "training_record":
            result = nodes.ensure_customer_node(state)
            if result.get("next_node") == "create_training_draft":
                draft_result = nodes.create_training_draft_node(state)
                result = {**result, **draft_result}
        elif intent in {"assessment", "training_revision", "followup"}:
            result = nodes.ensure_customer_node(state)
            if result.get("next_node") == "create_domain_draft":
                draft_result = nodes.create_domain_draft_node(state)
                result = {**result, **draft_result}
        elif intent == "customer_question":
            result = nodes.choose_read_tools_node(state)
            exec_result = nodes.execute_read_tools_node(state)
            answer_result = nodes.answer_with_context_node(state)
            result = {**result, **exec_result, **answer_result}
        elif intent == "customer_analysis":
            # 受控 ReAct 客户分析：绑定后按查询目标推进到最终回答。
            react_state = _run_react_query(state, task)
            result = dict(react_state)
        elif intent == "customer_lookup":
            result = nodes.bind_customer_node(state)
        else:
            result = {"next_node": "bound", "customer_id": customer.id}
    except Exception as exc:
        _finish_run(run, error=exc)
        task_services.transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="execution_failed",
            event_type="orchestration_failed",
            event_data={"run_id": run.id},
            run=run,
        )
        raise

    _finish_run(run)
    # 选择客户后，任务正式绑定该客户。
    task.customer_id = customer.id
    task.save(update_fields=["customer", "updated_at"])
    task = _sync_task_after_graph(task, {**state, **result})
    target_node = result.get("next_node") or ""
    target_status = _waiting_status_for_node(target_node)
    task_services.transition_task(
        task,
        target_status,
        current_step=target_node,
        event_type="orchestration_customer_selected",
        event_data={"next_node": target_node, "customer_id": customer.id, "run_id": run.id},
        run=run,
    )
    return _turn_payload(task, {**state, **result})


def _run_react_query(state: OrchestrationState, task: AssistantTask) -> OrchestrationState:
    """把已绑定客户的受控 ReAct 查询子图按节点推进到最终回答。

    手动编排节点以与 service 层其它恢复路径保持一致；每一步结果都回写 state，
    直至 ``react_decide`` 选择 final 并进入 ``react_finalize``。模型决策与 Tool
    调用次数上限由节点内部通过 limits 严格约束，不会无限循环。
    """
    merged = dict(state)
    merged.update(nodes.prepare_react_tools_node(merged))
    merged["next_node"] = "react_decide"
    while True:
        # 先按暂停节点继续，react_decide 决定走向。
        if merged.get("next_node") == "execute_react_tool":
            merged.update(nodes.execute_react_tool_node(merged))
            merged["next_node"] = "react_decide"
            continue
        decision = nodes.react_decide_node(merged)
        merged.update(decision)
        action = (merged.get("react_pending_decision") or {}).get("action") or "final"
        if action == "tool_call":
            merged.update(nodes.execute_react_tool_node(merged))
            continue
        merged.update(nodes.react_finalize_node(merged))
        break
    return merged


def _continue_from_node(
    state: OrchestrationState,
    next_node: str,
    run: AssistantRun,
    task: AssistantTask,
) -> OrchestrationState:
    """按暂停节点定向继续执行，绝不重新分类意图或猜测客户。"""
    state["user_input"] = state.get("user_input", "")
    if next_node in {"wait_customer_name", ""}:
        # 补充姓名后重新查客户。
        result = nodes.customer_lookup_node(state)
    elif next_node == "wait_customer_selection":
        # 未选客户不能继续读取或写入客户数据。
        result = {"next_node": "wait_customer_selection", "missing_fields": ["customer_id"]}
    elif next_node == "wait_draft_confirmation":
        # 只重新展示已有草稿，不重复生成。
        result = {
            "next_node": "wait_draft_confirmation",
            "resource_refs": state.get("resource_refs", {}),
        }
    elif next_node == "risk_review":
        result = {"next_node": "risk_review"}
    else:
        result = {"next_node": next_node or "completed"}
    merged = {**state, **result}
    return merged


def _build_cards(task: AssistantTask, state: OrchestrationState) -> list[dict[str, Any]]:
    """把编排状态转成前端可渲染的结构化卡片描述。

    卡片面向康复师，不含图内部节点名；每张卡片关联 task，并声明其状态和
    允许操作。前端据此渲染，不自行猜测业务状态。
    """
    cards: list[dict[str, Any]] = []
    next_node = state.get("next_node") or ""

    if next_node == "wait_customer_selection" or (
        next_node == "wait_customer_name"
    ):
        candidates = state.get("customer_candidates") or []
        cards.append(
            {
                "id": f"customer_selection:{task.id}",
                "type": "customer_selection",
                "status": "waiting_user",
                "resource_refs": {"task_id": task.id},
                "customer_candidates": candidates,
                "allowed_actions": ["select_customer", "cancel"],
            }
        )

    if next_node == "risk_review":
        cards.append(
            {
                "id": f"risk_review:{task.id}",
                "type": "risk_review",
                "status": "blocked",
                "resource_refs": {"task_id": task.id},
                "notice": state.get("risk_notice", ""),
                "allowed_actions": ["supplement", "continue", "dismiss"],
            }
        )

    if next_node == "wait_draft_confirmation":
        draft_type = (state.get("resource_refs") or {}).get("draft_type") or "training_record"
        card_type = {
            "training_record": "training_draft",
            "assessment": "assessment_draft",
            "followup": "domain_draft",
            "training_revision": "domain_draft",
        }.get(draft_type, "training_draft")
        cards.append(
            {
                "id": f"{card_type}:{(state.get('resource_refs') or {}).get('draft_id') or task.id}",
                "type": card_type,
                "status": "waiting_confirmation",
                "resource_refs": state.get("resource_refs") or {},
                "allowed_actions": ["edit", "confirm", "retry", "cancel"],
            }
        )

    # 目录唯一精确命中：展示「客户预选」卡片（可更换/可确认继续）。
    # 仅在当轮刚完成预选时透出一次；草稿本身仍待康复师确认，不绕过人工把关。
    preselected_id = state.get("preselected_customer_id")
    if next_node == "wait_draft_confirmation" and preselected_id:
        from apps.customers.models import Customer as _Customer

        customer = _Customer.objects.filter(pk=preselected_id, therapist=task.therapist).only(
            "id", "name", "gender", "status"
        ).first()
        cards.append(
            {
                "id": f"customer_preselected:{task.id}",
                "type": "customer_preselected",
                "status": "waiting_confirmation",
                "resource_refs": {
                    "task_id": task.id,
                    "customer_id": preselected_id,
                    "customer_name": customer.name if customer else "",
                    "gender": customer.gender if customer else "",
                    "draft_id": (state.get("resource_refs") or {}).get("draft_id"),
                },
                "notice": "已按此客户生成补记草稿。若不是此客户，可直接在下方草稿中调整或告诉我正确姓名。",
                "allowed_actions": ["confirm"],
            }
        )

    if next_node == "answer_with_context" and state.get("tool_result_refs"):
        cards.append(
            {
                "id": f"customer_summary:{task.id}",
                "type": "customer_summary",
                "status": "completed",
                "resource_refs": {"customer_id": state.get("customer_id"), "task_id": task.id},
                "summary": state.get("customer_summary") or {},
                "allowed_actions": ["view_recent_training", "view_schedule", "start_record", "start_assessment"],
            }
        )

    return cards


def _effective_query_goal(state: OrchestrationState) -> str:
    """返回本次回复应对外暴露的查询目标；仅对客户分析回复有意义。

    query_goal 为仅内存字段、不持久化，恢复任务时为空。为让前端能据目标门控
    「查看近期训练」等入口，customer_analysis 回复若缺内存值则按输入文本就近识别。
    """
    if (state.get("intent") or "") != "customer_analysis":
        return ""
    goal = (state.get("query_goal") or "").strip()
    if goal:
        return goal
    from apps.ai.orchestration.intent import detect_query_goal

    return detect_query_goal(state.get("user_input", "") or "")


def _turn_payload(task: AssistantTask, state: OrchestrationState) -> dict[str, Any]:
    """构造面向客户端的回合响应（不含图内部细节）。"""
    # 阶段 C 埋点：handle_turn / resume_task / submit_customer_selection 都会收敛到
    # 这里，统一在此上报一次本回合脱敏指标（不落 payload，避免泄露内部细节）。
    try:
        from apps.ai.orchestration.metrics import record_turn_metrics

        record_turn_metrics(state)
    except Exception:  # noqa: BLE001 - 埋点失败不影响响应
        pass
    trace_event(
        state,
        "turn.completed",
        intent=state.get("intent", ""),
        final_node=state.get("next_node", ""),
        task_status=getattr(task, "status", ""),
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step,
        "missing_fields": task.missing_fields,
        "customer_id": state.get("customer_id"),
        "intent": state.get("intent", ""),
        "query_goal": _effective_query_goal(state),
        "resource_refs": state.get("resource_refs", {}),
        "customer_candidates": state.get("customer_candidates", []),
        "needs_confirmation": state.get("needs_confirmation", False),
        "reply_content": state.get("reply_content", ""),
        "assistant_message_id": state.get("assistant_message_id"),
        "risk_notice": state.get("risk_notice", ""),
        "cards": _build_cards(task, state),
    }


def _handle_multi_customer_turn(
    therapist: Any,
    *,
    message: str,
    conversation_id: int | None = None,
    client_request_id: str = "",
    items_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """处理多客户批量训练补记：创建父任务与有序子项，返回批次概览卡片。"""
    from apps.training import batch_service

    task, items = batch_service.create_batch_task(
        therapist,
        message,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        items_data=items_data,
    )
    # 首句解析出姓名后，立即按第一项顺序调用当前康复师范围的客户查询；
    # 聊天界面拿到候选卡片后只需由康复师确认，不再要求额外点击“开始”。
    first = batch_service.prepare_current_item(therapist, task.id)
    # ``prepare_current_item`` 在自己的事务中推进父任务步骤；刷新创建任务时
    # 持有的实例，确保首轮 API 返回值与已展示的客户确认卡保持一致。
    task.refresh_from_db(fields=["status", "current_step", "updated_at"])
    first_item = first.get("item")
    cards: list[dict[str, Any]] = [
        {
            "id": f"batch_overview:{task.id}",
            "type": "batch_overview",
            "status": "waiting_user",
            "resource_refs": {"task_id": task.id, "total_items": len(items)},
            "items": [
                {
                    "id": item.id,
                    "sequence": item.sequence,
                    "customer_name_hint": item.customer_name_hint,
                    "status": item.status,
                }
                for item in items
            ],
            "allowed_actions": ["continue", "cancel"],
        }
    ]
    if first_item is not None:
        cards.append(
            {
                "id": f"batch_customer_selection:{task.id}:{first_item.id}",
                "type": "customer_selection",
                "status": "waiting_user",
                "resource_refs": {
                    "task_id": task.id,
                    "item_id": first_item.id,
                    "customer_name_hint": first_item.customer_name_hint,
                    "sequence": first_item.sequence,
                    "total_items": len(items),
                },
                "customer_candidates": first.get("candidates", []),
                "allowed_actions": ["select_customer", "cancel"],
            }
        )
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step,
        "intent": "multi_customer_training_record",
        "reply_content": f"已识别出 {len(items)} 位客户的训练内容，请按顺序逐项处理。",
        "cards": cards,
    }


__all__ = [
    "handle_turn",
    "resume_task",
    "submit_customer_selection",
    "OrchestrationDisabledError",
]
