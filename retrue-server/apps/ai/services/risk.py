"""风险提醒服务。

从客户训练记录中检测潜在风险，结构化保存 RiskAlert。
AI 不替代诊断，仅生成提醒；是否确认与处理由康复师决定。

触发规则标识：
    nrs_high_v1  多条记录存在 NRS>=6，提示需康复师人工核查。
本服务只陈述可计算的证据（评分序列、最高、最近一次），不输出未经验证的
“连续未明显改善”等方向性结论；是否需要暂停/复查等医学判断由康复师确认。
"""

from __future__ import annotations

import re

from django.contrib.auth.models import AbstractUser

from apps.ai.models import RiskAction, RiskAlert, RiskLevel
from apps.training.models import TrainingRecord

#: 当前触发规则版本标识，写入 RiskAlert.rule_code 用于追踪与去重。
RULE_CODE_NRS_HIGH = "nrs_high_v1"

#: 参与判定的最近记录条数。
_WINDOW = 3

_NRS_PATTERN = re.compile(r"NRS\s*(\d+)")

#: NRS 合法范围 0-10；超出视为解析异常，不计入评分。
_NRS_MIN, _NRS_MAX = 0, 10


def _parse_nrs(text: str) -> int | None:
    """从一段反馈文本提取合法 NRS 评分。

    参数：
        text: 客户反馈文本。
    返回：
        0-10 的评分；没有 NRS、或数值越界（如 NRS 15）时返回 None。
    """
    match = _NRS_PATTERN.search(text or "")
    if match is None:
        return None
    value = int(match.group(1))
    if _NRS_MIN <= value <= _NRS_MAX:
        return value
    return None


def detect_risk(therapist: AbstractUser, customer_id: int, record: TrainingRecord | None = None) -> RiskAlert | None:
    """检测训练记录中的风险并保存（去重）提醒。

    规则（``nrs_high_v1``）：最近 ``_WINDOW`` 条记录中至少 2 条含合法 NRS 且
    最高值 >=6 时创建提醒。提醒描述只包含实际出现的评分序列与统计值，
    并在最近一次已明显下降时降为“复查/人工核查”提示，不做自动暂停等断言。
    同一规则在存在未确认提醒时不重复创建，而是更新该提醒避免堆积。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
        record: 本次训练记录，可空（传入时用于定位最新提醒的关联记录）。
    返回：
        创建或更新的 RiskAlert 实例；未触发风险时返回 None。
    """
    records = list(
        TrainingRecord.objects.filter(therapist=therapist, customer_id=customer_id)
        .order_by("-training_date", "-created_at")[:_WINDOW]
    )
    if not records:
        return None

    scored: list[tuple[TrainingRecord, int]] = []
    skipped_no_nrs = 0
    invalid_nrs = 0
    for r in records:
        nrs = _parse_nrs(r.customer_feedback or "")
        if nrs is None:
            if _NRS_PATTERN.search(r.customer_feedback or ""):
                invalid_nrs += 1
            else:
                skipped_no_nrs += 1
            continue
        scored.append((r, nrs))

    if len(scored) < 2:
        return None

    # scored 已按训练日期从新到旧排序。
    values = [nrs for _, nrs in scored]
    highest = max(values)
    latest = values[0]

    if highest < 6:
        return None

    # 仅陈述计算出的证据：评分序列（新→旧）、最高、最近一次、缺失/越界计数。
    notes = []
    if skipped_no_nrs:
        notes.append(f"{skipped_no_nrs} 条记录未包含可解析 NRS，不计入")
    if invalid_nrs:
        notes.append(f"{invalid_nrs} 条记录 NRS 超出 0-10 范围，不计入")
    note_text = f"（{'；'.join(notes)}）" if notes else ""
    if latest < 6:
        # 最近一次已低于阈值，较早期高位有下降迹象：只提示人工复核，不自动暂停。
        evidence = (
            f"最近 {len(scored)} 条含评分记录 NRS（新→旧）为 {values}，最高 {highest}，"
            f"最近一次 {latest} 已低于 6，较历史高位有下降迹象，是否需继续干预请人工复核{note_text}"
        )
        level = RiskLevel.MEDIUM
        action = RiskAction.REVIEW
    else:
        evidence = (
            f"最近 {len(scored)} 条含评分记录 NRS（新→旧）为 {values}，最高 {highest}，"
            f"最近一次 {latest} 仍不低于 6，是否构成持续未改善/需调整请结合临床人工判断{note_text}"
        )
        level = RiskLevel.HIGH
        action = RiskAction.PAUSE

    # 去重：同客户同规则已有未确认提醒时更新之，不重复创建。
    existing = (
        RiskAlert.objects.filter(
            therapist=therapist,
            customer_id=customer_id,
            rule_code=RULE_CODE_NRS_HIGH,
            is_confirmed=False,
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        existing.risk_level = level
        existing.evidence = evidence
        existing.suggested_action = action
        if record is not None:
            existing.training_record = record
        existing.save(
            update_fields=[
                "risk_level",
                "evidence",
                "suggested_action",
                "training_record",
            ]
        )
        return existing

    return RiskAlert.objects.create(
        therapist=therapist,
        customer_id=customer_id,
        training_record=record,
        risk_level=level,
        rule_code=RULE_CODE_NRS_HIGH,
        evidence=evidence,
        suggested_action=action,
    )
