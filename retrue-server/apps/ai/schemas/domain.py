"""评估、随访与训练修订草稿的 Pydantic schema。

AI 只生成待确认草稿；正式写入由康复师确认后经领域服务完成。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AssessmentDraft(BaseModel):
    """评估草稿。"""

    assessment_type: str = Field(default="initial", description="评估类型 initial/reassessment")
    assessment_date: str = Field(default="", description="评估日期 YYYY-MM-DD")
    chief_complaint: str = Field(default="", description="主诉")
    medical_history: str = Field(default="", description="病史")
    rehab_goal: str = Field(default="", description="康复目标")
    current_status: str = Field(default="", description="当前状态（复评用）")
    note: str = Field(default="", description="备注")

    @field_validator("assessment_type", mode="before")
    @classmethod
    def _default_assessment_type(cls, value: Any) -> Any:
        """评估类型缺失时按首次评估处理，避免 null 流入评估记录。"""
        return "initial" if value is None else value

    @field_validator(
        "assessment_date",
        "chief_complaint",
        "medical_history",
        "rehab_goal",
        "current_status",
        "note",
        mode="before",
    )
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """模型按提示词对无法确定的字段输出 null，这里归一到空字符串。

        评估日期留空由确认流程按当天补齐（见 ``confirm_assessment_draft``）。
        """
        return "" if value is None else value


class FollowUpDraft(BaseModel):
    """随访草稿。"""

    followup_type: str = Field(default="visit", description="类型 visit/review/other")
    due_date: str = Field(default="", description="计划日期 YYYY-MM-DD")
    content: str = Field(default="", description="随访内容")

    @field_validator("followup_type", mode="before")
    @classmethod
    def _default_followup_type(cls, value: Any) -> Any:
        """随访类型缺失时按上门随访处理，避免 null 流入随访待办。"""
        return "visit" if value is None else value

    @field_validator("due_date", "content", mode="before")
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """模型按提示词输出 ``due_date=null``（日期未明确提及）时归一为空字符串。

        计划日期留空由确认流程按当天补齐（见 ``confirm_followup_draft``）。
        """
        return "" if value is None else value


class TrainingRevisionDraft(BaseModel):
    """训练记录修订草稿。"""

    training_date: str = Field(default="", description="训练日期 YYYY-MM-DD")
    customer_feedback: str = Field(default="", description="客户感受")
    therapist_observation: str = Field(default="", description="康复师观察")
    next_plan: str = Field(default="", description="下次计划")
    note: str = Field(default="", description="备注")

    @field_validator(
        "training_date",
        "customer_feedback",
        "therapist_observation",
        "next_plan",
        "note",
        mode="before",
    )
    @classmethod
    def _blank_text_if_none(cls, value: Any) -> Any:
        """模型按提示词对无法确定的字段输出 null，这里归一到空字符串。

        修订只更新描述字段，不依赖 ``training_date``（见
        ``confirm_training_revision_draft``）。
        """
        return "" if value is None else value
