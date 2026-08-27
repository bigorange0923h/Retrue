"""AI provider 工厂。

根据配置返回 provider 实例，支持两种模式：
1. 单 provider：按 settings.AI_PROVIDER 选择（兼容原行为）。
2. 多 provider 故障转移：按 settings.AI_FALLBACK_PROVIDERS（JSON 数组）
   创建多个 provider 并组合为 FallbackProvider，单一模型网络异常时自动切换。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings

from apps.ai.providers.base import AIProviderError, BaseProvider
from apps.ai.providers.deepseek import DeepSeekProvider
from apps.ai.providers.fallback import FallbackProvider
from apps.ai.providers.mock import MockProvider

logger = logging.getLogger(__name__)

# provider 注册表：名称 -> 类
# 新增真实服务商时在此注册。
PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "mock": MockProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider() -> BaseProvider:
    """获取当前配置的 AI provider 实例。

    优先使用多 provider 故障转移配置（AI_FALLBACK_PROVIDERS）；
    未配置时回退到单 provider（AI_PROVIDER）。

    返回：
        配置的 provider 实例，可能为 FallbackProvider。
    异常：
        ValueError / AIProviderError: 配置无效或缺少密钥。
    """
    fallback_specs = _read_fallback_specs()
    if fallback_specs:
        providers = [_build_provider(spec) for spec in fallback_specs]
        logger.info("启用 AI 多模型故障转移，provider 顺序：%s", [p.name for p in providers])
        return FallbackProvider(providers)

    return _build_single_provider()


def _read_fallback_specs() -> list[dict[str, Any]] | None:
    """读取多 provider 故障转移配置。

    从 settings.AI_FALLBACK_PROVIDERS（JSON 数组字符串）解析。

    返回：
        provider 规格列表；未配置时返回 None。
    """
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


def _build_single_provider() -> BaseProvider:
    """构建单 provider 实例。"""
    name = settings.AI_PROVIDER
    return _build_provider({"provider": name})


def _build_provider(spec: dict[str, Any]) -> BaseProvider:
    """根据规格构建单个 provider 实例。

    参数：
        spec: 含 provider 类型与可选 model 等字段的规格。
    返回：
        对应 provider 实例。
    异常：
        ValueError: provider 类型未注册。
    """
    provider_name = (spec.get("provider") or "").lower()
    provider_class = PROVIDER_REGISTRY.get(provider_name)
    if provider_class is None:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"未配置的 AI provider='{provider_name}'，当前可用：{available}。"
        )
    # 仅透传各 provider 构造函数支持的参数
    kwargs: dict[str, Any] = {}
    for key in ("model", "base_url", "timeout", "max_tokens"):
        if spec.get(key) is not None:
            kwargs[key] = spec[key]

    # 密钥解析：支持多种方式
    # 1. api_key 字段直接给值
    # 2. api_key 字段为 ${ENV_VAR}，从环境变量读取
    # 3. api_key_env 字段指定环境变量名
    api_key = spec.get("api_key")
    api_key_env = spec.get("api_key_env")
    if api_key_env:
        api_key = _read_env(api_key_env)
    elif api_key and str(api_key).startswith("${") and str(api_key).endswith("}"):
        api_key = _read_env(str(api_key)[2:-1])
    if api_key:
        kwargs["api_key"] = api_key

    return provider_class(**kwargs)


def _read_env(name: str) -> str:
    """读取环境变量，缺失时抛出清晰错误。

    参数：
        name: 环境变量名。
    返回：
        环境变量值。
    异常：
        ValueError: 环境变量未设置。
    """
    import os

    value = os.getenv(name, "")
    if not value:
        raise ValueError(f"缺少环境变量 {name}，请在 .env 中配置该服务商的 API Key。")
    return value
