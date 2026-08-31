"""对话长期记忆评估的结构化输出。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedMemoryCandidate(BaseModel):
    """模型从一轮对话中提取的一条记忆候选。"""

    classification: Literal[
        "customer_memory", "therapist_observation", "formal_fact", "temporary", "inference", "ignore"
    ]
    memory_type: Literal[
        "preference", "dislike", "communication", "habit", "goal", "concern", "pattern",
        "background", "therapist_observation", "other",
    ] = "other"
    memory_key: str = Field(default="", max_length=100)
    content: str = Field(default="", max_length=1000)
    normalized_value: str = Field(default="", max_length=1000)
    confidence: float = Field(ge=0, le=1)
    importance_score: int = Field(default=3, ge=1, le=5)
    evidence: str = Field(default="", max_length=1000)
    relation: Literal["new", "duplicate", "conflict", "conditional", "supplement"] = "new"


class MemoryEvaluationResult(BaseModel):
    """一轮对话的全部候选输出。"""

    candidates: list[ExtractedMemoryCandidate] = Field(default_factory=list, max_length=5)


class ExtractedEpisode(BaseModel):
    """模型提取的一次重要历史讨论事件。"""

    episode_key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=2000)
    key_points: list[str] = Field(default_factory=list, max_length=10)
    decisions: list[str] = Field(default_factory=list, max_length=10)
    next_actions: list[str] = Field(default_factory=list, max_length=10)
    importance_score: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(ge=0, le=1)


class EpisodeEvaluationResult(BaseModel):
    """一段受控对话上下文中的 Episode 候选。"""

    episodes: list[ExtractedEpisode] = Field(default_factory=list, max_length=3)
