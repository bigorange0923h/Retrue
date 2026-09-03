"""Mock 训练解析器的口述训练回归测试。"""

from django.test import SimpleTestCase

from apps.ai.providers.mock import MockProvider


class MockTrainingParseTests(SimpleTestCase):
    def test_parses_chinese_sets_before_exercise_and_feedback(self) -> None:
        result = MockProvider().parse_training_text(
            "黄伟成今天做了三组臀桥,每组10次,自己做完感觉还行 没有以前累了"
        )

        self.assertEqual(result["exercises"], [{
            "exercise_name": "臀桥",
            "activity_type": "exercise",
            "sets": 3,
            "reps": 10,
            "duration_seconds": None,
            "weight": "",
            "note": "",
        }])
        self.assertEqual(result["customer_feedback"], "还行 没有以前累了")

    def test_parses_sets_in_following_clause_and_feedback(self) -> None:
        result = MockProvider().parse_training_text(
            "阳峥嵘练了深蹲,有5组每组10次,做完之后感觉腿有些酸 没有其他不良反应"
        )

        self.assertEqual(result["exercises"][0]["exercise_name"], "深蹲")
        self.assertEqual(result["exercises"][0]["sets"], 5)
        self.assertEqual(result["exercises"][0]["reps"], 10)
        self.assertEqual(result["customer_feedback"], "腿有些酸 没有其他不良反应")
