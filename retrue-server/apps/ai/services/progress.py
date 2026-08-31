"""阶段进展参考服务。

AI 从历史训练记录与评估指标中提取变化趋势，生成阶段进展参考。
AI 不自动改变康复阶段，仅提供参考供康复师判断。
"""

from __future__ import annotations

import re
from decimal import Decimal

from django.contrib.auth.models import AbstractUser

from apps.assessments.models import Assessment
from apps.training.models import TrainingRecord


def _metric_key(metric) -> tuple[str, ...]:
    """返回可安全比较的指标身份键。

    同一类型但部位、侧别、动作、场景、测量方式、量表或单位不同的
    指标不能直接比较。
    """
    return tuple(
        (getattr(metric, field, "") or "").strip().lower()
        for field in (
            "metric_type",
            "body_part",
            "side",
            "movement",
            "context",
            "measurement_mode",
            "scale_code",
            "unit",
        )
    )


def _metric_label(metric) -> str:
    """生成面向康复师的简短指标名称。"""
    parts = [metric.get_metric_type_display()]
    side = metric.get_side_display() if getattr(metric, "side", "") else ""
    for value in (metric.body_part, side, getattr(metric, "movement", "")):
        if value and value not in parts:
            parts.append(value)
    return " ".join(parts)


def _display_number(value: Decimal) -> str:
    """去除 Decimal 展示中的无意义尾零。"""
    return format(value.normalize(), "f")


def _assessment_metric_observations(assessments: list[Assessment]) -> tuple[list[str], str | None]:
    """比较最近两次已完成评估中身份一致的指标。"""
    if len(assessments) < 2:
        return [], None

    latest, previous = assessments[0], assessments[1]
    latest_metrics = {_metric_key(metric): metric for metric in latest.metrics.all()}
    previous_metrics = {_metric_key(metric): metric for metric in previous.metrics.all()}
    observations: list[str] = []
    assessment_pain_trend: str | None = None
    result_labels = {
        "positive": "阳性",
        "negative": "阴性",
        "uncertain": "无法判断",
        "normal": "正常",
        "limited": "受限",
        "unable": "无法完成",
    }

    for key, current_metric in latest_metrics.items():
        previous_metric = previous_metrics.get(key)
        if previous_metric is None:
            continue

        label = _metric_label(current_metric)
        if current_metric.score is not None and previous_metric.score is not None:
            current_value = Decimal(current_metric.score)
            previous_value = Decimal(previous_metric.score)
            before = _display_number(previous_value)
            after = _display_number(current_value)

            if current_metric.metric_type == "pain":
                if current_value < previous_value:
                    assessment_pain_trend = "改善"
                    observations.append(f"{label}由 {before} 降至 {after}，疼痛减轻")
                elif current_value > previous_value:
                    assessment_pain_trend = "加重"
                    observations.append(f"{label}由 {before} 升至 {after}，疼痛加重")
                else:
                    assessment_pain_trend = assessment_pain_trend or "平稳"
                    observations.append(f"{label}维持 {after}，疼痛评分未变")
            elif current_metric.metric_type == "strength":
                if current_value > previous_value:
                    observations.append(f"{label}由 {before} 级升至 {after} 级，肌力提高")
                elif current_value < previous_value:
                    observations.append(f"{label}由 {before} 级降至 {after} 级，需关注")
            elif current_metric.metric_type == "rom" and current_value != previous_value:
                # ROM 数值增大不必然代表改善，因此只陈述客观变化。
                observations.append(f"{label}角度由 {before}° 变为 {after}°")
            continue

        current_code = getattr(current_metric, "result_code", "")
        previous_code = getattr(previous_metric, "result_code", "")
        if current_code and previous_code and current_code != previous_code:
            observations.append(
                f"{label}由{result_labels.get(previous_code, previous_code)}变为"
                f"{result_labels.get(current_code, current_code)}"
            )

    return observations, assessment_pain_trend


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

    # 只使用已完成评估。草稿可能尚未确认，不得进入阶段进展依据。
    assessments = list(
        Assessment.objects.filter(therapist=therapist, customer_id=customer_id, status="completed")
        .prefetch_related("metrics")
        .order_by("-assessment_date", "-created_at")[:2]
    )
    metric_observations, assessment_pain_trend = _assessment_metric_observations(assessments)
    observations.extend(metric_observations)
    if pain_trend is None and assessment_pain_trend is not None:
        pain_trend = assessment_pain_trend

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
