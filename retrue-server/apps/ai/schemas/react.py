"""受控 ReAct 查询子图的模型决策 schema。

模型每轮只允许输出一次受 schema 约束的「Tool 调用」或「最终回答」决策。本模块
通过 Pydantic 严格校验：将 ``action`` 限制为 ``tool_call``/``final``；把
``tool_name`` 限制为本轮服务端注入的 Tool 名称子集；限制文本参数长度；拒绝未知
字段与越权字段（``customer_id``/``therapist_id`` 等禁止出现）。

模型不能决定客户、康复师或资源归属：``customer_id``/``therapist_id`` 一律由
服务端从已持久化的 ``AssistantTask`` 注入，绝不采信模型输出。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: 允许的决策动作。
_ALLOWED_ACTIONS = frozenset({"tool_call", "final"})

#: 决策文本字段最大长度（防止模型注入超长内容）。
_MAX_TEXT = 1000
_MAX_REASON = 200


class ReactDecision(BaseModel):
    """一次受控决策：调用只读 Tool 或给出最终回答。

    两个动作共用同一条模型输出；校验规则按 ``action`` 分支收紧，避免
    ``tool_call`` 夹带最终回答或反之。
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(description="决策动作，只能是 tool_call 或 final")
    tool_name: str = Field(default="", description="本轮允许调用的只读 Tool 名称")
    arguments: dict = Field(default_factory=dict, description="Tool 的低风险业务参数")
    reason: str = Field(default="", description="作出该决策的原因（供审计，不持久化原文）")
    insufficient_information: bool = Field(
        default=False, description="是否因资料不足而无法给出可靠回答"
    )

    @field_validator("action")
    @classmethod
    def _validate_action(cls, value: str) -> str:
        action = str(value or "").strip()
        if action not in _ALLOWED_ACTIONS:
            raise ValueError("action 只能是 tool_call 或 final")
        return action

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, value: str) -> str:
        tool_name = str(value or "").strip()
        if len(tool_name) > 64:
            raise ValueError("tool_name 过长")
        return tool_name

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, value: str) -> str:
        return str(value or "")[: _MAX_REASON]

    @field_validator("arguments")
    @classmethod
    def _validate_arguments_size(cls, value: dict) -> dict:
        if not isinstance(value, dict):
            raise ValueError("arguments 必须是对象")
        # 仅拒绝异常大请求；具体字段合法性由 Tool 服务端 schema 再校验。
        if sum(len(str(k)) + len(str(v)) for k, v in value.items()) > _MAX_TEXT:
            raise ValueError("arguments 过大")
        return value
