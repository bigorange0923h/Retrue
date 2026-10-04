"""客户别称、脱敏导出与只读影响预览回归测试。"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.assessments.models import Assessment, AssessmentMetric
from apps.audit.models import AuditLog
from apps.courses.models import CourseAdjustment, CoursePackage
from apps.customers.catalog import match_customers_in_text
from apps.customers.models import Customer, CustomerAlias
from apps.customers.services import update_customer
from apps.training.models import TrainingExercise, TrainingRecord


class CustomerDeliveryTests(APITestCase):
    """保证交付资料归属正确，不泄露其他康复师客户数据。"""

    def setUp(self) -> None:
        """准备两个账号和明确模拟的数据。"""
        users = get_user_model()
        self.user = users.objects.create_user(username="delivery-one", password="test12345")
        self.other = users.objects.create_user(username="delivery-two", password="test12345")
        self.customer = Customer.objects.create(therapist=self.user, name="测试交付客户", phone="13800001111",
                                                note="测试联系号码 13800001111")
        self.foreign = Customer.objects.create(therapist=self.other, name="测试另一账号客户")
        self.client.force_login(self.user)

    def test_alias_create_edit_disable_affects_only_own_directory(self) -> None:
        """别称归一化、修改、停用均可重读，并即时退出自然语言匹配。"""
        url = reverse("customer-alias-list", args=[self.customer.id])
        resp = self.client.post(url, {"alias": " Ａ成 "}, format="json")
        self.assertEqual(resp.status_code, 200)
        alias_id = resp.data["data"]["id"]
        self.assertEqual(resp.data["data"]["normalized_alias"], "a成")
        self.assertEqual(match_customers_in_text(self.user, "A成今天训练").customer_id, self.customer.id)
        detail = reverse("customer-alias-detail", args=[self.customer.id, alias_id])
        resp = self.client.put(detail, {"alias": "测试小成", "is_active": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(match_customers_in_text(self.user, "测试小成").is_unmatched)
        self.assertFalse(self.client.get(url).data["data"][0]["is_active"])
        self.assertTrue(AuditLog.objects.filter(actor=self.user, action="update", object_id=str(alias_id)).exists())

    def test_alias_rejects_formal_name_conflict_and_normalized_duplicates(self) -> None:
        """同账号正式名歧义或归一化重复不能自动绑定。"""
        Customer.objects.create(therapist=self.user, name="测试小成")
        url = reverse("customer-alias-list", args=[self.customer.id])
        self.assertEqual(self.client.post(url, {"alias": "客户 测试小成"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"alias": "ＡＢＣ"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(url, {"alias": "abc"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"alias": " 客户 "}, format="json").status_code, 400)

    def test_alias_cross_account_and_customer_mismatch_are_hidden(self) -> None:
        """不能创建或改写另一账号/另一个客户的别称。"""
        foreign_alias = CustomerAlias.objects.create(therapist=self.other, customer=self.foreign,
                                                    alias="测试外国别称", normalized_alias="测试外国别称")
        resp = self.client.get(reverse("customer-alias-list", args=[self.foreign.id]))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.put(reverse("customer-alias-detail", args=[self.customer.id, foreign_alias.id]),
                               {"alias": "不应改写"}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_json_export_covers_records_and_ledger_masks_phone_and_audits(self) -> None:
        """结构化资料含评估/训练/课时流水，但无手机号、他人客户或内部向量。"""
        assessment = Assessment.objects.create(therapist=self.user, customer=self.customer,
                                                 assessment_date="2026-09-01", chief_complaint="测试主诉")
        AssessmentMetric.objects.create(assessment=assessment, metric_type="pain", score=2)
        training = TrainingRecord.objects.create(therapist=self.user, customer=self.customer,
                                                   training_date="2026-09-02", note="测试训练")
        TrainingExercise.objects.create(training_record=training, exercise_name="测试动作", sets=3, reps=12)
        TrainingRecord.objects.create(therapist=self.other, customer=self.foreign,
                                       training_date="2026-09-02", note="不应导出的测试他人训练")
        package = CoursePackage.objects.create(therapist=self.user, customer=self.customer,
                                                 name="测试课时包", total_sessions=10)
        CourseAdjustment.objects.create(therapist=self.user, package=package, delta=10, reason="测试购课")
        resp = self.client.get(reverse("customer-export", args=[self.customer.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.data["data"]
        payload = data["content"]
        self.assertEqual(len(payload["resources"]["assessments"]), 1)
        self.assertEqual(payload["resources"]["training_exercises"][0]["sets"], 3)
        self.assertEqual(payload["resources"]["course_adjustments"][0]["delta"], "10.0")
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("13800001111", serialized)
        self.assertNotIn("不应导出的测试他人训练", serialized)
        self.assertNotIn("embedding", serialized)
        self.assertEqual(AuditLog.objects.get(id=data["audit_id"]).action, "export")
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_readable_export_and_foreign_access(self) -> None:
        """文本报告可读且脱敏，跨账号导出与预览均返回404。"""
        resp = self.client.get(reverse("customer-export", args=[self.customer.id]), {"output": "report"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("客户康复资料", resp.data["data"]["content"])
        self.assertNotIn("13800001111", resp.data["data"]["content"])
        for name in ["customer-export", "customer-deletion-preview"]:
            self.assertEqual(self.client.get(reverse(name, args=[self.foreign.id])).status_code, 404)

    def test_deletion_preview_has_no_side_effect_and_no_delete_endpoint(self) -> None:
        """重复预览不写日志或更改客户；删除执行没有开放。"""
        url = reverse("customer-deletion-preview", args=[self.customer.id])
        before = (Customer.objects.count(), AuditLog.objects.count(), self.customer.updated_at)
        for _ in range(2):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.data["data"]["can_delete"])
            self.assertFalse(resp.data["data"]["execution_enabled"])
        self.customer.refresh_from_db()
        self.assertEqual(before, (Customer.objects.count(), AuditLog.objects.count(), self.customer.updated_at))
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_customer_audit_failure_rolls_back_update(self) -> None:
        """客户更新与审计同事务，不留只有业务变更的半成品。"""
        with patch("apps.customers.services.write_audit_log", side_effect=RuntimeError("模拟审计失败")):
            with self.assertRaises(RuntimeError):
                update_customer(self.user, self.customer, {"name": "不应保留"})
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "测试交付客户")

    def test_customer_nullable_date_can_be_explicitly_cleared(self) -> None:
        """显式 null 日期不能被服务层忽略成旧值。"""
        self.customer.birth_date = "1990-01-01"
        self.customer.save()
        resp = self.client.put(reverse("customer-detail", args=[self.customer.id]),
                               {"birth_date": None}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data["data"]["birth_date"])
