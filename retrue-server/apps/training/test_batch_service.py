"""多客户批量训练补记的领域服务与接口测试。

覆盖验收用例的拆分、顺序、客户确认、草稿、正式保存、幂等、推进与完成。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.ai.models import AiDraft, AiDraftStatus
from apps.assistant_tasks.models import AssistantTask, AssistantTaskStatus
from apps.customers.models import Customer
from apps.training.models import (
    TrainingRecord,
    TrainingRecordBatchItem,
    TrainingRecordBatchItemStatus,
)
from apps.training import batch_service

User = get_user_model()

EXAMPLE = "客户A今天做了深蹲10次，康复按摩1次；客户B做了俯卧撑，每组10次，共5组。"
BARE_NAME_EXAMPLE = "张三今天做了深蹲10次；李四做了俯卧撑，每组10次，共5组。"


@override_settings(AI_CONFIG_FILE="", AI_PROVIDER="mock")
class BatchServiceTests(APITestCase):
    """批量补记领域服务测试。"""

    def setUp(self) -> None:
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.client.force_login(self.therapist)
        self.customer_a = Customer.objects.create(therapist=self.therapist, name="客户A")
        self.customer_b = Customer.objects.create(therapist=self.therapist, name="客户B")

    def test_split_preserves_order_and_fields(self) -> None:
        """示例输入拆分为 2 项，保持顺序，深蹲不补组数，按摩为治疗，俯卧撑 5 组每组 10 次。"""
        items = batch_service.split_multi_customer_records(self.therapist, EXAMPLE)
        self.assertEqual(len(items), 2)
        first, second = items[0], items[1]
        self.assertEqual(first["customer_name_hint"], "客户A")
        self.assertEqual(second["customer_name_hint"], "客户B")

        first_activities = first["activities"]
        squat = first_activities[0]
        self.assertEqual(squat["name"], "深蹲")
        self.assertEqual(squat["reps"], 10)
        self.assertIsNone(squat["sets"])  # 不擅自补组数
        massage = first_activities[1]
        self.assertEqual(massage["name"], "康复按摩")
        self.assertEqual(massage["activity_type"], "therapy")
        self.assertEqual(massage["quantity"], 1)

        pushup = second["activities"][0]
        self.assertEqual(pushup["name"], "俯卧撑")
        self.assertEqual(pushup["sets"], 5)
        self.assertEqual(pushup["reps"], 10)

    def test_create_batch_task_creates_parent_and_items(self) -> None:
        """创建父任务与 2 个有序子项。"""
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        self.assertEqual(task.task_type, "multi_customer_training_record")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].sequence, 1)
        self.assertEqual(items[1].sequence, 2)
        self.assertEqual(items[0].customer_name_hint, "客户A")

    def test_split_supports_bare_names_in_original_order(self) -> None:
        """没有“客户”前缀时，也能按原句中的姓名与顺序拆分。"""
        items = batch_service.split_multi_customer_records(self.therapist, BARE_NAME_EXAMPLE)
        self.assertEqual([item["customer_name_hint"] for item in items], ["张三", "李四"])
        self.assertEqual(items[0]["activities"][0]["name"], "深蹲")
        self.assertEqual(items[1]["activities"][0]["sets"], 5)

    def test_prepare_current_item_searches_first_then_next_customer(self) -> None:
        """创建任务和保存上一项后，服务端直接准备当前项的客户候选。"""
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        first = batch_service.prepare_current_item(self.therapist, task.id)
        self.assertEqual(first["item"].id, items[0].id)
        self.assertEqual([candidate["id"] for candidate in first["candidates"]], [self.customer_a.id])

        batch_service.confirm_item_customer(self.therapist, task.id, items[0].id, self.customer_a.id)
        batch_service.confirm_item_record(
            self.therapist,
            task.id,
            items[0].id,
            {"training_date": "2026-09-02"},
            "prepare-next-1",
        )
        second = batch_service.prepare_current_item(self.therapist, task.id)
        self.assertEqual(second["item"].id, items[1].id)
        self.assertEqual([candidate["id"] for candidate in second["candidates"]], [self.customer_b.id])

    def test_search_item_hits_directory_alias(self) -> None:
        """目录匹配：hint 用别称也能唯一命中真实客户（不再只精确查档案名）。"""
        from apps.customers.catalog import normalize_name
        from apps.customers.models import CustomerAlias

        real = Customer.objects.create(therapist=self.therapist, name="黄伟成")
        CustomerAlias.objects.create(
            therapist=self.therapist, customer=real, alias="阿成", normalized_alias=normalize_name("阿成")
        )
        task, items = batch_service.create_batch_task(self.therapist, "阿成今天做了深蹲10次；王五做了俯卧撑5组")
        # 第二个子项（王五）目录无匹配 -> 应只保留当前唯一命中者；验证第一项目录匹配。
        first = batch_service.prepare_current_item(self.therapist, task.id)
        self.assertEqual(first["item"].id, items[0].id)
        candidates = first["candidates"]
        self.assertEqual([c["id"] for c in candidates], [real.id])

    def test_search_item_returns_ambiguous_multi_candidates(self) -> None:
        """目录匹配：同名多个真实客户（如两位“王五”）返回多候选，不自动绑定。"""
        first = Customer.objects.create(therapist=self.therapist, name="王五")
        second = Customer.objects.create(therapist=self.therapist, name="王五")
        task, items = batch_service.create_batch_task(self.therapist, "张三今天做了深蹲10次；王五做了俯卧撑5组")
        # 直接定位“王五”子项：目录匹配应命中两位同名客户 -> 多候选。
        item = next(i for i in items if i.customer_name_hint == "王五")
        candidates = batch_service.search_item_customer(self.therapist, task.id, item.id)
        self.assertEqual({c["id"] for c in candidates}, {first.id, second.id})

    def test_full_flow_end_to_end(self) -> None:
        """完整流程：识别 2 项 → 确认客户A → 保存A → 进入B → 保存B → 父任务完成。"""
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        self.assertEqual(task.status, AssistantTaskStatus.WAITING_USER)

        # 客户A：确认客户 → 草稿 → 正式确认。
        item_a = items[0]
        batch_service.confirm_item_customer(self.therapist, task.id, item_a.id, self.customer_a.id)
        item_a.refresh_from_db()
        self.assertEqual(item_a.status, TrainingRecordBatchItemStatus.WAITING_DRAFT)
        self.assertEqual(AiDraft.objects.filter(status=AiDraftStatus.PENDING).count(), 1)

        confirmed_a = batch_service.confirm_item_record(
            self.therapist,
            task.id,
            item_a.id,
            {"training_date": "2026-09-02", "customer_feedback": "完成良好"},
            "confirm-a-1",
        )
        self.assertEqual(confirmed_a.status, TrainingRecordBatchItemStatus.COMPLETED)
        self.assertIsNotNone(confirmed_a.training_record_id)

        # 保存A后自动进入B（B 仍是 pending）。
        item_b = items[1]
        item_b.refresh_from_db()
        self.assertEqual(item_b.status, TrainingRecordBatchItemStatus.PENDING)

        batch_service.confirm_item_customer(self.therapist, task.id, item_b.id, self.customer_b.id)
        confirmed_b = batch_service.confirm_item_record(
            self.therapist,
            task.id,
            item_b.id,
            {"training_date": "2026-09-02"},
            "confirm-b-1",
        )
        self.assertEqual(confirmed_b.status, TrainingRecordBatchItemStatus.COMPLETED)

        # 全部完成后父任务 completed，共 2 条正式记录。
        task.refresh_from_db()
        self.assertEqual(task.status, AssistantTaskStatus.COMPLETED)
        self.assertEqual(TrainingRecord.objects.count(), 2)

        summary = batch_service.build_batch_summary(self.therapist, task.id)
        self.assertEqual(summary["succeeded"], 2)
        self.assertEqual(summary["total_items"], 2)

    def test_repeated_confirm_idempotent(self) -> None:
        """客户A重复确认不会生成第二条记录。"""
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        item_a = items[0]
        batch_service.confirm_item_customer(self.therapist, task.id, item_a.id, self.customer_a.id)
        batch_service.confirm_item_record(
            self.therapist, task.id, item_a.id, {"training_date": "2026-09-02"}, "confirm-a-1"
        )
        # 重复确认：幂等返回，不新增记录。
        again = batch_service.confirm_item_record(
            self.therapist, task.id, item_a.id, {"training_date": "2026-09-02"}, "confirm-a-1"
        )
        self.assertEqual(again.status, TrainingRecordBatchItemStatus.COMPLETED)
        self.assertEqual(TrainingRecord.objects.count(), 1)

    def test_cannot_save_b_before_a(self) -> None:
        """客户A未完成时不能保存客户B。"""
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        item_b = items[1]
        with self.assertRaises(ValueError):
            batch_service.confirm_item_customer(self.therapist, task.id, item_b.id, self.customer_b.id)

    def test_skip_a_continues_b(self) -> None:
        """跳过客户A后可继续客户B。"""
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        batch_service.skip_item(self.therapist, task.id, items[0].id)
        items[0].refresh_from_db()
        self.assertEqual(items[0].status, TrainingRecordBatchItemStatus.SKIPPED)
        # B 可正常处理。
        batch_service.confirm_item_customer(self.therapist, task.id, items[1].id, self.customer_b.id)
        self.assertEqual(TrainingRecord.objects.count(), 0)  # 尚未确认

    def test_other_therapist_cannot_access(self) -> None:
        """非任务所属康复师不能操作子项。"""
        other = User.objects.create_user(username="t2", password="test12345")
        task, items = batch_service.create_batch_task(self.therapist, EXAMPLE)
        with self.assertRaises(ValueError):
            batch_service.confirm_item_customer(other, task.id, items[0].id, self.customer_a.id)
