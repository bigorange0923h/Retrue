"""评估 / 训练修订 / 随访草稿服务与模型意图分类测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft, AiDraftStatus, AiDraftType
from apps.ai.orchestration.intent import classify_intent
from apps.ai.services import domain_drafts
from apps.assessments.models import Assessment, AssessmentStatus
from apps.customers.models import Customer
from apps.followups.models import FollowUpStatus, FollowUpTask
from apps.training.models import TrainingRecord

User = get_user_model()


@override_settings(AI_CONFIG_FILE="", AI_PROVIDER="mock")
class DomainDraftTests(APITestCase):
    """领域草稿（评估/训练修订/随访）测试。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")

    def test_parse_assessment_draft(self) -> None:
        """评估草稿解析为 pending，不直接创建评估。"""
        draft = domain_drafts.parse_assessment_draft(
            self.therapist, "客户主诉右膝疼痛，希望恢复行走能力", customer_id=self.customer.id
        )
        self.assertEqual(draft.draft_type, AiDraftType.ASSESSMENT)
        self.assertEqual(draft.status, AiDraftStatus.PENDING)
        self.assertEqual(Assessment.objects.count(), 0)

    def test_confirm_assessment_draft_creates_draft_assessment(self) -> None:
        """确认评估草稿创建正式评估（状态草稿，待评估工作台完成）。"""
        draft = domain_drafts.parse_assessment_draft(
            self.therapist, "客户主诉右膝疼痛", customer_id=self.customer.id
        )
        confirmed = domain_drafts.confirm_assessment_draft(
            self.therapist,
            draft.id,
            {"assessment_type": "initial", "assessment_date": "2026-09-01", "chief_complaint": "右膝疼痛"},
            self.customer.id,
            idempotency_key="confirm-assessment-1",
        )
        self.assertEqual(confirmed.status, AiDraftStatus.CONFIRMED)
        assessment = Assessment.objects.get(id=confirmed.assessment_id)
        self.assertEqual(assessment.status, AssessmentStatus.DRAFT)
        self.assertEqual(assessment.chief_complaint, "右膝疼痛")

    def test_confirm_followup_draft_creates_followup(self) -> None:
        """确认随访草稿创建正式随访待办。"""
        draft = domain_drafts.parse_followup_draft(
            self.therapist, "下周复查一下恢复情况", customer_id=self.customer.id
        )
        confirmed = domain_drafts.confirm_followup_draft(
            self.therapist,
            draft.id,
            {"followup_type": "review", "due_date": "2026-09-08", "content": "复查恢复情况"},
            self.customer.id,
        )
        self.assertEqual(confirmed.status, AiDraftStatus.CONFIRMED)
        followup = FollowUpTask.objects.get(id=confirmed.followup_id)
        self.assertEqual(followup.status, FollowUpStatus.PENDING)
        self.assertEqual(followup.followup_type, "review")

    def test_confirm_training_revision_updates_record(self) -> None:
        """确认训练修订草稿更新目标训练记录。"""
        record = TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date="2026-08-30",
            customer_feedback="旧反馈",
        )
        draft = domain_drafts.parse_training_revision_draft(
            self.therapist,
            "训练记录有误，客户反馈应该改成感觉良好",
            customer_id=self.customer.id,
            target_record_id=record.id,
        )
        confirmed = domain_drafts.confirm_training_revision_draft(
            self.therapist,
            draft.id,
            {"customer_feedback": "感觉良好"},
            self.customer.id,
        )
        record.refresh_from_db()
        self.assertEqual(confirmed.status, AiDraftStatus.CONFIRMED)
        self.assertEqual(record.customer_feedback, "感觉良好")

    def test_draft_not_written_before_confirmation(self) -> None:
        """草稿确认前不写入任何正式记录。"""
        domain_drafts.parse_assessment_draft(
            self.therapist, "客户主诉右膝疼痛", customer_id=self.customer.id
        )
        domain_drafts.parse_followup_draft(
            self.therapist, "下周复查", customer_id=self.customer.id
        )
        self.assertEqual(Assessment.objects.count(), 0)
        self.assertEqual(FollowUpTask.objects.count(), 0)

    def test_cancel_domain_draft(self) -> None:
        """取消领域草稿不写正式记录。"""
        draft = domain_drafts.parse_assessment_draft(
            self.therapist, "客户主诉右膝疼痛", customer_id=self.customer.id
        )
        cancelled = domain_drafts.cancel_domain_draft(self.therapist, draft.id)
        self.assertEqual(cancelled.status, AiDraftStatus.CANCELLED)
        self.assertEqual(Assessment.objects.count(), 0)


@override_settings(AI_CONFIG_FILE="", AI_PROVIDER="mock")
class IntentModelTests(APITestCase):
    """模型意图分类补充测试。"""

    def test_new_intents_classified_by_rule(self) -> None:
        """评估 / 训练修订 / 随访意图可被确定性规则识别。"""
        self.assertEqual(classify_intent("给客户做一次首评", customer_bound=False).intent, "customer_lookup")
        self.assertEqual(
            classify_intent("做一次评估", customer_bound=True).intent, "assessment"
        )
        self.assertEqual(
            classify_intent("修改一下训练记录", customer_bound=True).intent, "training_revision"
        )
        self.assertEqual(
            classify_intent("安排一次随访", customer_bound=True).intent, "followup"
        )

    def test_model_classification_returns_none_on_invalid(self) -> None:
        """模型返回非法意图时安全回落 None。"""
        from apps.ai.orchestration.intent import classify_intent_with_model

        # mock provider 的 chat 返回固定文本，无法解析为合法 JSON 意图 → None
        result = classify_intent_with_model("你好")
        self.assertIsNone(result)
