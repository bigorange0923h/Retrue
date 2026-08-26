"""AI provider 工厂。

根据配置返回当前使用的 provider 实例。当前固定返回 MockProvider，
待真实服务商确定后按环境变量选择。
"""

from __future__ import annotations

from apps.ai.providers.base import BaseProvider
from apps.ai.providers.mock import MockProvider


def get_provider() -> BaseProvider:
    """获取当前 AI provider 实例。

    返回：
        当前配置的 provider 实例。
    """
    return MockProvider()
