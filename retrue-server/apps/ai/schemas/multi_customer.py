"""多客户批量训练补记的拆分 schema。

模型输出必须经过 Pydantic 严格校验；模型不能决定客户 ID 或正式写入动作。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class BatchActivity(BaseModel):
    """一个训练/治疗项目。"""

    name: str = Field(default="", description="动作或治疗名称")
    activity_type: str = Field(default="exercise", description="项目类型 exercise/therapy/massage")
    sets: int | None = Field(default=None, ge=0, description="组数")
    reps: int | None = Field(default=None, ge=0, description="次数")
    quantity: int | None = Field(default=None, ge=0, description="数量")
    unit: str = Field(default="", description="单位")
    duration: int | None = Field(default=None, ge=0, description="时长")

    @field_validator("name", "unit", mode="before")
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """模型按提示词对无法确定的文本字段输出 null，这里归一到空字符串。"""
        return "" if value is None else value

    @field_validator("activity_type", mode="before")
    @classmethod
    def _default_activity_type(cls, value: Any) -> Any:
        """项目类型缺失时按训练动作处理，避免 null 流入正式记录。"""
        return "exercise" if value is None else value


class BatchItem(BaseModel):
    """一个客户的一段训练描述。"""

    sequence: int = Field(ge=1, description="子项顺序，从 1 开始")
    customer_name_hint: str = Field(default="", description="客户姓名提示")
    activities: list[BatchActivity] = Field(default_factory=list, description="训练/治疗项目列表")

    @field_validator("customer_name_hint", mode="before")
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """客户姓名提示缺失时归一为空字符串，由康复师在拆分确认卡片上补齐。"""
        return "" if value is None else value


class MultiCustomerTrainingSplit(BaseModel):
    """多客户训练补记拆分结果。"""

    intent: str = Field(default="multi_customer_training_record")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    items: list[BatchItem] = Field(default_factory=list, description="有序子项列表")

    @field_validator("intent", mode="before")
    @classmethod
    def _default_intent(cls, value: Any) -> Any:
        """意图字段缺失时按多客户训练补记处理。"""
        return "multi_customer_training_record" if value is None else value

    @field_validator("confidence", mode="before")
    @classmethod
    def _default_confidence(cls, value: Any) -> Any:
        """置信度缺失时归零，避免 null 导致拆分结果整体校验失败。"""
        return 0.0 if value is None else value
