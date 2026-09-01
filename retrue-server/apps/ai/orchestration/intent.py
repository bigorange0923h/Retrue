"""意图分类：确定性规则优先 + 模型分类补充。

首期使用确定性规则，保证意图分类稳定、可测试、不依赖模型可用性；后续
接入真实模型时可在低置信度场景下调用 provider 做补充分类。分类结果永远
由编排层再次校验，模型不能直接决定写操作。

意图代码：
    general_knowledge  通用知识咨询（不读客户数据）
    customer_lookup    需按客户姓名查询（未绑定客户）
    customer_question  已绑定客户的历史/进度问题（只读 Tool）
    training_record    训练补记
    risk_review        涉及风险或禁忌（人工核查）
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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


def _extract_customer_name(text: str) -> str:
    """从输入中启发式提取客户姓名提示（首期简单规则）。

    优先匹配「客户/病人/患者 + 姓名」模式，姓名取紧随其后的 2~4 个中文或字母。
    提取失败时返回空字符串；调用方（customer_lookup 节点）对空姓名做安全处理。
    """
    normalized = str(text or "").strip()
    match = re.search(r"(?:客户|病人|患者)[「\s]*(?:叫|是|名字)?[「\s]*([\u4e00-\u9fa5A-Za-z]{2,4})", normalized)
    if match:
        return match.group(1)
    return ""


def classify_intent(text: str, *, customer_bound: bool, customer_name: str = "") -> IntentResult:
    """按确定性规则对一次用户输入分类。

    参数：
        text: 用户原始输入（仅用于分类，不写入任何状态）。
        customer_bound: 当前任务是否已绑定客户。
        customer_name: 前端或前序步骤明确给出的客户姓名提示，可为空。不在此
            处从自由文本猜测姓名，避免把“张三最近”这类片段误当作姓名。
    返回：
        IntentResult 结构化分类结果。
    """
    normalized = str(text or "").strip()

    if any(keyword in normalized for keyword in _RISK_KEYWORDS):
        return IntentResult(intent="risk_review", confidence=0.95)

    # 未绑定客户且输入提到客户姓名/称谓（或前端已给姓名提示）时，优先做
    # 客户检索，避免“客户张三最近的训练”被“训练”误判为补记。
    if not customer_bound and (customer_name or any(keyword in normalized for keyword in _NAME_LOOKUP_KEYWORDS)):
        return IntentResult(intent="customer_lookup", confidence=0.85, customer_name=customer_name)

    if any(keyword in normalized for keyword in _TRAINING_KEYWORDS):
        # 训练补记需要客户上下文；客户未绑定时仍进入补记流程，由其内部
        # ensure_customer 节点决定是否等待选择。
        return IntentResult(
            intent="training_record",
            confidence=0.9,
            customer_name=customer_name,
            needs_confirmation=True,
        )

    if customer_bound:
        if any(keyword in normalized for keyword in _CUSTOMER_QUESTION_KEYWORDS):
            return IntentResult(
                intent="customer_question",
                confidence=0.85,
                required_tools=[],
            )

    return IntentResult(intent="general_knowledge", confidence=0.9)
