"""阶段进展参考服务。

AI 从历史训练记录与评估指标中提取变化趋势，生成阶段进展参考。
AI 不自动改变康复阶段，仅提供参考供康复师判断。
"""

from __future__ import annotations

import re

from django.contrib.auth.models import AbstractUser

from apps.assessments.models import Assessment
from apps.training.models import TrainingRecord


def analyze_progress(therapist: AbstractUser, customer_id: int) -> dict:
    """分析客户阶段进展参考。

    参数：
        therapist: 当前康复师。
        customer_id: 客户主键。
    返回：
        含 pain_trend、observations、summary、recommendation 的字典。
    """
    records = list(
        TrainingRecord.objects.filter(therapist=therapist, customer_id=customer_id)
        .order_by("-training_date", "-created_at")[:3]
    )

    # 提取疼痛 NRS 趋势
    pain_scores = []
    for r in records:
        match = re.search(r"NRS\s*(\d+)", r.customer_feedback or "")
        if match:
            pain_scores.append(int(match.group(1)))

    observations = []
    pain_trend = None
    if len(pain_scores) >= 2:
        # records 按最新在前排序，pain_scores[0] 为最新，[-1] 为最早
        current, previous = pain_scores[0], pain_scores[-1]
        if current < previous:
            pain_trend = "改善"
            observations.append(f"疼痛由 NRS {previous} 降至 NRS {current}，明显改善")
        elif current > previous:
            pain_trend = "加重"
            observations.append(f"疼痛由 NRS {previous} 升至 NRS {current}，需关注")
        else:
            pain_trend = "平稳"
            observations.append(f"疼痛维持 NRS {previous}，未见明显变化")

    # 提取评估指标趋势（活动度/肌力）
    assessments = list(
        Assessment.objects.filter(therapist=therapist, customer_id=customer_id)
        .prefetch_related("metrics")
        .order_by("-assessment_date")[:2]
    )
    if len(assessments) >= 2:
        def metric_value(a, mtype):
            for m in a.metrics.all():
                if m.metric_type == mtype and m.score is not None:
                    return float(m.score)
            return None

        rom_now = metric_value(assessments[0], "rom")
        rom_prev = metric_value(assessments[1], "rom")
        if rom_now is not None and rom_prev is not None:
            if rom_now > rom_prev:
                observations.append(f"活动度评分由 {rom_prev} 提升至 {rom_now}，活动度改善")
            elif rom_now < rom_prev:
                observations.append(f"活动度评分由 {rom_prev} 下降至 {rom_now}，需关注")

    if not observations:
        observations.append("暂无足够的趋势数据，建议持续记录后评估")

    # 生成总结与建议（AI 不自动改阶段）
    summary = "；".join(observations)
    recommendation = "系统判断：当前存在进入下一阶段的迹象。" if pain_trend == "改善" else "系统判断：当前阶段进展需持续观察。"
    recommendation += "（康复师可手动调整阶段，AI 不会自动修改）"

    return {
        "pain_trend": pain_trend,
        "observations": observations,
        "summary": summary,
        "recommendation": recommendation,
    }
