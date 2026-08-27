"""风险提醒服务。

从客户训练记录中检测潜在风险，结构化保存 RiskAlert。
AI 不替代诊断，仅生成提醒；是否确认与处理由康复师决定。
"""

from __future__ import annotations

import re

from django.contrib.auth.models import AbstractUser

from apps.ai.models import RiskAlert, RiskLevel
from apps.ai.providers.factory import get_provider
from apps.training.models import TrainingRecord


def detect_risk(therapist: AbstractUser, customer_id: int, record: TrainingRecord | None = None) -> RiskAlert | None:
    """检测训练记录中的风险并保存提醒。

    规则：客户反馈中 NRS >= 6 且连续多次未改善，判定为高风险并提醒。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
        record: 本次训练记录，可空。
    返回：
        创建的 RiskAlert 实例；未触发风险时返回 None。
    """
    # 取最近几条记录
    records = list(
        TrainingRecord.objects.filter(therapist=therapist, customer_id=customer_id)
        .order_by("-training_date", "-created_at")[:3]
    )
    if not records:
        return None

    # 从反馈中提取 NRS 评分
    scores = []
    for r in records:
        match = re.search(r"NRS\s*(\d+)", r.customer_feedback or "")
        if match:
            scores.append(int(match.group(1)))

    if not scores:
        return None

    highest = max(scores)
    # 连续记录均有疼痛且最高 NRS >= 6，触发高风险提醒
    if highest >= 6 and len(scores) >= 2:
        alert = RiskAlert.objects.create(
            therapist=therapist,
            customer_id=customer_id,
            training_record=record,
            risk_level=RiskLevel.HIGH,
            evidence=f"最近 {len(records)} 次训练记录中检测到疼痛 NRS {scores}，最高 {highest}，连续未明显改善",
            suggested_action="pause",
        )
        return alert
    return None
