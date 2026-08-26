"""训练记录 AI 草稿的 Pydantic schema。

定义 AI 解析训练自然语言文本后生成的结构化草稿，
用于数据校验与前端预览/编辑/确认。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExerciseDraft(BaseModel):
    """训练动作草稿。"""

    exercise_name: str = Field(description="动作名称")
    sets: int | None = Field(default=None, ge=0, description="组数")
    reps: int | None = Field(default=None, ge=0, description="次数")
    weight: str = Field(default="", description="负荷/重量")
    duration_seconds: int | None = Field(default=None, ge=0, description="时长（秒）")
    note: str = Field(default="", description="备注")


class TrainingDraft(BaseModel):
    """训练记录 AI 草稿。"""

    training_date: str = Field(description="训练日期 YYYY-MM-DD")
    customer_hint: str | None = Field(default=None, description="从文本识别的客户姓名提示")
    exercises: list[ExerciseDraft] = Field(default_factory=list, description="训练动作列表")
    customer_feedback: str = Field(default="", description="客户感受")
    therapist_observation: str = Field(default="", description="康复师观察")
    next_plan: str = Field(default="", description="下次计划方向")
