"""assessments：评估接口单元测试。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.assessments.models import Assessment, AssessmentMetric
from apps.customers.models import Customer
from apps.audit.models import AuditLog
from apps.rehab.models import RehabPlan

User = get_user_model()


class AssessmentApiTests(APITestCase):
    """评估接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户与评估。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.assessment = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            # 每位客户只能有一份首次评估；该公共 fixture 供列表/编辑测试使用，
            # 创建测试中的首次评估通过 API 单独创建。
            assessment_type="reassessment",
            assessment_date="2026-08-01",
            chief_complaint="左膝前侧疼痛",
        )

    def test_create_assessment_with_metrics(self) -> None:
        """创建评估并保存指标。"""
        payload = {
            "customer": self.customer.id,
            "assessment_type": "initial",
            "assessment_date": "2026-08-01",
            "chief_complaint": "左膝疼痛",
            "metrics": [
                {"metric_type": "pain", "body_part": "左膝", "score": 6, "score_max": 10},
                {"metric_type": "strength", "body_part": "左膝", "score": 4, "score_max": 5},
            ],
        }
        resp = self.client.post(reverse("assessment-list"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(len(data["metrics"]), 2)
        self.assertEqual(data["metrics"][0]["metric_type"], "pain")

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建评估。"""
        resp = self.client.post(
            reverse("assessment-list"),
            {"customer": self.other_customer.id, "assessment_date": "2026-08-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_and_detail(self) -> None:
        """列表与详情。"""
        resp = self.client.get(reverse("assessment-list"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

        resp = self.client.get(reverse("assessment-detail", args=[self.assessment.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["chief_complaint"], "左膝前侧疼痛")

    def test_cannot_access_other_therapist_assessment(self) -> None:
        """不能访问其他康复师的评估。"""
        other_assessment = Assessment.objects.create(
            therapist=self.other, customer=self.other_customer, assessment_date="2026-08-01"
        )
        resp = self.client.get(reverse("assessment-detail", args=[other_assessment.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_writes_audit(self) -> None:
        """更新评估并记录审计。"""
        resp = self.client.put(
            reverse("assessment-detail", args=[self.assessment.id]),
            {"chief_complaint": "左膝疼痛（更新）", "rehab_goal": "恢复下蹲"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["chief_complaint"], "左膝疼痛（更新）")
        self.assertTrue(AuditLog.objects.filter(content_type__model="assessment").exists())

    def test_metric_definitions_are_available(self) -> None:
        """指标定义由服务端统一提供。"""
        resp = self.client.get(reverse("assessment-metric-definitions"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        definitions = {item["metric_type"]: item for item in resp.data["data"]}
        self.assertEqual(definitions["pain"]["max"], 10)
        self.assertEqual(definitions["pain"]["code"], "NRS_0_10")
        self.assertEqual(definitions["strength"]["code"], "MRC_0_5")
        self.assertEqual(definitions["rom"]["max"], 360)

    def test_server_derives_metric_scale_and_maximum(self) -> None:
        """客户端提交的满分不会覆盖服务端量表规则。"""
        resp = self.client.post(
            reverse("assessment-list"),
            {
                "customer": self.customer.id,
                "assessment_type": "initial",
                "assessment_date": "2026-08-01",
                "metrics": [
                    {
                        "metric_type": "pain",
                        "body_part": "左膝",
                        "score": 6,
                        "score_max": 99,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        metric = AssessmentMetric.objects.get(assessment_id=resp.data["data"]["id"])
        self.assertEqual(metric.score_max, 10)
        self.assertEqual(metric.scale_code, "NRS_0_10")
        self.assertEqual(metric.unit, "point")

    def test_complete_requires_full_assessment(self) -> None:
        """草稿允许保存，但完成前必须补齐步骤与指标字段。"""
        resp = self.client.post(
            reverse("assessment-complete", args=[self.assessment.id]),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["data"]["error_code"], "assessment_incomplete")
        self.assertEqual(Assessment.objects.get(id=self.assessment.id).status, "draft")

    def test_complete_revalidates_an_already_completed_assessment(self) -> None:
        """已完成记录修订后再次确认时仍需通过最新完整性校验。"""
        self.assessment.status = "completed"
        self.assessment.save(update_fields=["status"])

        resp = self.client.post(reverse("assessment-complete", args=[self.assessment.id]), format="json")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["data"]["error_code"], "assessment_incomplete")

    def test_complete_assessment_and_reject_duplicate_initial(self) -> None:
        """首评完成后状态更新，第二份首评被稳定错误码拒绝。"""
        create_resp = self.client.post(
            reverse("assessment-list"),
            {
                "customer": self.customer.id,
                "assessment_type": "initial",
                "assessment_date": "2026-08-02",
                "chief_complaint": "右膝疼痛",
                "onset_description": "两周前逐渐出现",
                "rehab_goal": "恢复下蹲",
                "metrics": [
                    {
                        "metric_type": "pain",
                        "body_part": "右膝",
                        "side": "right",
                        "context": "activity",
                        "score": 5,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_200_OK)
        assessment_id = create_resp.data["data"]["id"]
        complete_resp = self.client.post(reverse("assessment-complete", args=[assessment_id]), format="json")
        self.assertEqual(complete_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_resp.data["data"]["status"], "completed")
        duplicate_resp = self.client.post(
            reverse("assessment-list"),
            {"customer": self.customer.id, "assessment_type": "initial", "assessment_date": "2026-08-03"},
            format="json",
        )
        self.assertEqual(duplicate_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(duplicate_resp.data["data"]["error_code"], "initial_assessment_exists")

    def test_plan_must_belong_to_same_customer_and_therapist(self) -> None:
        """评估不能关联其他客户的康复计划。"""
        plan = RehabPlan.objects.create(
            therapist=self.other,
            customer=self.other_customer,
            start_date="2026-08-01",
        )
        resp = self.client.post(
            reverse("assessment-list"),
            {
                "customer": self.customer.id,
                "assessment_type": "reassessment",
                "assessment_date": "2026-08-04",
                "plan": plan.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["data"]["error_code"], "plan_customer_mismatch")

    def test_assessment_type_is_immutable_after_creation(self) -> None:
        """首评和复评不能通过更新互相转换。"""
        resp = self.client.put(
            reverse("assessment-detail", args=[self.assessment.id]),
            {"assessment_type": "initial"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["data"]["error_code"], "assessment_type_immutable")

    def test_all_metric_types_complete_with_type_specific_fields(self) -> None:
        """五种指标均使用各自的结果字段和服务端规则。"""
        assessment = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="reassessment",
            assessment_date="2026-08-05",
            chief_complaint="肩部活动受限",
            onset_description="近期逐渐出现",
            rehab_goal="恢复举手",
        )
        AssessmentMetric.objects.create(
            assessment=assessment,
            metric_type="strength",
            body_part="肩外展肌群",
            side="right",
            movement="肩关节外展",
            score=4,
            score_max=99,
        )
        AssessmentMetric.objects.create(
            assessment=assessment,
            metric_type="rom",
            body_part="右肩",
            side="right",
            movement="外展",
            measurement_mode="active",
            score="90.5",
        )
        AssessmentMetric.objects.create(
            assessment=assessment,
            metric_type="special_test",
            body_part="右肩",
            side="right",
            result_code="negative",
            details={"test_name": "Neer 测试"},
        )
        AssessmentMetric.objects.create(
            assessment=assessment,
            metric_type="functional",
            movement="举手",
            result_code="limited",
        )
        response = self.client.post(reverse("assessment-complete", args=[assessment.id]), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["status"], "completed")
        metrics = {item.metric_type: item for item in AssessmentMetric.objects.filter(assessment=assessment)}
        self.assertEqual(metrics["strength"].score_max, 5)
        self.assertIsNone(metrics["rom"].score_max)
        self.assertIsNone(metrics["special_test"].score)
        self.assertIsNone(metrics["functional"].score_max)

    def _create_completable_assessment(self) -> Assessment:
        """构造一份可正常完成的评估。"""
        assessment = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="reassessment",
            assessment_date="2026-08-06",
            chief_complaint="肘部疼痛",
            onset_description="近期逐渐出现",
            rehab_goal="恢复屈伸",
        )
        AssessmentMetric.objects.create(
            assessment=assessment,
            metric_type="pain",
            body_part="右肘",
            side="right",
            context="activity",
            score=3,
        )
        return assessment

    def test_complete_idempotent_when_unchanged_after_completion(self) -> None:
        """正常完成且完成后未修改的评估，重复完成应空转直接成功。"""
        assessment = self._create_completable_assessment()
        first = self.client.post(reverse("assessment-complete", args=[assessment.id]), format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["data"]["status"], "completed")

        second = self.client.post(reverse("assessment-complete", args=[assessment.id]), format="json")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["data"]["status"], "completed")

    def test_complete_revalidates_after_revision(self) -> None:
        """正常完成后若被修订（内容变残缺），再次完成需重新校验并报错。"""
        assessment = self._create_completable_assessment()
        resp = self.client.post(reverse("assessment-complete", args=[assessment.id]), format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # 完成后清空主诉，使评估重新不满足完成条件。
        assessment.chief_complaint = ""
        assessment.save(update_fields=["chief_complaint", "updated_at"])
        retry = self.client.post(reverse("assessment-complete", args=[assessment.id]), format="json")
        self.assertEqual(retry.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(retry.data["data"]["error_code"], "assessment_incomplete")

    def test_update_metric_diff_keeps_existing_metric_id(self) -> None:
        """更新评估时按 id 差异同步指标，保留已有指标 id。"""
        assessment = Assessment.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            assessment_type="reassessment",
            assessment_date="2026-08-07",
        )
        m1 = AssessmentMetric.objects.create(
            assessment=assessment, metric_type="pain", body_part="左膝", score=5
        )
        m2 = AssessmentMetric.objects.create(
            assessment=assessment, metric_type="strength", body_part="左膝", score=4
        )

        resp = self.client.put(
            reverse("assessment-detail", args=[assessment.id]),
            {
                "metrics": [
                    # 更新已有 m1（带原 id），保留原 id。
                    {"id": m1.id, "metric_type": "pain", "body_part": "左膝", "score": 6},
                    # 新增一条 rom，不带 id。
                    {"metric_type": "rom", "body_part": "左膝", "movement": "屈曲", "measurement_mode": "active", "score": 90},
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        remaining = list(AssessmentMetric.objects.filter(assessment=assessment).order_by("id"))
        self.assertEqual(len(remaining), 2)
        # 原有 m1 被更新且 id 不变；m2 未提交被删除。
        updated_m1 = AssessmentMetric.objects.get(id=m1.id)
        self.assertEqual(int(updated_m1.score), 6)
        self.assertFalse(AssessmentMetric.objects.filter(id=m2.id).exists())
        # 新增的 rom 正常落库。
        self.assertEqual(remaining[1].metric_type, "rom")

    def test_initial_status_endpoint(self) -> None:
        """首评直达接口返回存在性与状态。"""
        # 无首评。
        resp = self.client.get(
            reverse("assessment-initial"), {"customer_id": self.customer.id}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["exists"], False)

        # 创建首评草稿后返回 draft。
        create_resp = self.client.post(
            reverse("assessment-list"),
            {"customer": self.customer.id, "assessment_type": "initial", "assessment_date": "2026-08-08"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_200_OK)
        initial_id = create_resp.data["data"]["id"]
        resp = self.client.get(reverse("assessment-initial"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["exists"], True)
        self.assertEqual(resp.data["data"]["status"], "draft")
        self.assertEqual(resp.data["data"]["assessment_id"], initial_id)

        # 非法客户。
        resp = self.client.get(reverse("assessment-initial"), {"customer_id": self.other_customer.id})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
