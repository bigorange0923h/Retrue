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

    def test_parses_spoken_sets_and_each_set_count_with_ge_unit(self) -> None:
        """“做了10组、每组12个”必须预填为组数与每组次数。"""
        result = MockProvider().parse_training_text("黄伟成 今天做了臀桥10组 每组12个")

        self.assertEqual(len(result["exercises"]), 1)
        bridge = result["exercises"][0]
        self.assertIsNone(result["customer_hint"])
        self.assertEqual(bridge["exercise_name"], "臀桥")
        self.assertEqual(bridge["activity_type"], "exercise")
        self.assertEqual(bridge["sets"], 10)
        self.assertEqual(bridge["reps"], 12)

    def test_normalizes_explicit_per_set_ge_quantity_from_provider(self) -> None:
        """提供方把“每组 12 个”写入 quantity 时，也必须安全归入每组次数。"""
        from apps.ai.schemas.training import TrainingDraft

        result = TrainingDraft.model_validate(
            {
                "exercises": [
                    {"exercise_name": "臀桥", "sets": 10, "quantity": 12, "unit": "个"},
                ]
            }
        )
        bridge = result.exercises[0]
        self.assertEqual(bridge.reps, 12)
        self.assertIsNone(bridge.quantity)
        self.assertEqual(bridge.unit, "")

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
