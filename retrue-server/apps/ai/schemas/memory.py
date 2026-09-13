"""对话长期记忆评估的结构化输出。

模型对无法判断的字段可能输出 ``null``；这些字段多为带默认值的 ``Literal`` 或数值，
键存在且为 ``null`` 时默认值不生效，会让**整批**候选校验失败（消费方只能整轮跳过）。
这里把 null 归一到各自的安全默认值：低置信（0.0）与 ``ignore`` 会被消费方直接跳过，
从而只丢弃该条候选，不影响同批其他候选。

见 ``apps.knowledge.memory_evaluator``（阈值 0.6）与 ``apps.knowledge.episode_service``
（阈值 0.7）。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("classification", mode="before")
    @classmethod
    def _ignore_if_none(cls, value: Any) -> Any:
        """分类缺失时按“无需记录”处理，由消费方跳过该候选而非丢弃整批。"""
        return "ignore" if value is None else value

    @field_validator("memory_type", mode="before")
    @classmethod
    def _default_memory_type(cls, value: Any) -> Any:
        """记忆类型缺失时归入 other。"""
        return "other" if value is None else value

    @field_validator("relation", mode="before")
    @classmethod
    def _default_relation(cls, value: Any) -> Any:
        """与现有记忆的关系缺失时按新记忆处理。"""
        return "new" if value is None else value

    @field_validator("confidence", mode="before")
    @classmethod
    def _zero_confidence_if_none(cls, value: Any) -> Any:
        """置信度缺失按 0 处理，低于阈值时该候选被跳过，不会写入可疑记忆。"""
        return 0.0 if value is None else value


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

    @field_validator("confidence", mode="before")
    @classmethod
    def _zero_confidence_if_none(cls, value: Any) -> Any:
        """置信度缺失按 0 处理，低于阈值时该 Episode 被跳过。"""
        return 0.0 if value is None else value


class EpisodeEvaluationResult(BaseModel):
    """一段受控对话上下文中的 Episode 候选。"""

    episodes: list[ExtractedEpisode] = Field(default_factory=list, max_length=3)
