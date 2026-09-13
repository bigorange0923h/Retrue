"""AI 草稿 schema 与解析提示词的契约回归测试。

背景：提示词（``parse_system`` 及各 ``parse_*.txt``）明确要求模型对无法识别的
字段输出 null/空值，而草稿 schema 曾用非空 ``str`` 承接，键存在且为 ``null``
时 Pydantic 的 ``default`` 不生效，导致草稿校验失败（训练补记回合直接 500）。
本文件钉住各类草稿对“可空契约”的承接行为。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.ai.prompts.loader import render_prompt
from apps.ai.schemas.domain import AssessmentDraft, FollowUpDraft, TrainingRevisionDraft
from apps.ai.schemas.multi_customer import MultiCustomerTrainingSplit
from apps.ai.schemas.training import TrainingDraft
from apps.ai.services.training_parser import parse_training_input


class TrainingDraftNullToleranceTests(SimpleTestCase):
    """训练草稿：模型输出包含 null 或缺少字段时，解析不报错并归一为安全默认值。"""

    def _draft_from_model_output(self) -> TrainingDraft:
        """还原真实模型对“今天做了臀桥 做了10组 每组12个”的典型输出。

        说明：模型会多输出 ``customer_name``（正确字段应为 ``customer_hint``），
        并把无负荷/单位的动作字段写成 null，同时省略 ``training_date``。
        """
        return TrainingDraft(
            customer_name="黄伟成",
            exercises=[
                {
                    "exercise_name": "臀桥",
                    "activity_type": "exercise",
                    "sets": 10,
                    "reps": 12,
                    "quantity": None,
                    "unit": None,
                    "duration_seconds": None,
                    "weight": None,
                    "note": None,
                }
            ],
            customer_feedback=None,
            therapist_observation=None,
            next_plan=None,
        )

    def test_missing_training_date_defaults_to_today(self) -> None:
        """模型省略训练日期时按解析当天补默认值。"""
        draft = self._draft_from_model_output()
        self.assertEqual(draft.training_date, date.today().isoformat())

    def test_null_training_date_defaults_to_today(self) -> None:
        """模型把训练日期输出为 null 时同样补默认值。"""
        draft = TrainingDraft(training_date=None)
        self.assertEqual(draft.training_date, date.today().isoformat())

    def test_null_text_fields_become_empty_strings(self) -> None:
        """文本字段的 null 归一到空字符串，便于前端编辑与正式写入。"""
        draft = self._draft_from_model_output()
        self.assertEqual(draft.customer_feedback, "")
        self.assertEqual(draft.therapist_observation, "")
        self.assertEqual(draft.next_plan, "")
        exercise = draft.exercises[0]
        self.assertEqual(exercise.unit, "")
        self.assertEqual(exercise.weight, "")
        self.assertEqual(exercise.note, "")

    def test_null_activity_type_defaults_to_exercise(self) -> None:
        """项目类型为 null 时按训练动作处理，避免空枚举写入正式记录。"""
        draft = TrainingDraft(exercises=[{"exercise_name": "臀桥", "activity_type": None}])
        self.assertEqual(draft.exercises[0].activity_type, "exercise")

    def test_unknown_extra_field_is_ignored(self) -> None:
        """模型偶发多输出的字段不影响草稿校验，也不会污染字段。"""
        draft = self._draft_from_model_output()
        self.assertFalse(hasattr(draft, "customer_name"))
        self.assertIsNone(draft.customer_hint)

    @patch("apps.ai.services.training_parser.get_provider")
    def test_explicit_source_quantities_override_missing_model_values(self, get_provider: Mock) -> None:
        """原文明示 10 组、每组 12 个时，模型漏填也必须按原文写入草稿。"""
        get_provider.return_value.parse_training_text.return_value = {
            "exercises": [
                {
                    "exercise_name": "臀桥",
                    "activity_type": "exercise",
                    "sets": None,
                    "reps": None,
                }
            ]
        }

        draft = parse_training_input("黄伟成 今天做了臀桥10组 每组12个")

        self.assertEqual(draft.exercises[0].sets, 10)
        self.assertEqual(draft.exercises[0].reps, 12)


class DomainDraftNullToleranceTests(SimpleTestCase):
    """评估/随访/训练修订草稿：提示词允许的 null 不使草稿校验失败。"""

    def test_assessment_draft_accepts_null_date_and_text(self) -> None:
        """评估日期与文本字段为 null 时归一为空，日期由确认流程补当天。"""
        draft = AssessmentDraft(
            assessment_type=None,
            assessment_date=None,
            chief_complaint="右膝疼痛",
            medical_history=None,
            current_status=None,
        )
        self.assertEqual(draft.assessment_type, "initial")
        self.assertEqual(draft.assessment_date, "")
        self.assertEqual(draft.medical_history, "")
        self.assertEqual(draft.current_status, "")

    def test_followup_draft_accepts_null_due_date(self) -> None:
        """提示词要求日期未提及时 due_date 必须为 null，草稿必须能承接。"""
        draft = FollowUpDraft(followup_type=None, due_date=None, content=None)
        self.assertEqual(draft.followup_type, "visit")
        self.assertEqual(draft.due_date, "")
        self.assertEqual(draft.content, "")

    def test_training_revision_draft_accepts_null_date(self) -> None:
        """训练修订草稿在模型未给出训练日期时不应校验失败。"""
        draft = TrainingRevisionDraft(training_date=None, customer_feedback=None)
        self.assertEqual(draft.training_date, "")
        self.assertEqual(draft.customer_feedback, "")


class MultiCustomerSplitNullToleranceTests(SimpleTestCase):
    """多客户拆分：提示词允许“无法确定的字段保持为空”，null 不使拆分整体失败。"""

    def _split_from_model_output(self) -> MultiCustomerTrainingSplit:
        """还原模型对“客户A今天做了深蹲10次，康复按摩1次”的可能输出。"""
        return MultiCustomerTrainingSplit(
            intent=None,
            confidence=None,
            items=[
                {
                    "sequence": 1,
                    "customer_name_hint": None,
                    "activities": [
                        {
                            "name": "深蹲",
                            "activity_type": None,
                            "sets": None,
                            "reps": 10,
                            "quantity": None,
                            "unit": None,
                            "duration": None,
                        }
                    ],
                }
            ],
        )

    def test_null_fields_are_normalized(self) -> None:
        """拆分结果中的 null 归一到安全默认值，避免整批拆分不可用。"""
        parsed = self._split_from_model_output()
        self.assertEqual(parsed.intent, "multi_customer_training_record")
        self.assertEqual(parsed.confidence, 0.0)
        item = parsed.items[0]
        self.assertEqual(item.customer_name_hint, "")
        activity = item.activities[0]
        self.assertEqual(activity.name, "深蹲")
        self.assertEqual(activity.activity_type, "exercise")
        self.assertEqual(activity.unit, "")

    def test_split_accepts_items_without_intent_and_confidence(self) -> None:
        """图内复用拆分结果时只传 items，仍应校验通过。"""
        parsed = MultiCustomerTrainingSplit(
            items=[{"sequence": 1, "customer_name_hint": "客户A", "activities": []}]
        )
        self.assertEqual(parsed.items[0].customer_name_hint, "客户A")
        self.assertEqual(parsed.items[0].activities, [])


class ParseTrainingPromptContractTests(SimpleTestCase):
    """解析提示词必须声明模型需要产出的全部顶层字段。"""

    def test_prompt_documents_top_level_fields(self) -> None:
        """提示词缺少 training_date/customer_hint 契约会让模型省略这些字段。"""
        prompt = render_prompt("parse_training_text", text="今天做了臀桥 10 组 12 次")
        self.assertIn("training_date", prompt)
        self.assertIn("customer_hint", prompt)
