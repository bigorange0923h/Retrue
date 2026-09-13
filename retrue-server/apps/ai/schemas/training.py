"""训练记录 AI 草稿的 Pydantic schema。

定义 AI 解析训练自然语言文本后生成的结构化草稿，
用于数据校验与前端预览/编辑/确认。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ExerciseDraft(BaseModel):
    """训练动作/治疗项目草稿。

    ``activity_type`` 区分训练动作、康复治疗与按摩；``quantity``/``unit``
    表达“康复按摩 1 次”这类以数量为单位、无法用组数/次数表达的项目。
    """

    exercise_name: str = Field(description="动作名称")
    activity_type: str = Field(default="exercise", description="项目类型 exercise/therapy/massage")
    sets: int | None = Field(default=None, ge=0, description="组数")
    reps: int | None = Field(default=None, ge=0, description="次数")
    quantity: int | None = Field(default=None, ge=0, description="数量")
    unit: str = Field(default="", description="单位")
    weight: str = Field(default="", description="负荷/重量")
    duration_seconds: int | None = Field(default=None, ge=0, description="时长（秒）")
    note: str = Field(default="", description="备注")

    @field_validator("exercise_name", "unit", "weight", "note", mode="before")
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """模型按提示词对无法识别的文本字段输出 null，这里归一到空字符串。"""
        return "" if value is None else value

    @field_validator("activity_type", mode="before")
    @classmethod
    def _default_activity_type(cls, value: Any) -> Any:
        """项目类型缺失时按训练动作处理，避免 null 流入正式记录。"""
        return "exercise" if value is None else value

    @model_validator(mode="after")
    def _normalize_exercise_quantity_as_reps(self) -> "ExerciseDraft":
        """把“10 组、每组 12 个”这类明确的训练次数归入 reps。

        部分模型会将“个/下”先写到 ``quantity``；当同一动作已明确组数时，
        其语义是每组次数而非独立治疗数量。只在单位明确且 ``reps`` 缺失时转换，
        不根据经验补全未口述数据。
        """
        if (
            self.activity_type == "exercise"
            and self.sets is not None
            and self.reps is None
            and self.quantity is not None
            and self.unit in {"个", "次", "下"}
        ):
            self.reps = self.quantity
            self.quantity = None
            self.unit = ""
        return self


class TrainingDraft(BaseModel):
    """训练记录 AI 草稿。"""

    training_date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description="训练日期 YYYY-MM-DD",
    )
    customer_hint: str | None = Field(default=None, description="从文本识别的客户姓名提示")
    exercises: list[ExerciseDraft] = Field(default_factory=list, description="训练动作列表")
    customer_feedback: str = Field(default="", description="客户感受")
    therapist_observation: str = Field(default="", description="康复师观察")
    next_plan: str = Field(default="", description="下次计划方向")

    @field_validator("training_date", mode="before")
    @classmethod
    def _default_training_date(cls, value: Any) -> Any:
        """模型省略或输出 null 时，按解析当天补默认训练日期。

        提示词要求“无法确定的日期留空”，因此模型可能不产出 training_date；
        缺省日期由服务端按“今天”补齐，而不是让草稿校验直接失败。
        """
        if value is None or not str(value).strip():
            return date.today().isoformat()
        return value

    @field_validator("customer_feedback", "therapist_observation", "next_plan", mode="before")
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """模型按提示词对无法识别的文本字段输出 null，这里归一到空字符串。"""
        return "" if value is None else value
