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
            "quantity": None,
            "unit": "",
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

    def test_parses_massage_quantity_not_exercise_sets(self) -> None:
        """按摩以数量为单位：quantity=1、unit=次，不套用 sets/reps（F03）。"""
        result = MockProvider().parse_training_text("李雷今天做了康复按摩1次,整体感觉放松")

        massage = result["exercises"][0]
        self.assertEqual(massage["exercise_name"], "康复按摩")
        self.assertEqual(massage["activity_type"], "massage")
        self.assertEqual(massage["quantity"], 1)
        self.assertEqual(massage["unit"], "次")
        self.assertIsNone(massage["sets"])
        self.assertIsNone(massage["reps"])

    def test_parses_therapy_quantity(self) -> None:
        """治疗以数量为单位：quantity=2、unit=次（F03）。"""
        result = MockProvider().parse_training_text("李雷今天做了康复治疗2次")

        therapy = result["exercises"][0]
        self.assertEqual(therapy["exercise_name"], "康复治疗")
        self.assertEqual(therapy["activity_type"], "therapy")
        self.assertEqual(therapy["quantity"], 2)
        self.assertEqual(therapy["unit"], "次")
