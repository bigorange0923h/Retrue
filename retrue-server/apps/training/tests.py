"""training：训练记录接口单元测试。

覆盖训练记录创建、动作明细、数据隔离、时间线与修订审计。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.customers.models import Customer
from apps.training.models import TrainingRecord

User = get_user_model()


class TrainingApiTests(APITestCase):
    """训练记录接口测试。"""

    def setUp(self) -> None:
        """准备康复师账号、客户与训练记录。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")

        self.record = TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date="2026-08-26",
            customer_feedback="左膝疼痛 NRS 2",
            next_plan="增加单腿稳定训练",
        )

    def test_create_record_with_exercises(self) -> None:
        """创建训练记录并保存动作明细。"""
        payload = {
            "customer": self.customer.id,
            "training_date": "2026-08-27",
            "customer_feedback": "比上次稳定",
            "exercises": [
                {"exercise_name": "臀桥", "sets": 3, "reps": 12},
                {"exercise_name": "靠墙静蹲", "duration_seconds": 30},
            ],
        }
        resp = self.client.post(reverse("training-list"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["customer_name"], "张三")
        self.assertEqual(len(data["exercises"]), 2)
        self.assertEqual(data["exercises"][0]["exercise_name"], "臀桥")

    def test_create_record_for_other_customer_forbidden(self) -> None:
        """不能为其他康复师的客户创建训练记录。"""
        resp = self.client.post(
            reverse("training-list"),
            {"customer": self.other_customer.id, "training_date": "2026-08-27"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], 403)

    def test_list_requires_customer_id(self) -> None:
        """缺少 customer_id 返回 400。"""
        resp = self.client.get(reverse("training-list"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revision_requires_reason_and_writes_audit(self) -> None:
        """修订正式记录必须填写原因，并写入审计。"""
        payload = {
            "reason": "修正客户感受",
            "customer_feedback": "左膝疼痛 NRS 1（修正）",
        }
        resp = self.client.put(reverse("training-detail", args=[self.record.id]), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["customer_feedback"], "左膝疼痛 NRS 1（修正）")

        # 校验审计日志
        logs = AuditLog.objects.filter(content_type__model="trainingrecord", object_id=str(self.record.id))
        self.assertTrue(logs.exists())
        last = logs.order_by("-created_at").first()
        self.assertEqual(last.action, "update")
        self.assertEqual(last.reason, "修正客户感受")
        self.assertEqual(last.actor, self.therapist)

    def test_revision_without_reason_returns_400(self) -> None:
        """修订不提供原因返回 400。"""
        resp = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {"customer_feedback": "修改内容"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_revision_cannot_rebind_record_to_other_customer(self) -> None:
        """修订正式记录时不允许把记录改绑到其他康复师客户（F01）。"""
        resp = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {
                "reason": "尝试改绑客户",
                "customer": self.other_customer.id,
                "customer_feedback": "任意内容",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # 数据库归属无变化，且不应产生业务审计误记录。
        self.record.refresh_from_db()
        self.assertEqual(self.record.customer_id, self.customer.id)
        logs = AuditLog.objects.filter(content_type__model="trainingrecord", object_id=str(self.record.id))
        self.assertEqual(logs.count(), 0)

    def test_revision_accepts_same_customer_value(self) -> None:
        """提交与记录相同客户值仍可正常修订（保持兼容）。"""
        resp = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {
                "reason": "修正内容",
                "customer": self.customer.id,
                "customer_feedback": "左膝疼痛 NRS 1",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["customer"], self.customer.id)
        self.record.refresh_from_db()
        self.assertEqual(self.record.customer_id, self.customer.id)

    def test_create_preserves_massage_fields_on_manual_record(self) -> None:
        """手动创建时 activity_type/quantity/unit 不丢失（F03）。"""
        resp = self.client.post(
            reverse("training-list"),
            {
                "customer": self.customer.id,
                "training_date": "2026-08-27",
                "exercises": [
                    {
                        "exercise_name": "康复按摩",
                        "activity_type": "massage",
                        "quantity": 1,
                        "unit": "次",
                    },
                    {"exercise_name": "臀桥", "activity_type": "exercise", "sets": 3, "reps": 12},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        out = {e["exercise_name"]: e for e in data["exercises"]}
        self.assertEqual(out["康复按摩"]["activity_type"], "massage")
        self.assertEqual(out["康复按摩"]["quantity"], 1)
        self.assertEqual(out["康复按摩"]["unit"], "次")
        self.assertEqual(out["臀桥"]["sets"], 3)

    def test_revision_preserves_massage_fields(self) -> None:
        """人工修订整体替换动作时仍保留按摩数量字段（F03）。"""
        from apps.training.models import TrainingExercise

        TrainingExercise.objects.create(
            training_record=self.record,
            exercise_name="康复按摩",
            activity_type="massage",
            quantity=1,
            unit="次",
            sort_order=0,
        )
        resp = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {
                "reason": "补充动作",
                "exercises": [
                    {
                        "exercise_name": "康复按摩",
                        "activity_type": "massage",
                        "quantity": 2,
                        "unit": "次",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        out = {e["exercise_name"]: e for e in data["exercises"]}
        self.assertEqual(out["康复按摩"]["activity_type"], "massage")
        self.assertEqual(out["康复按摩"]["quantity"], 2)
        self.assertEqual(out["康复按摩"]["unit"], "次")
        db_item = TrainingExercise.objects.get(training_record=self.record, exercise_name="康复按摩")
        self.assertEqual(db_item.activity_type, "massage")
        self.assertEqual(db_item.quantity, 2)

    def test_revision_conflict_returns_409_on_stale_expected_updated_at(self) -> None:
        """用旧 updated_at 提交修订返回 409，避免覆盖并发修改（F08）。"""
        # 首次修订成功会推进 updated_at
        first = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {"reason": "第一次修订", "customer_feedback": "v1"},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        fresh_updated_at = first.data["data"]["updated_at"]

        # 模拟另一个编辑页面基于更旧版本提交
        stale = self.record.updated_at.isoformat()
        conflicted = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {
                "reason": "过期修订",
                "expected_updated_at": stale,
                "customer_feedback": "v2-stale",
            },
            format="json",
        )
        self.assertEqual(conflicted.status_code, status.HTTP_409_CONFLICT)
        self.record.refresh_from_db()
        self.assertEqual(self.record.customer_feedback, "v1")

        # 携带最新 updated_at 的修订成功
        ok = self.client.put(
            reverse("training-detail", args=[self.record.id]),
            {
                "reason": "基于最新修订",
                "expected_updated_at": fresh_updated_at,
                "customer_feedback": "v2-fresh",
            },
            format="json",
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_list_invalid_customer_id_returns_400(self) -> None:
        """训练列表 customer_id 非法返回 400 而非 500（F08）。"""
        resp = self.client.get(reverse("training-list"), {"customer_id": "abc"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.get(reverse("training-list"), {"customer_id": "-1"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_timeline_invalid_customer_id_returns_400(self) -> None:
        """时间线 customer_id 非法返回 400 而非 500（F08）。"""
        resp = self.client.get(reverse("customer-timeline"), {"customer_id": "abc"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_timeline_orders_by_date_desc(self) -> None:
        """客户时间线按训练日期倒序。"""
        TrainingRecord.objects.create(
            therapist=self.therapist, customer=self.customer, training_date="2026-08-25"
        )
        resp = self.client.get(reverse("customer-timeline"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        dates = [item["training_date"] for item in resp.data["data"]]
        self.assertEqual(dates, ["2026-08-26", "2026-08-25"])

    def test_cannot_access_other_therapist_record(self) -> None:
        """不能读取其他康复师的训练记录。"""
        other_record = TrainingRecord.objects.create(
            therapist=self.other, customer=self.other_customer, training_date="2026-08-26"
        )
        resp = self.client.get(reverse("training-detail", args=[other_record.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_course_session_allows_only_one_formal_record(self) -> None:
        """同一非空排课不能重复关联正式训练记录，未排课记录仍可多条。"""
        from apps.schedules.models import CourseSession

        session = CourseSession.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            date="2026-08-27",
        )
        TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            course_session=session,
            training_date="2026-08-27",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TrainingRecord.objects.create(
                    therapist=self.therapist,
                    customer=self.customer,
                    course_session=session,
                    training_date="2026-08-27",
                )

        # 条件唯一约束不应阻止没有排课来源的自然语言补记。
        TrainingRecord.objects.create(
            therapist=self.therapist,
            customer=self.customer,
            training_date="2026-08-28",
        )
        self.assertEqual(TrainingRecord.objects.filter(customer=self.customer).count(), 3)


class HomeTrainingApiTests(APITestCase):
    """家庭训练计划接口测试。"""

    def setUp(self) -> None:
        """准备康复师、客户。"""
        from apps.training.models import HomeTrainingPlan

        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.customer = Customer.objects.create(therapist=self.therapist, name="张三")
        self.other_customer = Customer.objects.create(therapist=self.other, name="李四")
        self.plan = HomeTrainingPlan.objects.create(
            therapist=self.therapist, customer=self.customer, title="膝部家庭训练"
        )

    def test_create_home_training_plan(self) -> None:
        """创建家庭训练计划（含动作）。"""
        payload = {
            "customer": self.customer.id,
            "title": "膝部训练",
            "exercises": [
                {"exercise_name": "臀桥", "sets": 3, "reps": 12},
                {"exercise_name": "靠墙静蹲", "duration_seconds": 30},
            ],
        }
        resp = self.client.post(reverse("home-training-list"), payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]["exercises"]), 2)

    def test_cannot_create_for_other_customer(self) -> None:
        """不能为其他康复师的客户创建家庭训练。"""
        resp = self.client.post(
            reverse("home-training-list"),
            {"customer": self.other_customer.id, "title": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_and_update(self) -> None:
        """列表与更新。"""
        resp = self.client.get(reverse("home-training-list"), {"customer_id": self.customer.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 1)

        resp = self.client.put(
            reverse("home-training-detail", args=[self.plan.id]),
            {"title": "更新后的家庭训练"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["title"], "更新后的家庭训练")

    def test_update_cannot_rebind_plan_to_other_customer(self) -> None:
        """更新家庭训练计划时不允许把计划改绑到其他康复师客户（F02）。"""
        resp = self.client.put(
            reverse("home-training-detail", args=[self.plan.id]),
            {"customer": self.other_customer.id, "title": "改绑后的计划"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.customer_id, self.customer.id)
        self.assertNotEqual(self.plan.title, "改绑后的计划")

    def test_update_accepts_same_customer_value(self) -> None:
        """提交与计划相同客户值仍可正常更新（保持兼容）。"""
        resp = self.client.put(
            reverse("home-training-detail", args=[self.plan.id]),
            {"customer": self.customer.id, "title": "更新标题"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["customer"], self.customer.id)

    def test_list_invalid_customer_id_returns_400(self) -> None:
        """家庭训练列表 customer_id 非法返回 400（F08）。"""
        resp = self.client.get(reverse("home-training-list"), {"customer_id": "abc"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
