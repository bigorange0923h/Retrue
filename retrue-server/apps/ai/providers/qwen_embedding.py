"""Qwen（阿里云百炼）embedding provider。

使用阿里云百炼 DashScope 的 OpenAI 兼容协议调用 text-embedding-v3，
为客户私有知识库提供向量化能力（RAG）。

配置项来自 settings：AI_EMBEDDING_API_KEY、AI_EMBEDDING_MODEL、AI_EMBEDDING_BASE_URL。
默认模型 text-embedding-v3，默认维度 1024。
"""

from __future__ import annotations

from django.conf import settings

from apps.ai.providers.base import AIProviderError, BaseEmbeddingProvider

#: text-embedding-v3 默认输出维度
DEFAULT_DIMENSIONS = 1024


class QwenEmbeddingProvider(BaseEmbeddingProvider):
    """基于 Qwen（OpenAI 兼容协议）的 embedding provider。

    调用 DashScope /embeddings 端点生成文本向量。
    """

    name = "qwen-embedding"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """初始化 Qwen embedding 客户端。

        参数（可选，缺省时回退到 settings）：
            model: 模型名称，默认 settings.AI_EMBEDDING_MODEL 或 text-embedding-v3。
            api_key: API 密钥，默认 settings.AI_EMBEDDING_API_KEY。
            base_url: 服务地址，默认 DashScope 兼容端点。
            timeout: 请求超时秒数，默认 settings.AI_TIMEOUT。

        异常：
            AIProviderError: 缺少 API Key 配置。
        """
        api_key = api_key or getattr(settings, "AI_EMBEDDING_API_KEY", "") or settings.AI_API_KEY
        if not api_key:
            raise AIProviderError(
                "未配置 embedding API Key（AI_EMBEDDING_API_KEY 或 QWEN_API_KEY），"
                "无法使用 Qwen embedding。请在 retrue-server/.env 中设置。"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 依赖缺失
            raise AIProviderError("缺少 openai 依赖，请运行 pip install openai") from exc

        self.name = f"qwen/{model or getattr(settings, 'AI_EMBEDDING_MODEL', '') or 'text-embedding-v3'}"
        self.model = model or getattr(settings, "AI_EMBEDDING_MODEL", "") or "text-embedding-v3"
        self.dim = DEFAULT_DIMENSIONS
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url
            or getattr(settings, "AI_EMBEDDING_BASE_URL", "")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=timeout or settings.AI_TIMEOUT,
        )

    def dimensions(self) -> int:
        """返回当前向量维度。"""
        return self.dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """将文本列表向量化。

        参数：
            texts: 待向量化的文本列表。
        返回：
            与输入等长的向量列表。
        异常：
            AIProviderError: 调用失败或返回数量不匹配。
        """
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self.model, input=texts)
        except Exception as exc:  # noqa: BLE001
            raise AIProviderError(f"Qwen embedding 调用失败：{exc}") from exc

        data = response.data
        if len(data) != len(texts):
            raise AIProviderError("Qwen embedding 返回向量数量与输入不一致")
        vectors = [item.embedding for item in data]
        self.dim = len(vectors[0]) if vectors else self.dim
        return vectors
