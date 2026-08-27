"""AI provider 工厂。

根据配置（settings.AI_PROVIDER）返回对应的 provider 实例。
当前内置 MockProvider；真实服务商（openai/dashscope）为预留，
接入时实现对应 provider 并注册到 PROVIDER_REGISTRY。
"""

from __future__ import annotations

from django.conf import settings

from apps.ai.providers.base import BaseProvider
from apps.ai.providers.mock import MockProvider

# provider 注册表：名称 -> 类
# 新增真实服务商时在此注册。
PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "mock": MockProvider,
}


def get_provider() -> BaseProvider:
    """获取当前配置的 AI provider 实例。

    按 settings.AI_PROVIDER 选择 provider。配置了未实现的服务商时，
    抛出清晰错误提示，避免静默回退到 mock。

    返回：
        当前配置的 provider 实例。
    异常：
        ValueError: 配置了未知或未实现的 AI provider。
    """
    name = settings.AI_PROVIDER
    provider_class = PROVIDER_REGISTRY.get(name)
    if provider_class is None:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"未配置的 AI_PROVIDER='{name}'，当前可用：{available}。"
            f"请检查 .env 中的 AI_PROVIDER 配置。"
        )
    return provider_class()
