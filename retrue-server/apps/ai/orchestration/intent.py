"""意图理解：确定性安全规则 + 结构化模型语义判断。

自然语言不再通过「文本包含某词」直接路由。除风险这类宁可保守拦截的安全
场景外，模型必须以受 Pydantic 校验的 JSON 输出意图、客户实体与缺失参数；
编排层仍负责目录匹配、权限、任务状态及任何写入前的人工确认。

意图代码：
    general_knowledge  通用知识咨询（不读客户数据）
    customer_lookup    需按客户姓名查询（未绑定客户）
    customer_question  已绑定客户的泛化历史/进度问题（只读，兼容旧路径）
    customer_analysis  已绑定客户、带有明确查询目标的只读分析（受控 ReAct 子图）
    training_record    训练补记
    multi_customer_training_record  多客户批量训练补记
    assessment         生成评估草稿
    training_revision  生成训练记录修订草稿
    followup           生成随访草稿
    risk_review        涉及风险或禁忌（人工核查）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentResult:
    """一次意图分类的结构化结果。"""

    intent: str
    confidence: float
    customer_name: str = ""
    required_tools: list[str] | None = None
    needs_confirmation: bool = False
    query_goal: str = ""
    requires_customer_context: bool = False
    missing_slots: list[str] | None = None
    needs_clarification: bool = False
    tasks: list[dict[str, str]] | None = None


# 风险/禁忌触发词。
_RISK_KEYWORDS = (
    "风险",
    "禁忌",
    "危险",
    "不能做",
    "会不会加重",
    "红肿",
    "发热",
)

# 查询目标只用于受控 ReAct 的服务端 Tool 白名单选择与历史兼容；它不再参与
# 自然语言 intent 路由，路由结果完全来自结构化模型。
_QUERY_GOAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "customer_profile": ("基础情况", "基本资料", "档案", "客户资料", "基本情况", "客户信息"),
    "recent_training": ("训练怎么样", "训练情况", "训练内容", "训练次数", "训练了几次", "几次训练", "多少次训练", "训练频率", "训练记录", "练得怎么样", "练了什么", "练了", "训练强度", "训练量", "最近训练", "训练进展"),
    "assessment_progress": ("评估有没有", "评估结果", "评估改善", "有没有改善", "改善没有", "首评", "评估状态", "评估进展"),
    "attendance_or_course": ("缺课", "上课", "课程", "出勤", "排课", "来得勤", "上几节", "课程安排", "来上课", "没来", "旷课"),
}

#: 服务端受控的查询目标取值。模型对 query_goal 的自由文本一律被规整到该集合，
#: 从而保证与 ``nodes._QUERY_GOAL_TOOLS`` 的只读工具白名单映射恒一致。
QUERY_GOAL_VALUES = frozenset(
    {
        "customer_profile",
        "recent_training",
        "assessment_progress",
        "attendance_or_course",
        "comprehensive_progress",
    }
)

def detect_query_goal(text: str) -> str:
    """识别已进入查询分支后的 Tool 白名单目标，不参与意图路由。

    新流程由结构化模型决定是否为客户查询；仅当它已给出 ``customer_analysis``
    后，才可用本函数将查询范围限制到服务端定义的只读 Tool 子集。
    """
    normalized = str(text or "").strip()
    for goal in ("customer_profile", "recent_training", "assessment_progress", "attendance_or_course"):
        if any(keyword in normalized for keyword in _QUERY_GOAL_KEYWORDS[goal]):
            return goal
    return ""


def _normalize_query_goal(text: str, intent: str, model_goal: str) -> str:
    """把模型输出的 query_goal 规整为服务端受控查询目标。

    模型可读意图，但对 ``query_goal`` 常输出自由自然语言（如“查询黄伟成的训练
    次数”），无法映射到 ``nodes._QUERY_GOAL_TOOLS``。因此 customer_analysis 的
    查询目标始终以服务端确定性关键字识别为准：模型给出的自由文本一律丢弃，
    命中 ``_QUERY_GOAL_KEYWORDS`` 则返回对应受控目标，否则退回全量综合查询。
    """
    if intent != "customer_analysis":
        return ""
    goal = str(model_goal or "").strip()
    # 只有明确的受控目标才直接采信；空串与自由文本都交给服务端关键字兜底，
    # 保证 customer_analysis 恒落到受控枚举，能映射到只读工具白名单。
    if goal in QUERY_GOAL_VALUES:
        return goal
    return detect_query_goal(text) or "comprehensive_progress"


def classify_intent(
    text: str,
    *,
    customer_bound: bool,
    customer_name: str = "",
    conversation_context: dict | None = None,
    use_model: bool = True,
) -> IntentResult:
    """识别一次用户输入的语义意图，并返回受控的结构化任务信息。

    参数：
        text: 用户原始输入（仅用于分类，不写入任何状态）。
        customer_bound: 当前任务是否已绑定客户。
        customer_name: 前端或前序步骤明确给出的客户姓名提示。
        use_model: 是否调用结构化模型；仅测试安全降级时可关闭。
    返回：
        IntentResult 结构化分类结果。
    """
    normalized = str(text or "").strip()

    if any(keyword in normalized for keyword in _RISK_KEYWORDS):
        result = IntentResult(intent="risk_review", confidence=0.95)
    elif not customer_bound and customer_name:
        # 前端显式传入的姓名是结构化可信参数，可直接进入目录检索。
        result = IntentResult(intent="customer_lookup", confidence=0.85, customer_name=customer_name)
    else:
        if use_model:
            model_result = classify_intent_with_model(
                normalized,
                customer_name=customer_name,
                customer_bound=customer_bound,
                conversation_context=conversation_context,
            )
            if model_result is not None:
                result = model_result
                logger.info(
                    "意图识别：原文=%r，意图=%s（置信度 %.2f，模型结构化识别）",
                    normalized,
                    result.intent,
                    result.confidence,
                )
                return result
        # 模型不可用时宁可作为只读通用咨询处理，也不猜测训练补记。
        result = IntentResult(intent="general_knowledge", confidence=0.5)

    logger.info(
        "意图识别：原文=%r，意图=%s（置信度 %.2f，需确认=%s）",
        normalized,
        result.intent,
        result.confidence,
        result.needs_confirmation,
    )
    return result


def classify_intent_with_model(
    text: str,
    *,
    customer_name: str = "",
    customer_bound: bool = False,
    conversation_context: dict | None = None,
) -> IntentResult | None:
    """调用模型补充分类，失败时返回 None（由调用方回落规则结果）。

    模型只给出候选意图，仍需经过编排层边界校验；绝不返回可触发写操作的
    未受控意图。
    """
    from apps.ai.providers.base import AIProviderError
    from apps.ai.providers.factory import get_provider
    from apps.ai.schemas.intent import IntentClassification

    try:
        data = get_provider().classify_intent(
            text,
            context={
                "customer_bound": customer_bound,
                "customer_name": customer_name,
                "conversation_context": conversation_context or {},
            },
        )
        parsed = IntentClassification(**data)
    except (AIProviderError, ValueError, TypeError):
        return None
    intent = parsed.intent
    name = str(parsed.customer_name or customer_name).strip()[:64]
    # customer_analysis 的 query_goal 必须受控：丢弃模型的自由文本，优先按服务端
    # 确定性关键字识别具体查询目标；识别不到再退化为全量档案综合查询。
    # 非客户分析意图不需要查询目标。
    goal = _normalize_query_goal(text, intent, parsed.query_goal)
    return IntentResult(
        intent=intent,
        confidence=parsed.confidence,
        customer_name=name,
        query_goal=goal,
        requires_customer_context=intent in {"customer_analysis", "assessment", "training_revision", "followup"},
        needs_confirmation=intent in {"training_record", "multi_customer_training_record", "assessment", "training_revision", "followup"},
        missing_slots=parsed.missing_slots,
        needs_clarification=parsed.needs_clarification,
        tasks=[task.model_dump() for task in parsed.tasks],
    )
