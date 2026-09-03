"""意图分类：确定性规则优先 + 模型分类补充。

首期使用确定性规则，保证意图分类稳定、可测试、不依赖模型可用性；后续
接入真实模型时可在低置信度场景下调用 provider 做补充分类。分类结果永远
由编排层再次校验，模型不能直接决定写操作。

意图代码：
    general_knowledge  通用知识咨询（不读客户数据）
    customer_lookup    需按客户姓名查询（未绑定客户）
    customer_question  已绑定客户的历史/进度问题（只读 Tool）
    training_record    训练补记
    multi_customer_training_record  多客户批量训练补记
    assessment         生成评估草稿
    training_revision  生成训练记录修订草稿
    followup           生成随访草稿
    risk_review        涉及风险或禁忌（人工核查）
"""

from __future__ import annotations

import logging
import re
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


# 训练补记的确定性触发词。
_TRAINING_KEYWORDS = (
    "补记",
    "训练记录",
    "今天训练",
    "昨天训练",
    "做了",
    "组",
    "次",
    "训练量",
    "练了",
    "康复训练",
)

# 客户历史/进度问题的触发词。
_CUSTOMER_QUESTION_KEYWORDS = (
    "最近",
    "历史",
    "进展",
    "上次",
    "进度",
    "恢复情况",
    "评估",
    "课程",
    "计划",
)

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

# 姓名类意图触发词（未绑定客户时）。
_NAME_LOOKUP_KEYWORDS = (
    "客户",
    "病人",
    "患者",
)

# 评估草稿触发词。
_ASSESSMENT_KEYWORDS = (
    "评估",
    "首评",
    "复评",
    "检查报告",
    "病历",
)

# 训练记录修订触发词。
_TRAINING_REVISION_KEYWORDS = (
    "修改训练",
    "修订训练",
    "改训练",
    "修改一下训练",
    "训练记错了",
    "训练有误",
    "更正",
    "改一下训练",
    "修正训练",
)

# 随访草稿触发词。
_FOLLOWUP_KEYWORDS = (
    "随访",
    "回访",
    "复查",
    "复诊",
    "随访计划",
)


def _is_multi_customer(text: str) -> bool:
    """判断输入是否为多客户批量训练补记。

    特征：出现两个及以上客户名称提示，且包含训练/补记语义关键词。

    康复师经常直接说“张三今天……；李四做了……”，不能要求每个名字
    都带“客户”前缀。这里只做保守的首轮识别；真正的姓名、顺序和训练
    内容仍由 LangGraph 的结构化拆分节点与 schema 校验完成。
    """
    explicit_mentions = re.findall(r"(?:客户|病人|患者)[A-Za-z0-9\u4e00-\u9fa5]{1,4}", text)
    # 仅识别后面紧跟训练叙述的 2~4 个汉字，避免把普通句子片段当作客户名。
    # 裸姓名仅允许位于句首或一段训练描述的分隔符之后。否则“今天做了”会
    # 把“今天”错认成姓名，导致单客户输入被误判为批量任务。
    bare_mentions = re.findall(
        r"(?:^|(?<=[，,；;。\n]))([\u4e00-\u9fa5]{2,4})(?=(?:今天|昨日|昨天|刚刚|做了|练了|训练了|进行了|完成了))",
        text,
    )
    customer_mentions = {item.strip() for item in [*explicit_mentions, *bare_mentions] if item.strip()}
    if len(customer_mentions) < 2:
        return False
    return any(keyword in text for keyword in _TRAINING_KEYWORDS)


def _extract_customer_name(text: str) -> str:
    """从输入中启发式提取客户姓名提示（首期简单规则）。

    优先匹配「客户/病人/患者 + 姓名」模式，姓名取紧随其后的 2~4 个中文或字母。
    提取失败时返回空字符串；调用方（customer_lookup 节点）对空姓名做安全处理。
    """
    normalized = str(text or "").strip()
    match = re.search(r"(?:客户|病人|患者)[「\s]*(?:叫|是|名字)?[「\s]*([\u4e00-\u9fa5A-Za-z]{2,4})", normalized)
    if match:
        return match.group(1)
    # 训练补记常以“张三今天做了……”直接开头。只接受句首或分号后的
    # 2~4 字姓名并要求后接训练谓词，避免将普通句子误认成客户。
    match = re.search(
        r"(?:^|(?<=[，,；;。\n]))([\u4e00-\u9fa5]{2,4}?)(?=(?:今天|昨日|昨天|刚刚|做了|练了|训练了|进行了|完成了))",
        normalized,
    )
    if match:
        return match.group(1)
    return ""


def classify_intent(
    text: str,
    *,
    customer_bound: bool,
    customer_name: str = "",
    use_model: bool = False,
) -> IntentResult:
    """按确定性规则对一次用户输入分类；低置信度时可选由模型补充。

    参数：
        text: 用户原始输入（仅用于分类，不写入任何状态）。
        customer_bound: 当前任务是否已绑定客户。
        customer_name: 前端或前序步骤明确给出的客户姓名提示，可为空。不在此
            处从自由文本猜测姓名，避免把“张三最近”这类片段误当作姓名。
        use_model: 是否允许在规则无法判定时调用模型补充分类（默认关闭，保证
            可测试、可离线、不依赖模型可用性）。
    返回：
        IntentResult 结构化分类结果。
    """
    normalized = str(text or "").strip()

    if any(keyword in normalized for keyword in _RISK_KEYWORDS):
        result = IntentResult(intent="risk_review", confidence=0.95)

    # 多客户批量补记：出现多个“客户X”且含训练/补记语义时优先识别。
    elif _is_multi_customer(normalized):
        result = IntentResult(
            intent="multi_customer_training_record",
            confidence=0.9,
            needs_confirmation=True,
        )

    # 未绑定客户且输入提到客户姓名/称谓（或前端已给姓名提示）时，优先做
    # 客户检索，避免“客户张三最近的训练”被“训练”误判为补记。
    elif not customer_bound and (customer_name or any(keyword in normalized for keyword in _NAME_LOOKUP_KEYWORDS)):
        result = IntentResult(intent="customer_lookup", confidence=0.85, customer_name=customer_name)

    # 评估草稿（需客户上下文，未绑定时走 ensure_customer 等待选择）。
    elif any(keyword in normalized for keyword in _ASSESSMENT_KEYWORDS):
        result = IntentResult(intent="assessment", confidence=0.88, needs_confirmation=True)

    # 训练记录修订。
    elif any(keyword in normalized for keyword in _TRAINING_REVISION_KEYWORDS):
        result = IntentResult(intent="training_revision", confidence=0.86, needs_confirmation=True)

    # 随访草稿。
    elif any(keyword in normalized for keyword in _FOLLOWUP_KEYWORDS):
        result = IntentResult(intent="followup", confidence=0.86, needs_confirmation=True)

    elif any(keyword in normalized for keyword in _TRAINING_KEYWORDS):
        # 训练补记需要客户上下文；客户未绑定时仍进入补记流程，由其内部
        # ensure_customer 节点决定是否等待选择。此处从文本提取裸姓名
        # （如“张三今天做了……”），供 ensure_customer 搜索客户候选，但绝不
        # 据此改变意图为 customer_lookup，避免“今天做了”误判。
        parsed_customer_name = customer_name or _extract_customer_name(normalized)
        result = IntentResult(
            intent="training_record",
            confidence=0.9,
            customer_name=parsed_customer_name,
            needs_confirmation=True,
        )

    elif customer_bound and any(keyword in normalized for keyword in _CUSTOMER_QUESTION_KEYWORDS):
        result = IntentResult(
            intent="customer_question",
            confidence=0.85,
            required_tools=[],
        )

    # 规则无法判定：可选调用模型补充，否则回落到通用咨询。
    else:
        if use_model:
            model_result = classify_intent_with_model(normalized, customer_name=customer_name)
            if model_result is not None:
                result = model_result
                logger.info(
                    "意图识别：原文=%r，意图=%s（置信度 %.2f，模型补充）",
                    normalized,
                    result.intent,
                    result.confidence,
                )
                return result
        result = IntentResult(intent="general_knowledge", confidence=0.9)

    logger.info(
        "意图识别：原文=%r，意图=%s（置信度 %.2f，需确认=%s）",
        normalized,
        result.intent,
        result.confidence,
        result.needs_confirmation,
    )
    return result


def classify_intent_with_model(text: str, *, customer_name: str = "") -> IntentResult | None:
    """调用模型补充分类，失败时返回 None（由调用方回落规则结果）。

    模型只给出候选意图，仍需经过编排层边界校验；绝不返回可触发写操作的
    未受控意图。
    """
    import json

    from apps.ai.prompts.loader import load_prompt, render_prompt
    from apps.ai.providers.base import AIProviderError
    from apps.ai.providers.factory import get_provider

    try:
        prompt = render_prompt("classify_intent", text=text)
        content = get_provider().chat(prompt, system=load_prompt("classify_intent_system"))
    except (AIProviderError, ValueError):
        return None

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None

    intent = str(data.get("intent", "")).strip()
    allowed = {
        "general_knowledge",
        "customer_lookup",
        "customer_question",
        "training_record",
        "multi_customer_training_record",
        "assessment",
        "training_revision",
        "followup",
        "risk_review",
    }
    if intent not in allowed:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    name = str(data.get("customer_name", "") or customer_name).strip()[:64]
    return IntentResult(intent=intent, confidence=confidence, customer_name=name)
