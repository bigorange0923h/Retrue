"""AI provider 故障转移（Fallback）。

将多个 provider 组合为一个，按配置顺序依次调用；
某个 provider 网络/调用失败时自动切换到下一个可用 provider，
实现多模型容灾。
"""

from __future__ import annotations

import logging

from apps.ai.providers.base import AIProviderError, BaseProvider

logger = logging.getLogger(__name__)


class FallbackProvider(BaseProvider):
    """多 provider 故障转移组合器。

    内部持有按优先级排序的 provider 列表。调用时依次尝试，
    单个 provider 抛出 AIProviderError 时记录日志并切换到下一个；
    全部失败时抛出最后一个错误。
    """

    name = "fallback"

    def __init__(self, providers: list[BaseProvider]) -> None:
        """初始化故障转移组合器。

        参数：
            providers: 按优先级排序的 provider 实例列表（优先使用靠前者）。
        """
        if not providers:
            raise ValueError("FallbackProvider 需要至少一个 provider")
        self._providers = providers

    def parse_training_text(self, text: str) -> dict:
        """解析训练文本，依次尝试各 provider。

        参数：
            text: 自然语言训练描述。
        返回：
            结构化草稿字典。
        异常：
            AIProviderError: 所有 provider 均失败时抛出。
        """
        return self._try_all("parse_training_text", text)

    def prepare_lesson(self, summary: dict) -> dict:
        """生成备课建议，依次尝试各 provider。

        参数：
            summary: 客户历史汇总。
        返回：
            备课建议字典。
        异常：
            AIProviderError: 所有 provider 均失败时抛出。
        """
        return self._try_all("prepare_lesson", summary)

    def _try_all(self, method: str, payload) -> dict:
        """按顺序调用各 provider 的指定方法，实现故障转移。

        参数：
            method: 要调用的 provider 方法名。
            payload: 传给该方法的参数。
        返回：
            首个成功 provider 的返回值。
        异常：
            AIProviderError: 所有 provider 均失败时抛出最后一个错误。
        """
        errors = []
        for provider in self._providers:
            try:
                return getattr(provider, method)(payload)
            except AIProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
                logger.warning("AI provider %s 调用失败，尝试下一个。错误：%s", provider.name, exc)
            except Exception as exc:  # noqa: BLE001 - 任何异常都应触发切换
                errors.append(f"{provider.name}: {exc}")
                logger.exception("AI provider %s 调用异常，尝试下一个。", provider.name)
        raise AIProviderError(
            "所有 AI provider 均调用失败：\n" + "\n".join(errors)
        )
