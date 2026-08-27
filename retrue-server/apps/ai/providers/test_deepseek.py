"""deepseek provider 单元测试。

通过模拟 OpenAI 客户端验证 JSON 解析与 schema 校验逻辑，不发起真实网络请求。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.ai.providers.base import AIProviderError
from apps.ai.providers.deepseek import _parse_json, _pydantic_to_json_schema


@override_settings(
    AI_PROVIDER="deepseek",
    AI_API_KEY="test-key",
    AI_MODEL="deepseek-chat",
    AI_BASE_URL="",
)
class DeepSeekParseTests(SimpleTestCase):
    """测试 JSON 解析与 schema 转换。"""

    def test_parse_json_plain(self) -> None:
        """解析普通 JSON。"""
        data = _parse_json('{"a": 1}')
        self.assertEqual(data, {"a": 1})

    def test_parse_json_with_code_fence(self) -> None:
        """解析带 markdown 代码块围栏的 JSON。"""
        data = _parse_json('```json\n{"exercises": []}\n```')
        self.assertEqual(data, {"exercises": []})

    def test_parse_json_invalid_raises(self) -> None:
        """无效 JSON 抛出错误。"""
        with self.assertRaises(AIProviderError):
            _parse_json("这不是 JSON")

    def test_pydantic_to_json_schema(self) -> None:
        """Pydantic 模型转换为 JSON schema。"""
        from apps.ai.schemas.training import TrainingDraft

        schema = _pydantic_to_json_schema(TrainingDraft)
        self.assertIn("exercises", schema["properties"])
        self.assertEqual(schema["type"], "object")

    @patch("openai.OpenAI")
    def test_parse_training_text_calls_llm(self, mock_openai: MagicMock) -> None:
        """parse_training_text 调用 LLM 并返回结构化草稿。"""
        from apps.ai.providers.deepseek import DeepSeekProvider

        message = MagicMock()
        message.content = (
            '{"training_date": "2026-08-27", "customer_hint": null, '
            '"exercises": [{"exercise_name": "臀桥", "sets": 3, "reps": 12, '
            '"weight": "", "duration_seconds": null, "note": ""}], '
            '"customer_feedback": "左膝疼痛", "therapist_observation": "", "next_plan": ""}'
        )
        choice = MagicMock()
        choice.message = message
        mock_response = MagicMock()
        mock_response.choices = [choice]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        provider = DeepSeekProvider()
        result = provider.parse_training_text("今天做了臀桥 3 组 12 次")
        self.assertEqual(result["exercises"][0]["exercise_name"], "臀桥")
        self.assertEqual(result["exercises"][0]["sets"], 3)
        self.assertEqual(result["customer_feedback"], "左膝疼痛")

    @patch("openai.OpenAI")
    def test_parse_training_text_invalid_result(self, mock_openai: MagicMock) -> None:
        """LLM 返回无法通过 schema 校验时抛出错误。"""
        from apps.ai.providers.deepseek import DeepSeekProvider

        message = MagicMock()
        message.content = '{"exercises": "not-a-list"}'  # 类型错误，触发校验失败
        choice = MagicMock()
        choice.message = message
        mock_response = MagicMock()
        mock_response.choices = [choice]
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        provider = DeepSeekProvider()
        with self.assertRaises(AIProviderError):
            provider.parse_training_text("x")


@override_settings(AI_PROVIDER="deepseek", AI_API_KEY="", AI_MODEL="deepseek-chat", AI_BASE_URL="")
class DeepSeekMissingKeyTests(SimpleTestCase):
    """缺少 API key 时抛出清晰错误。"""

    def test_missing_api_key_raises(self) -> None:
        """缺少 API key 时抛出错误。"""
        from apps.ai.providers.deepseek import DeepSeekProvider

        with self.assertRaises(AIProviderError):
            DeepSeekProvider()
