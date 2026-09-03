"""多客户批量训练补记领域服务。

负责父级批量任务与有序业务子项的创建、客户搜索与确认、草稿生成、正式
确认、跳过、顺序推进与完成。所有写操作由服务校验归属与状态；AI 只生成
草稿，正式训练记录在康复师明确确认后经 training_parser 领域服务写入。

父任务使用 ``AssistantTask``（task_type=multi_customer_training_record，
customer=null）；子项使用 ``TrainingRecordBatchItem``，按 sequence 严格推进。
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone

from apps.ai.models import AiDraft, AiDraftStatus
from apps.ai.schemas.multi_customer import MultiCustomerTrainingSplit
from apps.assistant_tasks.models import AssistantTask, AssistantTaskStatus
from apps.customers.models import Customer
from apps.training.models import (
    TrainingRecordBatchItem,
    TrainingRecordBatchItemStatus,
)


def _owner_id(therapist: AbstractUser) -> int:
    from apps.assistant_tasks.services import _owner_id as _oid

    return _oid(therapist)


def _get_owned_task(therapist: AbstractUser, task_id: int, *, for_update: bool = False):
    from apps.assistant_tasks.services import get_owned_task

    task = get_owned_task(therapist, task_id, for_update=for_update)
    if task is None or str(getattr(task, "task_type", "") or "") != "multi_customer_training_record":
        raise ValueError("批量任务不存在或无权访问")
    return task


def _get_owned_item(therapist: AbstractUser, task: AssistantTask, item_id: int, *, for_update: bool = False):
    queryset = TrainingRecordBatchItem.objects.filter(assistant_task_id=task.id, id=item_id)
    if for_update:
        queryset = queryset.select_for_update()
    item = queryset.first()
    if item is None:
        raise ValueError("批量子项不存在或无权访问")
    return item


def _transition_task(task, status, *, current_step: str, event_type: str, event_data: dict | None = None):
    from apps.assistant_tasks.services import TaskTransitionError, transition_task

    try:
        return transition_task(
            task,
            status,
            current_step=current_step,
            event_type=event_type,
            event_data=event_data or {},
        )
    except TaskTransitionError:
        # 等待态之间不允许直接转换：先转 running 再转目标，保留两段审计事件。
        task = transition_task(
            task,
            AssistantTaskStatus.RUNNING,
            current_step=current_step,
            event_type=f"{event_type}_via_running",
            event_data=event_data or {},
        )
        return transition_task(
            task,
            status,
            current_step=current_step,
            event_type=event_type,
            event_data=event_data or {},
        )


def split_multi_customer_records(therapist: AbstractUser, input_text: str) -> list[dict]:
    """调用 provider 将多客户输入拆分为有序子项（经 Pydantic 校验）。

    返回 items 列表；拆分失败抛出 ValueError，由上层展示拆分确认卡片。
    """
    from apps.ai.providers.factory import get_provider

    raw = get_provider().parse_multi_customer_text(input_text)
    parsed = MultiCustomerTrainingSplit(**raw)
    if not parsed.items:
        raise ValueError("未能从描述中识别出客户记录，请调整描述后重试")
    return [item.model_dump() for item in parsed.items]


@transaction.atomic
def create_batch_task(
    therapist: AbstractUser,
    input_text: str,
    *,
    conversation_id: int | None = None,
    client_request_id: str = "",
    items_data: list[dict] | None = None,
) -> tuple[AssistantTask, list[TrainingRecordBatchItem]]:
    """创建父级批量任务与有序子项。

    ``items_data`` 由 LangGraph 的多客户拆分节点提供时直接复用，避免同一段
    原文在图外再次调用 provider；未提供时保留领域服务的独立调用兼容性。
    """
    from apps.assistant_tasks.services import create_task as task_create

    if items_data is None:
        items_data = split_multi_customer_records(therapist, input_text)
    parsed_items = MultiCustomerTrainingSplit(items=items_data).items
    task = task_create(
        therapist,
        conversation=conversation_id,
        task_type="multi_customer_training_record",
        skill_code="multi_customer_training_record",
        origin="assistant_turns",
        client_request_id=client_request_id,
        status=AssistantTaskStatus.RUNNING,
        current_step="create_batch_items",
    )
    items: list[TrainingRecordBatchItem] = []
    for data in parsed_items:
        item = TrainingRecordBatchItem.objects.create(
            assistant_task=task,
            sequence=data.sequence,
            source_message=input_text,
            customer_name_hint=data.customer_name_hint,
            parsed_payload={"activities": [activity.model_dump() for activity in data.activities]},
            status=TrainingRecordBatchItemStatus.PENDING,
        )
        items.append(item)

    total = len(items)
    _transition_task(
        task,
        AssistantTaskStatus.WAITING_USER,
        current_step="show_batch_overview",
        event_type="batch_items_created",
        event_data={"total_items": total},
    )
    task.state_data = {
        "total_items": total,
        "current_index": 0,
        "current_item_id": items[0].id if items else None,
        "next_node": "wait_item_customer_confirmation",
    }
    task.save(update_fields=["state_data", "updated_at"])
    return task, items


def get_batch_state(therapist: AbstractUser, task_id: int) -> dict:
    """返回批量任务与子项的整体状态，供前端恢复与概览。"""
    task = _get_owned_task(therapist, task_id)
    items = list(
        TrainingRecordBatchItem.objects.filter(assistant_task_id=task.id).order_by("sequence", "id")
    )
    current_item = next(
        (item for item in items if not item.is_terminal),
        None,
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "current_step": task.current_step,
        "total_items": len(items),
        "current_item_id": current_item.id if current_item else None,
        "items": [
            {
                "id": item.id,
                "sequence": item.sequence,
                "customer_name_hint": item.customer_name_hint,
                "customer_id": item.customer_id,
                "customer_name": item.customer.name if item.customer_id else "",
                "status": item.status,
                "draft_id": item.ai_draft_id,
                "training_record_id": item.training_record_id,
            }
            for item in items
        ],
    }


def search_item_customer(therapist: AbstractUser, task_id: int, item_id: int) -> list[dict]:
    """按子项客户姓名提示查询当前康复师名下客户候选。

    姓名来自首句实体解析，必须原样交给既有受控查询 helper；不去掉“客户”等
    字样，也不在此做跨康复师或模糊枚举查询。
    """
    task = _get_owned_task(therapist, task_id)
    item = _get_owned_item(therapist, task, item_id)
    from apps.assistant_tasks import tools

    hint = (item.customer_name_hint or "").strip()
    if not hint:
        return []
    exact_matches = tools.lookup_current_therapist_customers_by_name(therapist, hint)
    if exact_matches:
        return exact_matches
    # “客户张三”中的“客户”可能是称谓而非档案姓名；仅在原样精确匹配无
    # 结果时尝试去称谓后的精确查询，仍不使用模糊搜索或跨康复师枚举。
    normalized_hint = hint
    for prefix in ("客户", "病人", "患者"):
        if normalized_hint.startswith(prefix) and len(normalized_hint) > len(prefix):
            normalized_hint = normalized_hint[len(prefix) :].strip()
            break
    if normalized_hint and normalized_hint != hint:
        return tools.lookup_current_therapist_customers_by_name(therapist, normalized_hint)
    return []


@transaction.atomic
def prepare_current_item(therapist: AbstractUser, task_id: int) -> dict:
    """准备当前最早未完成子项的客户确认信息。

    调用方在创建批量任务、保存/跳过上一项或页面恢复时使用本函数。它只处理
    当前子项，保证客户搜索与确认严格按 sequence 顺序进行。
    """
    task = _get_owned_task(therapist, task_id, for_update=True)
    item = (
        TrainingRecordBatchItem.objects.select_for_update()
        .filter(assistant_task_id=task.id)
        .exclude(
            status__in=[
                TrainingRecordBatchItemStatus.COMPLETED,
                TrainingRecordBatchItemStatus.SKIPPED,
                TrainingRecordBatchItemStatus.FAILED,
                TrainingRecordBatchItemStatus.CANCELLED,
            ]
        )
        .order_by("sequence", "id")
        .first()
    )
    if item is None:
        return {"item": None, "candidates": []}
    if item.status == TrainingRecordBatchItemStatus.WAITING_DRAFT:
        return {"item": item, "candidates": [], "draft_id": item.ai_draft_id}

    item.status = TrainingRecordBatchItemStatus.SEARCHING_CUSTOMER
    item.save(update_fields=["status", "updated_at"])
    candidates = search_item_customer(therapist, task.id, item.id)
    item.status = TrainingRecordBatchItemStatus.WAITING_CUSTOMER
    item.save(update_fields=["status", "updated_at"])
    task.state_data = {
        "total_items": TrainingRecordBatchItem.objects.filter(assistant_task_id=task.id).count(),
        "current_index": item.sequence - 1,
        "current_item_id": item.id,
        "next_node": "wait_item_customer_confirmation",
    }
    task.save(update_fields=["state_data", "updated_at"])
    _transition_task(
        task,
        AssistantTaskStatus.WAITING_USER,
        current_step="wait_item_customer_confirmation",
        event_type="item_customer_search_ready",
        event_data={"item_id": item.id, "candidate_count": len(candidates)},
    )
    return {"item": item, "candidates": candidates}


@transaction.atomic
def confirm_item_customer(therapist: AbstractUser, task_id: int, item_id: int, customer_id: int) -> TrainingRecordBatchItem:
    """确认子项客户，再次校验归属；确认后生成草稿进入等待草稿确认。"""
    task = _get_owned_task(therapist, task_id)
    item = _get_owned_item(therapist, task, item_id, for_update=True)
    if item.is_terminal:
        raise ValueError("该子项已处理完成，不能再次确认客户")
    # 顺序校验：存在更早的未终态子项时，不能处理当前子项。
    earlier_unfinished = TrainingRecordBatchItem.objects.filter(
        assistant_task_id=task.id,
        sequence__lt=item.sequence,
    ).exclude(
        status__in=[
            TrainingRecordBatchItemStatus.COMPLETED,
            TrainingRecordBatchItemStatus.SKIPPED,
            TrainingRecordBatchItemStatus.FAILED,
            TrainingRecordBatchItemStatus.CANCELLED,
        ]
    ).exists()
    if earlier_unfinished:
        raise ValueError("请先完成上一位客户的记录，再处理当前客户")

    customer = Customer.objects.filter(therapist=therapist, id=customer_id).first()
    if customer is None:
        raise ValueError("所选客户不存在或无权访问")

    item.customer = customer
    item.status = TrainingRecordBatchItemStatus.WAITING_DRAFT
    item.save(update_fields=["customer", "status", "updated_at"])

    # 生成草稿（复用 training_parser 的解析，但用子项自身的任务类型不匹配，
    # 这里直接创建 AiDraft 并解析该子项的训练内容）。
    draft = _create_item_draft(therapist, item)

    _transition_task(
        task,
        AssistantTaskStatus.WAITING_CONFIRMATION,
        current_step="wait_item_draft_confirmation",
        event_type="item_customer_confirmed",
        event_data={"item_id": item.id, "customer_id": customer.id},
    )
    return item


def _create_item_draft(therapist: AbstractUser, item: TrainingRecordBatchItem) -> AiDraft:
    """为子项创建 AiDraft（pending），内容来自子项 parsed_payload。"""
    activities = (item.parsed_payload or {}).get("activities", [])
    exercises = [
        {
            "exercise_name": act.get("name", ""),
            "activity_type": act.get("activity_type", "exercise"),
            "sets": act.get("sets"),
            "reps": act.get("reps"),
            "quantity": act.get("quantity"),
            "unit": act.get("unit", ""),
            "duration_seconds": act.get("duration"),
            "note": "",
        }
        for act in activities
    ]
    draft = AiDraft.objects.create(
        therapist=therapist,
        customer=item.customer,
        # 批量子项草稿不关联父任务：父任务类型是 multi_customer_training_record，
        # 而 training_parser 的确认要求 training_record 任务；这里通过子项关联草稿。
        assistant_task_id=None,
        status=AiDraftStatus.PENDING,
        input_text=item.source_message,
        ai_result={
            "training_date": timezone.localdate().isoformat(),
            "exercises": exercises,
            "customer_feedback": "",
            "therapist_observation": "",
            "next_plan": "",
        },
    )
    item.ai_draft = draft
    item.save(update_fields=["ai_draft", "updated_at"])
    return draft


def update_item_draft(
    therapist: AbstractUser,
    task_id: int,
    item_id: int,
    confirmed: dict,
) -> AiDraft:
    """保存子项草稿的编辑（不写入正式记录）。"""
    task = _get_owned_task(therapist, task_id)
    item = _get_owned_item(therapist, task, item_id, for_update=True)
    if item.is_terminal:
        raise ValueError("该子项已处理完成，不能修改草稿")
    draft = item.ai_draft
    if draft is None or draft.status != AiDraftStatus.PENDING:
        raise ValueError("草稿不存在或已确认")
    draft.ai_result = {**draft.ai_result, **confirmed}
    draft.save(update_fields=["ai_result", "updated_at"])
    return draft


@transaction.atomic
def confirm_item_record(
    therapist: AbstractUser,
    task_id: int,
    item_id: int,
    confirmed: dict,
    idempotency_key: str,
) -> TrainingRecordBatchItem:
    """正式确认子项训练记录（幂等），完成后推进到下一子项。"""
    task = _get_owned_task(therapist, task_id, for_update=True)
    item = _get_owned_item(therapist, task, item_id, for_update=True)
    if item.status == TrainingRecordBatchItemStatus.COMPLETED:
        # 幂等：重复确认直接返回，不创建第二条记录。
        return item
    if item.status != TrainingRecordBatchItemStatus.WAITING_DRAFT:
        raise ValueError(f"子项当前状态不允许确认：{item.get_status_display()}")

    customer = item.customer
    if customer is None:
        raise ValueError("子项未确认客户")

    from apps.ai.services import training_parser

    draft = item.ai_draft
    if draft is None or draft.status != AiDraftStatus.PENDING:
        raise ValueError("草稿不存在或已确认")

    # 合并最终确认结果到草稿并调用正式确认领域服务。
    draft.ai_result = {**draft.ai_result, **confirmed}
    draft.save(update_fields=["ai_result", "updated_at"])

    try:
        confirmed_draft = training_parser.confirm_training_draft(
            therapist,
            draft.id,
            dict(confirmed),
            customer.id,
            course_session_id=None,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        item.status = TrainingRecordBatchItemStatus.FAILED
        item.error_code = "item_confirm_failed"
        item.error_message = str(exc)[:500]
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        _transition_task(
            task,
            AssistantTaskStatus.FAILED,
            current_step="item_failed",
            event_type="item_confirm_failed",
            event_data={"item_id": item.id, "error_message": str(exc)[:200]},
        )
        raise

    item.status = TrainingRecordBatchItemStatus.COMPLETED
    item.training_record = confirmed_draft.training_record
    item.confirmation_key = idempotency_key
    item.save(
        update_fields=["status", "training_record", "confirmation_key", "updated_at"]
    )

    # 推进到下一子项；若无下一项则完成父任务。
    next_item = (
        TrainingRecordBatchItem.objects.filter(
            assistant_task_id=task.id,
            status__in=[
                TrainingRecordBatchItemStatus.PENDING,
                TrainingRecordBatchItemStatus.SEARCHING_CUSTOMER,
                TrainingRecordBatchItemStatus.WAITING_CUSTOMER,
                TrainingRecordBatchItemStatus.WAITING_DRAFT,
                TrainingRecordBatchItemStatus.SAVING,
                TrainingRecordBatchItemStatus.FAILED,
            ],
        )
        .order_by("sequence")
        .first()
    )
    if next_item is None:
        _transition_task(
            task,
            AssistantTaskStatus.COMPLETED,
            current_step="complete_batch",
            event_type="batch_completed",
            event_data={"completed_item_id": item.id},
        )
    else:
        _transition_task(
            task,
            AssistantTaskStatus.WAITING_USER,
            current_step="load_next_item",
            event_type="item_advanced",
            event_data={"completed_item_id": item.id, "next_item_id": next_item.id},
        )
    return item


@transaction.atomic
def skip_item(therapist: AbstractUser, task_id: int, item_id: int) -> TrainingRecordBatchItem:
    """跳过当前子项并推进到下一项。"""
    task = _get_owned_task(therapist, task_id, for_update=True)
    item = _get_owned_item(therapist, task, item_id, for_update=True)
    if item.is_terminal:
        raise ValueError("该子项已处理完成，不能跳过")
    item.status = TrainingRecordBatchItemStatus.SKIPPED
    item.save(update_fields=["status", "updated_at"])

    next_item = (
        TrainingRecordBatchItem.objects.filter(
            assistant_task_id=task.id,
            status__in=[
                TrainingRecordBatchItemStatus.PENDING,
                TrainingRecordBatchItemStatus.SEARCHING_CUSTOMER,
                TrainingRecordBatchItemStatus.WAITING_CUSTOMER,
                TrainingRecordBatchItemStatus.WAITING_DRAFT,
                TrainingRecordBatchItemStatus.SAVING,
                TrainingRecordBatchItemStatus.FAILED,
            ],
        )
        .order_by("sequence")
        .first()
    )
    if next_item is None:
        _transition_task(task, AssistantTaskStatus.COMPLETED, current_step="complete_batch", event_type="batch_completed")
    else:
        _transition_task(task, AssistantTaskStatus.WAITING_USER, current_step="load_next_item", event_type="item_skipped", event_data={"item_id": item.id, "next_item_id": next_item.id})
    return item


def build_batch_summary(therapist: AbstractUser, task_id: int) -> dict:
    """生成批量补记处理汇总（用于最终展示）。"""
    task = _get_owned_task(therapist, task_id)
    items = list(TrainingRecordBatchItem.objects.filter(assistant_task_id=task.id).order_by("sequence"))
    total = len(items)
    succeeded = sum(1 for i in items if i.status == TrainingRecordBatchItemStatus.COMPLETED)
    skipped = sum(1 for i in items if i.status == TrainingRecordBatchItemStatus.SKIPPED)
    failed = sum(1 for i in items if i.status == TrainingRecordBatchItemStatus.FAILED)
    return {
        "task_id": task.id,
        "total_items": total,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "lines": [
            {
                "sequence": i.sequence,
                "customer_name": i.customer.name if i.customer_id else i.customer_name_hint,
                "status": i.status,
                "training_record_id": i.training_record_id,
            }
            for i in items
        ],
    }
