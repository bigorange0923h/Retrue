"""FallbackProvider 故障转移单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.ai.providers.base import AIProviderError
from apps.ai.providers.fallback import FallbackProvider, provider_health


def make_provider(name: str, result: dict | None = None, error: Exception | None = None) -> MagicMock:
    """构造一个可配置成功/失败的 provider mock。"""
    provider = MagicMock()
    provider.name = name
    if error is not None:
        provider.parse_training_text.side_effect = error
        provider.prepare_lesson.side_effect = error
    else:
        provider.parse_training_text.return_value = result or {}
        provider.prepare_lesson.return_value = result or {}
    return provider


class FallbackProviderTests(SimpleTestCase):
    """故障转移组合器测试。"""

    def setUp(self) -> None:
        """隔离进程级熔断状态，避免测试之间互相影响。"""
        provider_health._states.clear()  # noqa: SLF001 - 测试需要重置共享状态

    def test_uses_first_provider_on_success(self) -> None:
        """首个 provider 成功时直接使用，不调用后续。"""
        first = make_provider("a", {"ok": 1})
        second = make_provider("b", {"ok": 2})
        combo = FallbackProvider([first, second])
        result = combo.parse_training_text("text")
        self.assertEqual(result, {"ok": 1})
        second.parse_training_text.assert_not_called()

    def test_switches_to_next_on_failure(self) -> None:
        """首个失败时自动切换到下一个。"""
        first = make_provider("a", error=AIProviderError("网络错误"))
        second = make_provider("b", {"ok": 2})
        combo = FallbackProvider([first, second])
        result = combo.parse_training_text("text")
        self.assertEqual(result, {"ok": 2})

    def test_prepare_lesson_fallback(self) -> None:
        """prepare_lesson 同样支持故障转移。"""
        first = make_provider("a", error=AIProviderError("超时"))
        second = make_provider("b", {"checks": ["x"]})
        combo = FallbackProvider([first, second])
        result = combo.prepare_lesson({"summary": {}})
        self.assertEqual(result, {"checks": ["x"]})

    def test_all_fail_raises(self) -> None:
        """所有 provider 均失败时抛出错误。"""
        first = make_provider("a", error=AIProviderError("失败1"))
        second = make_provider("b", error=AIProviderError("失败2"))
        combo = FallbackProvider([first, second])
        with self.assertRaises(AIProviderError) as ctx:
            combo.parse_training_text("text")
        self.assertIn("失败1", str(ctx.exception))
        self.assertIn("失败2", str(ctx.exception))

    def test_empty_providers_raises(self) -> None:
        """无 provider 时抛出 ValueError。"""
        with self.assertRaises(ValueError):
            FallbackProvider([])

    def test_non_ai_error_also_triggers_switch(self) -> None:
        """非 AIProviderError 异常也触发切换。"""
        first = make_provider("a", error=RuntimeError("连接重置"))
        second = make_provider("b", {"ok": 3})
        combo = FallbackProvider([first, second])
        self.assertEqual(combo.parse_training_text("text"), {"ok": 3})

    def test_circuit_breaker_skips_provider_after_threshold(self) -> None:
        """连续失败达到阈值后，后续请求直接跳过故障模型。"""
        first = make_provider("primary-circuit", error=AIProviderError("超时"))
        second = make_provider("backup-circuit", {"ok": 4})
        combo = FallbackProvider([first, second], failure_threshold=2, cooldown_seconds=300)

        combo.parse_training_text("first")
        combo.parse_training_text("second")
        combo.parse_training_text("third")

        self.assertEqual(first.parse_training_text.call_count, 2)
        self.assertEqual(second.parse_training_text.call_count, 3)
