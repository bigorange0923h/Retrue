"""AI provider 故障转移（Fallback）。

将多个 provider 组合为一个，按配置顺序依次调用；
某个 provider 网络/调用失败时自动切换到下一个可用 provider，
实现多模型容灾。
"""

from __future__ import annotations

import logging
import threading
import time

from apps.ai.providers.base import AIProviderError, BaseProvider

logger = logging.getLogger(__name__)


class ProviderHealthRegistry:
    """记录进程内聊天模型的连续失败次数与熔断窗口。

    状态以 provider 展示名为键保存，因此即使每次请求重新构建
    ``FallbackProvider``，同一 Django 进程内的熔断状态仍会持续生效。
    """

    def __init__(self) -> None:
        """初始化线程安全的健康状态存储。"""
        self._states: dict[str, dict[str, float | int]] = {}
        self._lock = threading.Lock()

    def is_available(self, name: str) -> bool:
        """判断模型当前是否允许调用，熔断窗口到期后自动恢复探测。"""
        with self._lock:
            state = self._states.get(name, {})
            return time.monotonic() >= float(state.get("open_until", 0))

    def record_success(self, name: str) -> None:
        """记录成功调用并清空该模型的失败状态。"""
        with self._lock:
            self._states.pop(name, None)

    def record_failure(self, name: str, threshold: int, cooldown_seconds: int) -> bool:
        """记录失败；达到阈值时开启熔断并返回 True。"""
        with self._lock:
            state = self._states.setdefault(name, {"failures": 0, "open_until": 0})
            state["failures"] = int(state["failures"]) + 1
            if int(state["failures"]) < threshold:
                return False
            state["open_until"] = time.monotonic() + cooldown_seconds
            state["failures"] = 0
            return True


provider_health = ProviderHealthRegistry()


class FallbackProvider(BaseProvider):
    """多 provider 故障转移组合器。

    内部持有按优先级排序的 provider 列表。调用时依次尝试，
    单个 provider 抛出 AIProviderError 时记录日志并切换到下一个；
    全部失败时抛出最后一个错误。
    """

    name = "fallback"

    def __init__(
        self,
        providers: list[BaseProvider],
        failure_threshold: int = 3,
        cooldown_seconds: int = 300,
    ) -> None:
        """初始化故障转移组合器。

        参数：
            providers: 按优先级排序的 provider 实例列表（优先使用靠前者）。
            failure_threshold: 单个模型连续失败多少次后熔断。
            cooldown_seconds: 熔断后跳过该模型的秒数。
        """
        if not providers:
            raise ValueError("FallbackProvider 需要至少一个 provider")
        if failure_threshold < 1 or cooldown_seconds < 1:
            raise ValueError("故障转移的失败阈值和熔断时长必须大于 0")
        self._providers = providers
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds

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

    def chat(self, prompt: str, system: str | None = None) -> str:
        """通用对话，依次尝试各 provider 并支持故障转移。

        参数：
            prompt: 用户侧消息。
            system: 可选的系统提示。
        返回：
            文本回答。
        异常：
            AIProviderError: 所有 provider 均失败时抛出。
        """
        return self._try_all("chat", prompt, system)

    def parse_assessment_text(self, text: str) -> dict:
        return self._try_all("parse_assessment_text", text)

    def parse_followup_text(self, text: str) -> dict:
        return self._try_all("parse_followup_text", text)

    def parse_training_revision_text(self, text: str) -> dict:
        return self._try_all("parse_training_revision_text", text)

    def _try_all(self, method: str, payload, system: str | None = None):
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
            if not provider_health.is_available(provider.name):
                errors.append(f"{provider.name}: 熔断中")
                logger.info("AI provider %s 正处于熔断窗口，跳过本次调用。", provider.name)
                continue
            try:
                result = (
                    provider.chat(payload, system)
                    if method == "chat"
                    else getattr(provider, method)(payload)
                )
                provider_health.record_success(provider.name)
                return result
            except AIProviderError as exc:
                errors.append(f"{provider.name}: {exc}")
                self._record_failure(provider.name, exc)
            except Exception as exc:  # noqa: BLE001 - 任何异常都应触发切换
                errors.append(f"{provider.name}: {exc}")
                self._record_failure(provider.name, exc)
        raise AIProviderError(
            "所有 AI provider 均调用失败：\n" + "\n".join(errors)
        )

    def _record_failure(self, name: str, error: Exception) -> None:
        """记录失败并在达到阈值后打开该模型的熔断窗口。"""
        opened = provider_health.record_failure(
            name, self._failure_threshold, self._cooldown_seconds
        )
        if opened:
            logger.warning(
                "AI provider %s 已连续失败 %s 次，未来 %s 秒直接切换备用模型。",
                name,
                self._failure_threshold,
                self._cooldown_seconds,
            )
        else:
            logger.warning("AI provider %s 调用失败，尝试下一个。错误：%s", name, error)
