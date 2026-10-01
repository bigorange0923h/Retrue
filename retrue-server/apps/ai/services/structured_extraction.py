"""结构化候选的共用类型校验与错误分类。

业务事实是否有原文依据由各领域继续判断；此处只处理输出形状。
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ExtractionValidationError(ValueError):
    """候选结构无效；code 可用于草稿/任务的脱敏错误分类。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_candidate(schema: type[SchemaT], raw: Any) -> SchemaT:
    """以领域 schema 校验候选，返回模型或抛出不含原文的错误。"""
    if not isinstance(raw, dict):
        raise ExtractionValidationError("invalid_shape", "AI 返回的结构不是对象，请重试或手动填写")
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        locations = sorted({".".join(map(str, error["loc"])) for error in exc.errors()})
        fields = "、".join(locations[:5]) or "未知字段"
        raise ExtractionValidationError("schema_invalid", f"AI 返回字段校验失败：{fields}") from exc
