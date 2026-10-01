"""评估录入体验的权限、依据、同草稿写入与版本冲突回归。"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft
from apps.ai.orchestration.assessment_input import validate
from apps.assessments.models import Assessment
from apps.customers.models import Customer


class AssessmentInputTests(APITestCase):
    """通过实际 API 验证候选与评估的边界，不调用真实模型。"""

    def setUp(self):
        """创建两个隔离的康复师和测试客户。"""
        self.user = get_user_model().objects.create_user(username="input_t1", password="test12345")
        self.other = get_user_model().objects.create_user(username="input_t2", password="test12345")
        self.customer = Customer.objects.create(therapist=self.user, name="测试客户 A")
        self.foreign = Customer.objects.create(therapist=self.other, name="测试客户 B")
        self.client.force_login(self.user)
        self.url = reverse("assessment-input-draft")
        self.source = "右膝下蹲疼痛 3 分，约两周前开始，想恢复上下楼。"
        self.raw = {
            "fields": [
                {"field": "chief_complaint", "value": "右膝下蹲疼痛", "evidence": "右膝下蹲疼痛 3 分"},
                {"field": "onset_description", "value": "约两周前", "evidence": "约两周前开始"},
                {"field": "rehab_goal", "value": "恢复上下楼", "evidence": "想恢复上下楼"},
            ],
            "metrics": [{
                "value": {"metric_type": "pain", "body_part": "膝", "side": "right", "context": "activity", "score": 3},
                "evidence": {key: "右膝下蹲疼痛 3 分" for key in ("metric_type", "body_part", "side", "context", "score")},
            }],
        }

    def candidate(self, **context):
        """经真实编排图生成候选，只替换模型边界。"""
        with patch("apps.ai.orchestration.assessment_input.get_provider") as provider:
            provider.return_value.chat.return_value = json.dumps(self.raw, ensure_ascii=False)
            response = self.client.post(self.url, {"customer_id": self.customer.id, "input_text": self.source, **context}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["data"]

    def assessment(self):
        """创建一份有独立生命周期的首评草稿。"""
        return Assessment.objects.create(therapist=self.user, customer=self.customer, assessment_date="2026-10-01", chief_complaint="人工填写")

    def test_candidate_does_not_create_assessment(self):
        """自然语言只产生候选；相对时间不擅自换算日期。"""
        draft = self.candidate()
        self.assertEqual(Assessment.objects.count(), 0)
        self.assertEqual(draft["metrics"][0]["value"]["score"], 3)
        self.assertNotIn("onset_date", [item["field"] for item in draft["fields"]])
        stored = AiDraft.objects.get(id=draft["id"])
        self.assertEqual(stored.status, "pending")

    @patch("apps.ai.orchestration.assessment_input.get_provider")
    def test_foreign_customer_rejected_before_model(self, provider):
        """越权输入在模型前被拒，恢复入口也不能读取。"""
        response = self.client.post(self.url, {"customer_id": self.foreign.id, "input_text": "描述"}, format="json")
        self.assertEqual(response.status_code, 400)
        provider.assert_not_called()
        self.assertIsNone(self.client.get(self.url, {"customer_id": self.foreign.id}).data["data"].get("id"))

    def test_refresh_recovers_pending_candidate(self):
        """恢复只返回同客户、类型和目标的候选。"""
        assessment = self.assessment()
        draft = self.candidate(assessment_id=assessment.id)
        response = self.client.get(self.url, {"customer_id": self.customer.id, "assessment_id": assessment.id})
        self.assertEqual(response.data["data"]["id"], draft["id"])
        other_type = self.client.get(self.url, {"customer_id": self.customer.id, "assessment_type": "reassessment"})
        self.assertIsNone(other_type.data["data"])

    def test_adopt_updates_same_assessment_and_confirms_with_save(self):
        """采用与保存同事务，不另建首评；人工修改值仍保留。"""
        assessment = self.assessment()
        draft = self.candidate(assessment_id=assessment.id)
        response = self.client.put(reverse("assessment-detail", args=[assessment.id]), {
            "expected_updated_at": assessment.updated_at.isoformat(), "ai_input_draft_ids": [draft["id"]],
            "onset_description": "约两周前", "chief_complaint": "人工修正的右膝问题", "metrics": [draft["metrics"][0]["value"]],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Assessment.objects.count(), 1)
        stored = AiDraft.objects.get(id=draft["id"])
        self.assertEqual(stored.status, "confirmed")
        self.assertEqual(stored.assessment_id, assessment.id)
        self.assertEqual(stored.confirmed_result["chief_complaint"], "人工修正的右膝问题")
        self.assertEqual(response.data["data"]["status"], "draft")

    def test_invalid_draft_rolls_back_fields_and_metrics(self):
        """伪造候选 ID 时整次更新回滚，不能只撤销候选状态。"""
        assessment = self.assessment()
        response = self.client.put(reverse("assessment-detail", args=[assessment.id]), {
            "chief_complaint": "不应写入", "ai_input_draft_ids": [999999],
            "metrics": [{"metric_type": "pain", "body_part": "膝", "score": 3}],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        assessment.refresh_from_db()
        self.assertEqual(assessment.chief_complaint, "人工填写")
        self.assertEqual(assessment.metrics.count(), 0)

    def test_version_conflict_preserves_latest(self):
        """旧窗口保存返回 409，不覆盖新值。"""
        assessment = self.assessment()
        old_version = assessment.updated_at.isoformat()
        url = reverse("assessment-detail", args=[assessment.id])
        fresh = self.client.put(url, {"chief_complaint": "另一窗口更新", "expected_updated_at": old_version}, format="json")
        self.assertEqual(fresh.status_code, 200)
        stale = self.client.put(url, {"chief_complaint": "旧窗口覆盖", "expected_updated_at": old_version}, format="json")
        self.assertEqual(stale.status_code, 409)
        assessment.refresh_from_db()
        self.assertEqual(assessment.chief_complaint, "另一窗口更新")

    def test_stale_completion_rejected(self):
        """完成请求也受版本保护，不能完成另一窗口刚修改的内容。"""
        assessment = self.assessment()
        old_version = assessment.updated_at.isoformat()
        assessment.note = "另一窗口补充"
        assessment.save()
        response = self.client.post(reverse("assessment-complete", args=[assessment.id]), {"expected_updated_at": old_version}, format="json")
        self.assertEqual(response.status_code, 409)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, "draft")

    def test_unsupported_item_degrades_without_losing_valid_fields(self):
        """缺依据单项被略过，不废掉其他可用输入，不制造正常值。"""
        self.raw["fields"].extend([
            {"field": "medication", "value": "无用药", "evidence": "想恢复上下楼"},
            {"field": ["非法字段"], "value": "无", "evidence": "无"},
        ])
        self.raw["metrics"][0]["value"]["score"] = 8
        draft = self.candidate()
        self.assertEqual(len(draft["fields"]), 3)
        self.assertEqual(draft["metrics"], [])
        self.assertTrue(draft["warnings"])

    def test_metric_does_not_borrow_other_side_score(self):
        """一项指标各属性必须来自同一局部证据，不能借用另一侧数值。"""
        self.source += "左膝疼痛 8 分。"
        self.raw["metrics"][0]["value"]["score"] = 8
        self.raw["metrics"][0]["evidence"]["score"] = "左膝疼痛 8 分"
        self.assertEqual(self.candidate()["metrics"], [])

    @patch("apps.ai.orchestration.assessment_input.get_provider")
    def test_model_failure_sanitized(self, provider):
        """模型异常不暴露健康原文、密钥或内部错误。"""
        provider.return_value.chat.side_effect = RuntimeError("private-health api-key-value")
        response = self.client.post(self.url, {"customer_id": self.customer.id, "input_text": self.source}, format="json")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-health", str(response.data))
        self.assertEqual(Assessment.objects.count(), 0)

    @patch("apps.ai.orchestration.assessment_input.get_provider")
    def test_source_save_does_not_call_model(self, provider):
        """AI 失败时仍可保存描述并恢复，不假装已采用到评估。"""
        assessment = self.assessment()
        response = self.client.put(self.url, {"customer_id": self.customer.id, "assessment_id": assessment.id, "input_text": self.source}, format="json")
        self.assertEqual(response.status_code, 200)
        provider.assert_not_called()
        self.assertTrue(response.data["data"]["source_only"])
        restored = self.client.get(self.url, {"customer_id": self.customer.id, "assessment_id": assessment.id})
        self.assertEqual(restored.data["data"]["input_text"], self.source)
        assessment.refresh_from_db()
        self.assertEqual(assessment.chief_complaint, "人工填写")

    def test_pending_new_page_candidate_can_bind_without_adopting(self):
        """保存后绑定新建页候选，刷新仍能复核，状态保持 pending。"""
        draft = self.candidate()
        assessment = self.assessment()
        response = self.client.put(self.url, {"customer_id": self.customer.id, "assessment_id": assessment.id, "input_text": self.source, "source_draft_id": draft["id"]}, format="json")
        self.assertEqual(response.status_code, 200)
        stored = AiDraft.objects.get(id=draft["id"])
        self.assertEqual(stored.status, "pending")
        self.assertEqual(stored.assessment_id, assessment.id)
        self.assertEqual(len(stored.ai_result["fields"]), 3)

    def test_completed_assessment_cannot_be_organized(self):
        """已完成首评不会通过整理流程再次创建或写入。"""
        assessment = self.assessment()
        assessment.status = "completed"
        assessment.save()
        with patch("apps.ai.orchestration.assessment_input.get_provider") as provider:
            response = self.client.post(self.url, {"customer_id": self.customer.id, "assessment_id": assessment.id, "input_text": self.source}, format="json")
        self.assertEqual(response.status_code, 400)
        provider.assert_not_called()

    def test_negated_result_not_transformed_to_normal(self):
        """“不正常”不能成为正常功能项目。"""
        result = validate({"input_text": "下蹲动作不正常", "raw": {"fields": [], "metrics": [{
            "value": {"metric_type": "functional", "movement": "下蹲", "result_code": "normal"},
            "evidence": {"metric_type": "下蹲动作不正常", "movement": "下蹲", "result_code": "不正常"},
        }]}})
        self.assertEqual(result["candidate"]["metrics"], [])

    def test_historical_score_not_used_as_current(self):
        """模型截掉历史限定词时，仍由原文邻近上下文阻止旧结果复用。"""
        self.source = "上次" + self.source
        self.assertEqual(self.candidate()["metrics"], [])

    def test_goal_score_not_used_as_measurement(self):
        """希望达到的评分不构成本次测量事实。"""
        self.source = "希望" + self.source
        self.assertEqual(self.candidate()["metrics"], [])

    def test_fraction_denominator_not_used_as_score(self):
        """4/5 的肌力结果只能抽成 4，不能把满分 5 当结果。"""
        self.source = "右膝伸展肌力 4/5 级"
        self.raw["metrics"] = [{
            "value": {"metric_type": "strength", "body_part": "膝", "side": "right", "movement": "伸展", "score": 5},
            "evidence": {key: self.source for key in ("metric_type", "body_part", "side", "movement", "score")},
        }]
        self.assertEqual(self.candidate()["metrics"], [])
