"""AI provider 工厂。

统一 AI 配置入口：
- 主配置：yaml 文件（settings.AI_CONFIG_FILE，默认 ai_config.yaml）。
  providers 列表定义模型顺序；单个 provider 直接使用，多个则组合为故障转移。
- 备选：AI_FALLBACK_PROVIDERS（JSON 数组，兼容旧配置）。
- 单 provider：AI_PROVIDER（最简场景）。

密钥统一通过 api_key_env 引用 .env 中的独立变量，不写入配置文件。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from django.conf import settings

from apps.ai.providers.base import AIProviderError, BaseEmbeddingProvider, BaseProvider
from apps.ai.providers.deepseek import DeepSeekProvider
from apps.ai.providers.fallback import FallbackProvider
from apps.ai.providers.mock import MockProvider
from apps.ai.providers.qwen_embedding import QwenEmbeddingProvider

logger = logging.getLogger(__name__)

# provider 注册表：名称 -> 类
PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "mock": MockProvider,
    "deepseek": DeepSeekProvider,
}

# embedding provider 注册表：名称 -> 类
EMBEDDING_PROVIDER_REGISTRY: dict[str, type[BaseEmbeddingProvider]] = {
    "qwen": QwenEmbeddingProvider,
}


def get_provider() -> BaseProvider:
    """获取当前配置的 AI provider 实例。

    优先级：
    1. yaml 配置（config.enabled=true）。
    2. AI_FALLBACK_PROVIDERS（JSON，兼容）。
    3. 单 provider（AI_PROVIDER）。

    返回：
        单个 provider，或由多个 provider 组成的 FallbackProvider。
    """
    specs = _read_yaml_config() or _read_fallback_specs() or _single_provider_spec()
    providers = [_build_provider(spec) for spec in specs]
    if len(providers) == 1:
        return providers[0]
    logger.info("启用 AI 多模型故障转移，顺序：%s", [p.name for p in providers])
    return FallbackProvider(providers)


def _read_yaml_config() -> list[dict[str, Any]] | None:
    """读取 yaml 多模型配置（主入口）。

    返回：
        provider 规格列表；未启用或文件缺失时返回 None。
    """
    path = getattr(settings, "AI_CONFIG_FILE", "")
    if not path or not os.path.exists(path):
        return None
    try:
        import yaml
    except ImportError:
        logger.warning("缺少 PyYAML 依赖，忽略 %s 配置。", path)
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        logger.exception("解析 %s 失败，回退到其它 AI 配置。", path)
        return None

    if not data.get("config", {}).get("enabled"):
        return None
    providers = data.get("providers", [])
    if not isinstance(providers, list) or not providers:
        raise ValueError(f"{path} 的 providers 必须为至少含一个条目的数组")
    return providers


def _read_fallback_specs() -> list[dict[str, Any]] | None:
    """读取 AI_FALLBACK_PROVIDERS（JSON，兼容旧配置）。"""
    raw = getattr(settings, "AI_FALLBACK_PROVIDERS", "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AI_FALLBACK_PROVIDERS 不是有效 JSON") from exc
    if not isinstance(data, list) or not data:
        raise ValueError("AI_FALLBACK_PROVIDERS 必须是至少含一个条目的数组")
    return data


def _single_provider_spec() -> list[dict[str, Any]]:
    """构造单 provider 规格。"""
    return [{"provider": settings.AI_PROVIDER}]


def _build_provider(spec: dict[str, Any]) -> BaseProvider:
    """根据规格构建单个 provider 实例。

    参数：
        spec: 含 provider 类型与可选 model/base_url/api_key 等字段。
    返回：
        对应 provider 实例。
    异常：
        ValueError: provider 类型未注册或缺少密钥环境变量。
    """
    provider_name = (spec.get("provider") or "").lower()
    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if provider_class is None:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"未配置的 AI provider='{provider_name}'，当前可用：{available}。"
        )
    # 透传构造函数支持的可选参数
    kwargs: dict[str, Any] = {}
    for key in ("model", "base_url", "timeout", "max_tokens"):
        if spec.get(key) is not None:
            kwargs[key] = spec[key]
    api_key = _resolve_api_key(spec)
    if api_key:
        kwargs["api_key"] = api_key
    return provider_class(**kwargs)


def _resolve_api_key(spec: dict[str, Any]) -> str:
    """解析 provider 的 API 密钥。

    支持三种写法：
    1. api_key_env：指定环境变量名（推荐）。
    2. api_key 形如 ${VAR}：从环境变量引用。
    3. api_key：直接给值。

    返回：
        解析后的密钥；未提供时返回空字符串。
    """
    api_key = spec.get("api_key")
    api_key_env = spec.get("api_key_env")
    if api_key_env:
        return _read_env(api_key_env)
    if api_key and str(api_key).startswith("${") and str(api_key).endswith("}"):
        return _read_env(str(api_key)[2:-1])
    return api_key or ""


def _read_env(name: str) -> str:
    """读取环境变量，缺失时抛出清晰错误。

    参数：
        name: 环境变量名。
    返回：
        环境变量值。
    异常：
        ValueError: 环境变量未设置。
    """
    value = os.getenv(name, "")
    if not value:
        raise ValueError(f"缺少环境变量 {name}，请在 .env 中配置该服务商的 API Key。")
    return value


def get_embedding_provider() -> BaseEmbeddingProvider:
    """获取当前配置的 embedding provider。

    优先级：
    1. yaml 配置（embeddings 段）。
    2. 单 provider 环境变量（AI_EMBEDDING_PROVIDER）。

    返回：
        embedding provider 实例。
    异常：
        ValueError: 未配置可用的 embedding provider。
    """
    spec = _read_embedding_yaml() or _single_embedding_spec()
    provider_name = (spec.get("provider") or "").lower()
    provider_class = EMBEDDING_PROVIDER_REGISTRY.get(provider_name)
    if provider_class is None:
        available = ", ".join(EMBEDDING_PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"未配置的 embedding provider='{provider_name}'，当前可用：{available}。"
            "请在 ai_config.yaml 的 embeddings 段配置，或在 .env 设置 AI_EMBEDDING_PROVIDER。"
        )
    kwargs: dict[str, Any] = {}
    for key in ("model", "base_url", "timeout"):
        if spec.get(key) is not None:
            kwargs[key] = spec[key]
    api_key = _resolve_api_key(spec)
    if api_key:
        kwargs["api_key"] = api_key
    return provider_class(**kwargs)


def _read_embedding_yaml() -> dict[str, Any] | None:
    """读取 yaml 配置中的 embeddings 段。

    返回：
        embedding 规格字典；未启用或缺失时返回 None。
    """
    path = getattr(settings, "AI_CONFIG_FILE", "")
    if not path or not os.path.exists(path):
        return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        logger.exception("解析 %s 失败，无法读取 embedding 配置。", path)
        return None
    if not data.get("config", {}).get("enabled"):
        return None
    embedding = data.get("embeddings")
    if not isinstance(embedding, dict) or not embedding.get("provider"):
        return None
    return embedding


def _single_embedding_spec() -> dict[str, Any]:
    """构造单 embedding provider 规格（兼容环境变量配置）。"""
    provider = getattr(settings, "AI_EMBEDDING_PROVIDER", "") or "qwen"
    return {"provider": provider}
