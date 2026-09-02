"""意图分类的结构化输出 schema。

用于在确定性规则无法判定（低置信度）时，由模型补充分类。分类结果
只作为候选，最终仍由编排层的规则与边界校验兜底，模型不能直接决定写操作。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    """一次模型意图分类的结构化结果。"""

    intent: str = Field(
        description=(
            "意图代码，只能是 general_knowledge / customer_lookup / "
            "customer_question / training_record / risk_review 之一"
        )
    )
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0~1")
    customer_name: str = Field(default="", description="识别到的客户姓名提示，无则为空")
