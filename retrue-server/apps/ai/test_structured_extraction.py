"""训练抽取的原文依据和共用结构校验回归。"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ai.schemas.training import TrainingDraft
from apps.ai.services.structured_extraction import ExtractionValidationError, validate_candidate
from apps.ai.services.training_parser import parse_training_input
from apps.ai.services.training_evidence import review_training_evidence


class StructuredCandidateTests(SimpleTestCase):
    """候选结构错误须提供稳定分类且不泄露模型原文。"""

    def test_invalid_shape_is_classified(self) -> None:
        with self.assertRaises(ExtractionValidationError) as caught:
            validate_candidate(TrainingDraft, ["不是对象"])
        self.assertEqual(caught.exception.code, "invalid_shape")

    def test_invalid_schema_reports_only_field_path(self) -> None:
        with self.assertRaises(ExtractionValidationError) as caught:
            validate_candidate(TrainingDraft, {"exercises": "敏感原文"})
        self.assertEqual(caught.exception.code, "schema_invalid")
        self.assertIn("exercises", str(caught.exception))
        self.assertNotIn("敏感原文", str(caught.exception))


class TrainingEvidenceTests(SimpleTestCase):
    """只有具备当前项目原文依据的数量进入待确认草稿。"""

    def test_numbers_require_matching_units(self) -> None:
        parsed = TrainingDraft(exercises=[{"exercise_name": "臀桥", "sets": 12, "reps": 3, "duration_seconds": 12}])
        review_training_evidence(parsed, "今天臀桥 3 组，每组 12 次")
        self.assertIsNone(parsed.exercises[0].sets)
        self.assertIsNone(parsed.exercises[0].reps)
        self.assertIsNone(parsed.exercises[0].duration_seconds)

    def test_chinese_number_must_not_match_inside_larger_number(self) -> None:
        parsed = TrainingDraft(exercises=[{"exercise_name": "臀桥", "sets": 3}])
        review_training_evidence(parsed, "今天臀桥十三组")
        self.assertIsNone(parsed.exercises[0].sets)

    def test_conflicting_doses_are_not_selected_automatically(self) -> None:
        parsed = TrainingDraft(exercises=[{"exercise_name": "臀桥", "sets": 3}])
        issues = review_training_evidence(parsed, "今天臀桥3组还是5组记不清")
        self.assertIsNone(parsed.exercises[0].sets)
        self.assertIn("unsupported_number", [issue["code"] for issue in issues])

    def test_unpunctuated_exercises_do_not_share_numbers(self) -> None:
        parsed = TrainingDraft(exercises=[{"exercise_name": "臀桥", "sets": 4}, {"exercise_name": "深蹲", "sets": 4}])
        review_training_evidence(parsed, "今天臀桥3组和深蹲4组")
        self.assertIsNone(parsed.exercises[0].sets)
        self.assertEqual(parsed.exercises[1].sets, 4)
        parsed.exercises[1].sets = 3
        review_training_evidence(parsed, "今天臀桥3组和深蹲4组")
        self.assertIsNone(parsed.exercises[1].sets)

    def test_negated_or_planned_dose_requires_review(self) -> None:
        for source in ("今天没有做臀桥3组", "下次计划臀桥3组"):
            with self.subTest(source=source):
                parsed = TrainingDraft(exercises=[{"exercise_name": "臀桥", "sets": 3}])
                issues = review_training_evidence(parsed, source)
                self.assertIsNone(parsed.exercises[0].sets)
                self.assertIn("action_needs_review", [issue["code"] for issue in issues])

    def test_unknown_exercise_cannot_borrow_source_numbers(self) -> None:
        parsed = TrainingDraft(exercises=[{"exercise_name": "深蹲", "sets": 3}])
        issues = review_training_evidence(parsed, "今天臀桥3组")
        self.assertIsNone(parsed.exercises[0].sets)
        self.assertIn("name_needs_review", [issue["code"] for issue in issues])

    def test_duration_keeps_explicit_equivalent_values(self) -> None:
        for description in ("一分钟三十秒", "1.5分钟", "90秒"):
            with self.subTest(description=description):
                parsed = TrainingDraft(exercises=[{"exercise_name": "静蹲", "duration_seconds": 90}])
                review_training_evidence(parsed, f"今天静蹲{description}")
                self.assertEqual(parsed.exercises[0].duration_seconds, 90)

    def test_weight_must_not_match_inside_larger_number(self) -> None:
        parsed = TrainingDraft(exercises=[{"exercise_name": "臀桥", "weight": "5 kg"}])
        review_training_evidence(parsed, "今天臀桥负重15kg")
        self.assertEqual(parsed.exercises[0].weight, "")

    @patch("apps.ai.services.training_parser.get_provider")
    def test_unsupported_number_is_cleared_without_losing_other_fields(self, get_provider) -> None:
        get_provider.return_value.parse_training_text.return_value = {
            "exercises": [{"exercise_name": "臀桥", "sets": 7, "reps": 12}],
            "customer_feedback": "膝盖有点疼",
        }
        parsed = parse_training_input("今天做了臀桥 3 组，每组 12 次，膝盖有点疼")
        self.assertIsNone(parsed.exercises[0].sets)
        self.assertEqual(parsed.exercises[0].reps, 12)
        self.assertEqual(parsed.customer_feedback, "膝盖有点疼")
        self.assertEqual(parsed._review_issues[0]["code"], "unsupported_number")

    @patch("apps.ai.services.training_parser.get_provider")
    def test_other_exercise_number_does_not_support_current_exercise(self, get_provider) -> None:
        get_provider.return_value.parse_training_text.return_value = {
            "exercises": [
                {"exercise_name": "臀桥", "sets": 3},
                {"exercise_name": "深蹲", "sets": 3},
            ],
        }
        parsed = parse_training_input("今天做了臀桥 3 组，深蹲 4 组")
        self.assertEqual(parsed.exercises[0].sets, 3)
        self.assertIsNone(parsed.exercises[1].sets)

    @patch("apps.ai.services.training_parser.get_provider")
    def test_missing_date_is_marked_as_default(self, get_provider) -> None:
        get_provider.return_value.parse_training_text.return_value = {
            "exercises": [{"exercise_name": "臀桥"}],
        }
        parsed = parse_training_input("做了臀桥")
        self.assertEqual(parsed.training_date, date.today().isoformat())
        self.assertIn("date_needs_review", [issue["code"] for issue in parsed._review_issues])

    @patch("apps.ai.services.training_parser.get_provider")
    def test_clear_weight_without_source(self, get_provider) -> None:
        get_provider.return_value.parse_training_text.return_value = {
            "exercises": [{"exercise_name": "臀桥", "weight": "5 kg"}],
        }
        parsed = parse_training_input("今天做了臀桥")
        self.assertEqual(parsed.exercises[0].weight, "")
        self.assertIn("unsupported_weight", [issue["code"] for issue in parsed._review_issues])

    @patch("apps.ai.services.training_parser.get_provider")
    def test_chinese_number_and_minute_conversion_remain_available(self, get_provider) -> None:
        get_provider.return_value.parse_training_text.return_value = {
            "exercises": [{"exercise_name": "靠墙静蹲", "sets": 21, "duration_seconds": 90, "weight": "5 kg"}],
        }
        parsed = parse_training_input("今天做了靠墙静蹲二十一组，每组 1 分 30 秒，负重 5 公斤")
        self.assertEqual(parsed.exercises[0].sets, 21)
        self.assertEqual(parsed.exercises[0].duration_seconds, 90)
        self.assertEqual(parsed.exercises[0].weight, "5 kg")

    @patch("apps.ai.services.training_parser.get_provider")
    def test_unsupported_customer_hint_is_not_used(self, get_provider) -> None:
        get_provider.return_value.parse_training_text.return_value = {
            "customer_hint": "张三",
            "exercises": [{"exercise_name": "臀桥"}],
        }
        parsed = parse_training_input("今天做了臀桥")
        self.assertIsNone(parsed.customer_hint)
        self.assertIn("unsupported_customer_hint", [issue["code"] for issue in parsed._review_issues])
