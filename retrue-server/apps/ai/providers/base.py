"""AI provider 抽象基类。

定义所有 AI 供应商必须实现的接口，使业务层与具体模型解耦。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """AI 供应商抽象基类。

    业务层仅依赖本接口，不感知具体模型 SDK。
    子类需实现 parse_training_text 方法。
    """

    #: provider 展示名，用于日志与故障转移提示
    name: str = "provider"

    @abstractmethod
    def parse_training_text(self, text: str) -> dict:
        """将自然语言训练描述解析为结构化草稿。

        参数：
            text: 康复师输入的自然语言训练描述。
        返回：
            结构化草稿字典，含 exercises、customer_feedback、
            therapist_observation、next_plan 等字段。
        异常：
            raise AIProviderError: 解析失败时抛出。
        """
        raise NotImplementedError

    @abstractmethod
    def prepare_lesson(self, summary: dict) -> dict:
        """基于客户历史汇总生成备课建议。

        参数：
            summary: 客户历史数据汇总（上次训练、当前疼痛、阶段等）。
        返回：
            备课建议字典，含建议检查、推荐测试、训练思路、风险提醒等。
        """
        raise NotImplementedError

    @abstractmethod
    def chat(self, prompt: str, system: str | None = None) -> str:
        """通用对话能力，返回自由文本。

        用于 RAG 回答、客户 AI 对话等需要自然语言输出的场景。
        prompt 通常是已渲染完整的对话/检索指令，system 为可选的系统提示。

        参数：
            prompt: 用户侧消息（通常含上下文）。
            system: 可选的系统提示。
        返回：
            模型生成的文本回答。
        异常：
            raise AIProviderError: 调用失败时抛出。
        """
        raise NotImplementedError

    def parse_assessment_text(self, text: str) -> dict:
        """将自然语言解析为评估草稿（默认实现，基于 chat + JSON）。

        子类可覆盖为更精确的规则或结构化调用。
        """
        from apps.ai.prompts.loader import load_prompt, render_prompt

        prompt = render_prompt("parse_assessment", text=text)
        content = self.chat(prompt, system=load_prompt("parse_system"))
        return self._parse_json_content(content)

    def parse_followup_text(self, text: str) -> dict:
        """将自然语言解析为随访草稿（默认实现，基于 chat + JSON）。"""
        from apps.ai.prompts.loader import load_prompt, render_prompt

        prompt = render_prompt("parse_followup", text=text)
        content = self.chat(prompt, system=load_prompt("parse_system"))
        return self._parse_json_content(content)

    def parse_training_revision_text(self, text: str) -> dict:
        """将自然语言解析为训练记录修订草稿（默认实现，基于 chat + JSON）。"""
        from apps.ai.prompts.loader import load_prompt, render_prompt

        prompt = render_prompt("parse_training_revision", text=text)
        content = self.chat(prompt, system=load_prompt("parse_system"))
        return self._parse_json_content(content)

    @staticmethod
    def _parse_json_content(content: str) -> dict:
        """把模型输出解析为 JSON 字典（复用 deepseek 的容错解析）。"""
        import json
        import re

        if not content.strip():
            raise AIProviderError("AI 返回内容为空")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise AIProviderError("AI 返回内容不是有效 JSON")
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise AIProviderError("AI 返回内容不是有效 JSON") from exc
        return data if isinstance(data, dict) else {}


class BaseEmbeddingProvider(ABC):
    """文本向量化 provider 抽象基类。

    用于客户私有知识库的向量检索（RAG）。
    业务层仅依赖本接口，不感知具体模型 SDK。
    """

    #: provider 展示名，用于日志
    name: str = "embedding"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表向量化。

        参数：
            texts: 待向量化的文本列表，长度 1..N。
        返回：
            与输入等长的向量列表，每个向量维度固定（如 1024）。
        异常：
            raise AIProviderError: 向量化失败时抛出。
        """
        raise NotImplementedError

    @abstractmethod
    def dimensions(self) -> int:
        """返回当前向量维度。"""
        raise NotImplementedError


class AIProviderError(Exception):
    """AI 供应商调用异常。

    解析失败或调用异常时抛出，用于上层转换为用户可读的错误。
    """

    def __init__(self, message: str):
        """初始化异常。

        参数：
            message: 面向用户的中文错误消息。
        """
        super().__init__(message)
        self.message = message
