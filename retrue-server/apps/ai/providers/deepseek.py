"""DeepSeek AI provider。

使用 DeepSeek 的 OpenAI 兼容 API 调用 LLM，生成结构化草稿与备课建议。
配置项来自 settings：AI_API_KEY、AI_MODEL、AI_BASE_URL、AI_TIMEOUT、AI_MAX_TOKENS。
"""

from __future__ import annotations

import json
import re

from django.conf import settings

from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.base import AIProviderError, BaseProvider
from apps.ai.schemas.training import TrainingDraft
from apps.ai.schemas.intent import IntentClassification


class DeepSeekProvider(BaseProvider):
    """基于 DeepSeek（OpenAI 兼容协议）的 provider。

    调用 DeepSeek chat completions，通过 JSON 模式与 Pydantic schema 校验
    生成结构化的训练草稿与备课建议。
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """初始化 DeepSeek 客户端。

        参数（可选，缺省时回退到 settings）：
            model: 模型名称，默认 settings.AI_MODEL 或 deepseek-chat。
            api_key: API 密钥，默认 settings.AI_API_KEY。
            base_url: 服务地址，默认 settings.AI_BASE_URL 或官方地址。
            timeout: 请求超时秒数，默认 settings.AI_TIMEOUT。
            max_tokens: 最大输出 token，默认 settings.AI_MAX_TOKENS。

        异常：
            AIProviderError: 缺少 API Key 配置。
        """
        api_key = api_key or settings.AI_API_KEY
        if not api_key:
            raise AIProviderError(
                "未配置 AI_API_KEY，无法使用 DeepSeek 服务。请在 retrue-server/.env 中设置。"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 依赖缺失
            raise AIProviderError("缺少 openai 依赖，请运行 pip install openai") from exc

        self.name = f"deepseek/{model or settings.AI_MODEL or 'deepseek-chat'}"
        self.model = model or settings.AI_MODEL or "deepseek-chat"
        self.timeout = timeout or settings.AI_TIMEOUT
        self.max_tokens = max_tokens or settings.AI_MAX_TOKENS
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or settings.AI_BASE_URL or "https://api.deepseek.com",
            timeout=self.timeout,
        )

    def parse_training_text(self, text: str) -> dict:
        """将自然语言训练描述解析为结构化草稿。

        参数：
            text: 自然语言训练描述。
        返回：
            符合 TrainingDraft schema 的字典。
        异常：
            AIProviderError: 调用失败或结果无法通过校验。
        """
        schema = _pydantic_to_json_schema(TrainingDraft)
        prompt = render_prompt("parse_training_text", text=text)
        content = self._chat_json(prompt, schema, system=load_prompt("parse_system"))
        try:
            return TrainingDraft(**content).model_dump()
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"AI 结果校验失败：{exc}") from exc

    def classify_intent(self, text: str, *, context: dict | None = None) -> dict:
        """用 JSON 模式生成并校验意图理解结果。"""
        schema = _pydantic_to_json_schema(IntentClassification)
        prompt = render_prompt(
            "classify_intent",
            text=text,
            context=json.dumps(context or {}, ensure_ascii=False),
        )
        content = self._chat_json(prompt, schema, system=load_prompt("classify_intent_system"))
        try:
            return IntentClassification(**content).model_dump()
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"意图识别结果校验失败：{exc}") from exc

    def prepare_lesson(self, summary: dict) -> dict:
        """基于客户历史汇总生成备课建议。

        参数：
            summary: 客户历史数据汇总。
        返回：
            备课建议字典。
        """
        prompt = render_prompt(
            "prepare_lesson",
            summary=json.dumps(summary, ensure_ascii=False),
        )
        content = self._chat_json(prompt, None, system=load_prompt("prepare_system"))
        return {
            "suggested_checks": content.get("suggested_checks", []),
            "recommended_tests": content.get("recommended_tests", []),
            "recommended_parts": content.get("recommended_parts", []),
            "training_approach": content.get("training_approach", ""),
            "risk_reminders": content.get("risk_reminders", []),
        }

    def chat(self, prompt: str, system: str | None = None) -> str:
        """通用对话能力，返回自由文本（RAG 回答、客户对话等）。

        参数：
            prompt: 用户侧消息（含检索到的知识上下文）。
            system: 可选的系统提示。
        返回：
            模型生成的文本回答。
        异常：
            AIProviderError: 调用失败时抛出。
        """
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.3,
            )
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"DeepSeek 对话调用失败：{exc}") from exc
        return response.choices[0].message.content or ""

    def _chat_json(self, prompt: str, schema: dict | None, system: str) -> dict:
        """调用 DeepSeek 并解析 JSON 响应。

        参数：
            prompt: 用户消息。
            schema: JSON schema 或 None（不限制结构）。
            system: 系统提示。
        返回：
            解析后的字典。
        异常：
            AIProviderError: 调用失败或响应无法解析为 JSON。
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        # 若提供 schema，要求 JSON 模式输出
        response_format = {"type": "json_object"} if schema is not None else {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format=response_format,
                max_tokens=self.max_tokens,
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"DeepSeek 调用失败：{exc}") from exc

        content = response.choices[0].message.content or ""
        return _parse_json(content)


def _parse_json(content: str) -> dict:
    """从模型输出中解析 JSON 对象。

    兼容模型输出外层带 ```json 代码块等场景。

    参数：
        content: 模型返回的文本。
    返回：
        解析后的字典。
    异常：
        AIProviderError: 无法解析出 JSON。
    """
    if not content.strip():
        raise AIProviderError("AI 返回内容为空")
    # 移除 markdown 代码块围栏
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试从文本中提取首个 JSON 对象
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise AIProviderError("AI 返回内容不是有效 JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AIProviderError("AI 返回内容不是有效 JSON") from exc
    return data


def _pydantic_to_json_schema(model) -> dict:
    """将 Pydantic 模型转为 JSON schema。

    参数：
        model: Pydantic 模型类。
    返回：
        对应 JSON schema。
    """
    return model.model_json_schema()
