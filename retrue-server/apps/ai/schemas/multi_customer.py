"""多客户批量训练补记的拆分 schema。

模型输出必须经过 Pydantic 严格校验；模型不能决定客户 ID 或正式写入动作。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BatchActivity(BaseModel):
    """一个训练/治疗项目。"""

    name: str = Field(description="动作或治疗名称")
    activity_type: str = Field(default="exercise", description="项目类型 exercise/therapy/massage")
    sets: int | None = Field(default=None, ge=0, description="组数")
    reps: int | None = Field(default=None, ge=0, description="次数")
    quantity: int | None = Field(default=None, ge=0, description="数量")
    unit: str = Field(default="", description="单位")
    duration: int | None = Field(default=None, ge=0, description="时长")


class BatchItem(BaseModel):
    """一个客户的一段训练描述。"""

    sequence: int = Field(ge=1, description="子项顺序，从 1 开始")
    customer_name_hint: str = Field(description="客户姓名提示")
    activities: list[BatchActivity] = Field(default_factory=list, description="训练/治疗项目列表")


class MultiCustomerTrainingSplit(BaseModel):
    """多客户训练补记拆分结果。"""

    intent: str = Field(default="multi_customer_training_record")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    items: list[BatchItem] = Field(default_factory=list, description="有序子项列表")
