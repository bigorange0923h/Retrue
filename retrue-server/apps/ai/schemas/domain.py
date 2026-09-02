"""评估、随访与训练修订草稿的 Pydantic schema。

AI 只生成待确认草稿；正式写入由康复师确认后经领域服务完成。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssessmentDraft(BaseModel):
    """评估草稿。"""

    assessment_type: str = Field(default="initial", description="评估类型 initial/reassessment")
    assessment_date: str = Field(description="评估日期 YYYY-MM-DD")
    chief_complaint: str = Field(default="", description="主诉")
    medical_history: str = Field(default="", description="病史")
    rehab_goal: str = Field(default="", description="康复目标")
    current_status: str = Field(default="", description="当前状态（复评用）")
    note: str = Field(default="", description="备注")


class FollowUpDraft(BaseModel):
    """随访草稿。"""

    followup_type: str = Field(default="visit", description="类型 visit/review/other")
    due_date: str = Field(description="计划日期 YYYY-MM-DD")
    content: str = Field(default="", description="随访内容")


class TrainingRevisionDraft(BaseModel):
    """训练记录修订草稿。"""

    training_date: str = Field(description="训练日期 YYYY-MM-DD")
    customer_feedback: str = Field(default="", description="客户感受")
    therapist_observation: str = Field(default="", description="康复师观察")
    next_plan: str = Field(default="", description="下次计划")
    note: str = Field(default="", description="备注")
