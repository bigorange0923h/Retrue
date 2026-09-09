"""ai：风险提醒规则（nrs_high_v1）单元测试。

覆盖：持续高位、明显改善、明显加重、缺值、非法范围与重复触发去重。
约束：只验证可计算证据与提醒等级/建议动作；不验证新的医学阈值。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import RiskAction, RiskAlert, RiskLevel
from apps.ai.services.risk import detect_risk
from apps.customers.models import Customer
from apps.training.models import TrainingRecord

User = get_user_model()


class RiskRuleTests(TestCase):
    """nrs_high_v1 风险规则测试。"""

    def setUp(self) -> None:
        """准备康复师与客户。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

    def _add_record(self, training_date: str, feedback: str) -> TrainingRecord:
        """创建一条带反馈的训练记录。"""
        return TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date=training_date,
            customer_feedback=feedback,
        )

    def _detect(self) -> RiskAlert | None:
        """调用风险检测。"""
        return detect_risk(self.therapist, self.customer.id)

    def test_sustained_high_nrs_triggers_high(self) -> None:
        """8→8 持续高位触发高风险，规则代码可追踪。"""
        self._add_record("2026-08-25", "左膝疼痛 NRS 8")
        self._add_record("2026-08-26", "左膝疼痛 NRS 8")
        alert = self._detect()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.risk_level, RiskLevel.HIGH)
        self.assertEqual(alert.suggested_action, RiskAction.PAUSE)
        self.assertEqual(alert.rule_code, "nrs_high_v1")
        self.assertNotIn("连续未明显改善", alert.evidence)

    def test_obvious_improvement_not_reported_as_continuous(self) -> None:
        """旧 8→新 1 属明显改善：不输出“连续未明显改善”，降为待人工复核。"""
        self._add_record("2026-08-25", "左膝疼痛 NRS 8")
        self._add_record("2026-08-26", "左膝疼痛 NRS 1")
        alert = self._detect()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.risk_level, RiskLevel.MEDIUM)
        self.assertEqual(alert.suggested_action, RiskAction.REVIEW)
        self.assertNotIn("连续未明显改善", alert.evidence)
        self.assertIn("已低于 6", alert.evidence)

    def test_worsening_from_low_to_high_triggers_high(self) -> None:
        """旧 1→新 8 属明显加重，触发高风险。"""
        self._add_record("2026-08-25", "左膝疼痛 NRS 1")
        self._add_record("2026-08-26", "左膝疼痛 NRS 8")
        alert = self._detect()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.risk_level, RiskLevel.HIGH)
        self.assertEqual(alert.suggested_action, RiskAction.PAUSE)

    def test_missing_score_does_not_claim_continuity(self) -> None:
        """评分缺值时无足够证据：不创建提醒。"""
        self._add_record("2026-08-25", "今天训练状态尚可")  # 无 NRS
        self._add_record("2026-08-26", "左膝疼痛 NRS 8")  # 仅一条有评分
        self.assertIsNone(self._detect())

    def test_out_of_range_score_ignored(self) -> None:
        """NRS 超出 0-10 视为非法，不计入评分。"""
        self._add_record("2026-08-25", "左膝疼痛 NRS 15")  # 越界
        self._add_record("2026-08-26", "左膝疼痛 NRS 8")
        self.assertIsNone(self._detect())

    def test_repeated_detect_does_not_duplicate_unconfirmed_alert(self) -> None:
        """同一规则未确认提醒不重复创建（去重）。"""
        self._add_record("2026-08-25", "左膝疼痛 NRS 7")
        self._add_record("2026-08-26", "左膝疼痛 NRS 6")
        first = self._detect()
        self.assertIsNotNone(first)
        second = self._detect()
        self.assertEqual(second.id, first.id)
        self.assertEqual(RiskAlert.objects.filter(rule_code="nrs_high_v1").count(), 1)

    def test_below_threshold_does_not_trigger(self) -> None:
        """最近评分均低于 6 不触发提醒。"""
        self._add_record("2026-08-25", "左膝疼痛 NRS 3")
        self._add_record("2026-08-26", "左膝疼痛 NRS 4")
        self.assertIsNone(self._detect())
