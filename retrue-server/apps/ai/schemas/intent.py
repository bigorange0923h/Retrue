"""意图理解的结构化输出 schema。

自然语言的意图、客户实体、任务数量和待补充参数均由模型一次输出；服务端
只接受本 schema 中的受控字段，并仍负责权限、客户归属和写入确认校验。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ALLOWED_INTENTS = frozenset(
    {
        "general_knowledge",
        "customer_lookup",
        "customer_question",
        "customer_analysis",
        "training_record",
        "multi_customer_training_record",
        "assessment",
        "training_revision",
        "followup",
        "risk_review",
    }
)


class IntentTask(BaseModel):
    """模型发现的一项任务，用于多意图检测和后续任务规划。"""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(description="该子任务的意图代码")
    customer_name: str = Field(default="", max_length=64, description="该任务涉及的客户姓名提示")
    query_goal: str = Field(default="", max_length=64, description="该客户查询子任务的目标，无则为空")

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        """拒绝编排层未定义的意图代码。"""
        normalized = str(value or "").strip()
        if normalized not in _ALLOWED_INTENTS:
            raise ValueError("不支持的意图代码")
        return normalized


class IntentClassification(BaseModel):
    """一次模型意图理解的受控结构化结果。"""

    model_config = ConfigDict(extra="forbid")

    intent: str = Field(
        description="当前应优先执行的意图代码"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0~1")
    customer_name: str = Field(default="", description="识别到的客户姓名提示，无则为空")
    query_goal: str = Field(default="", max_length=64, description="客户查询目标，无则为空")
    missing_slots: list[str] = Field(default_factory=list, description="执行前缺失的必要参数")
    needs_clarification: bool = Field(default=False, description="是否必须向用户追问")
    tasks: list[IntentTask] = Field(default_factory=list, description="发现的任务列表，单任务也可为空")

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        """拒绝模型杜撰的路由代码。"""
        normalized = str(value or "").strip()
        if normalized not in _ALLOWED_INTENTS:
            raise ValueError("不支持的意图代码")
        return normalized

    @field_validator("missing_slots")
    @classmethod
    def validate_missing_slots(cls, value: list[str]) -> list[str]:
        """限制待补充字段，避免将用户原文或未知指令写入状态。"""
        allowed = {"customer_name", "customer_id", "training_content", "training_date"}
        return [item for item in value if item in allowed]
