"""评估录入的 LangGraph：校验上下文、抽取、逐项证据检查、保存候选。

只发送本次明确输入的文字，不读取历史临床结果；不直接写评估内容。
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

from django.utils import timezone
from langgraph.graph import END, START, StateGraph
from rest_framework import serializers
from pydantic import BaseModel, ConfigDict, ValidationError

from apps.ai.models import AiDraft, AiDraftStatus, AiDraftType
from apps.ai.prompts.loader import load_prompt, render_prompt
from apps.ai.providers.factory import get_provider
from apps.ai.services.structured_extraction import validate_candidate
from apps.assessments.metric_definitions import MetricValidationError, validate_metric_payload
from apps.assessments.models import Assessment
from apps.customers.models import Customer


TEXT_FIELDS = (
    "chief_complaint", "onset_description", "medical_history", "aggravating_factors",
    "relieving_factors", "prior_care", "surgery_history", "medication", "exercise_habits",
    "work_demands", "sleep_impact", "rehab_goal", "current_status", "note",
)
DATE_FIELDS = ("assessment_date", "onset_date")
CHOICE_EVIDENCE = {
    "left": r"左", "right": r"右", "bilateral": r"双|两侧", "not_applicable": r"不适用",
    "rest": r"静息|休息时", "activity": r"活动|下蹲|上下楼|下楼|上楼|行走|走路|跑步",
    "pre_training": r"训练前", "post_training": r"训练后", "night": r"夜间|夜里",
    "active": r"主动", "passive": r"被动", "positive": r"阳性", "negative": r"阴性",
    "uncertain": r"无法判断|不确定", "normal": r"正常", "limited": r"受限", "unable": r"无法完成",
    "injury": r"受伤", "sudden": r"突然", "gradual": r"逐渐", "postoperative": r"术后",
    "unknown": r"不清楚|未知", "other": r"其他",
}
METRIC_EVIDENCE = {
    "pain": r"疼|痛|NRS", "strength": r"肌力|MRC", "rom": r"活动度|AROM|PROM|度|°",
    "special_test": r"测试|试验", "functional": r"动作|功能|下蹲|步行|行走|上下楼",
}


class InputEnvelope(BaseModel):
    """只约束顶层容器；单项错误留给验证节点分别降级。"""

    fields: list[Any] = []
    metrics: list[Any] = []


class InputField(BaseModel):
    """文字候选的严格字段类型，避免容器/null 被当成临床文字。"""

    model_config = ConfigDict(strict=True, extra="forbid")
    field: str
    value: str
    evidence: str


class InputState(TypedDict, total=False):
    """本次图内状态；不将模型调用对象或健康原文写入日志。"""

    therapist: Any
    customer_id: int
    assessment_id: int | None
    assessment_type: str
    input_text: str
    customer: Any
    raw: Any
    candidate: dict
    draft: Any


def authorize(state: InputState) -> dict:
    """任何模型调用前先确认客户、目标评估与生命周期归属。"""
    customer = Customer.objects.filter(id=state["customer_id"], therapist=state["therapist"]).first()
    if customer is None:
        raise serializers.ValidationError({"customer_id": "客户不存在或无权访问"})
    if state.get("assessment_id"):
        target = Assessment.objects.filter(
            id=state["assessment_id"], therapist=state["therapist"], customer=customer,
            assessment_type=state["assessment_type"], status="draft",
        ).first()
        if target is None:
            raise serializers.ValidationError({"assessment_id": "仅可整理当前客户的未完成评估"})
    return {"customer": customer}


def extract(state: InputState) -> dict:
    """在图节点内调用模型；只发送本次输入与无个人信息的字段规则。"""
    content = get_provider().chat(
        render_prompt("assessment_input", input_text=state["input_text"]),
        system=load_prompt("assessment_input_system"),
    )
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    raw = json.loads(cleaned)
    return {"raw": validate_candidate(InputEnvelope, raw).model_dump()}


def grounded(value: Any, quote: Any, source: str, *, choice: bool = False, numeric: bool = False) -> bool:
    """证据必须是原文片段；文本原样抽取，枚举需明确词语，数字逐 token 核对。"""
    if not isinstance(quote, str) or not quote.strip() or quote not in source or len(quote) > 500:
        return False
    if numeric:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        fractions = re.findall(r"(\d+(?:\.\d+)?)\s*/\s*(?:5|10)(?!\d)", quote)
        if fractions:
            return any(Decimal(number) == Decimal(str(value)) for number in fractions)
        return any(Decimal(number) == Decimal(str(value)) for number in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?(?![\d.])", quote))
    if not isinstance(value, str) or not value.strip():
        return False
    if choice:
        pattern = CHOICE_EVIDENCE.get(value)
        if value in ("left", "right") and "左" in quote and "右" in quote:
            return False
        # 否定/待查结果不推导成肯定枚举；保留给人工精确填写。
        if value in ("normal", "positive", "negative") and re.search(r"不正常|非正常|非阳性|非阴性|未见|未测|未做|待查|排除", quote):
            return False
        return bool(pattern and re.search(pattern, quote, re.I))
    return value in quote


def is_current_result(quote: str, source: str) -> bool:
    """局部原文不得把上次、计划或未测内容变成本次结果，歧义时保守略过。"""
    position = source.find(quote)
    clause_start = max((source.rfind(separator, 0, position) for separator in ("。", "；", ";", "\n", "！", "？")), default=-1) + 1
    context = source[clause_start:position] + quote
    history = list(re.finditer(r"上次|上周|之前|既往|以前|曾经|历史", context))
    current = list(re.finditer(r"本次|这次|刚才|今天|此次", context))
    if history and (not current or history[-1].start() > current[-1].start()):
        return False
    return not re.search(r"未测|未做|没测|没有测|没做|计划|打算|准备测|希望|目标|预计", context)


def validate(state: InputState) -> dict:
    """单项安全降级：丢弃无依据值，保留其他有效候选，不猜测正常结果。"""
    raw, source = state["raw"], state["input_text"]
    fields, metrics, warnings = [], [], []
    seen = set()
    for item in raw.get("fields", [])[:50]:
        try:
            item = InputField.model_validate(item).model_dump()
        except ValidationError:
            warnings.append("一项文字候选结构无效，已略过")
            continue
        field, value, quote = item.get("field"), item.get("value"), item.get("evidence")
        if field not in (*TEXT_FIELDS, *DATE_FIELDS, "onset_mode") or field in seen:
            warnings.append("未知或重复文字候选已略过")
            continue
        valid = grounded(value, quote, source, choice=field == "onset_mode")
        if valid and field in DATE_FIELDS:
            try:
                valid = date.fromisoformat(value).isoformat() == value
            except ValueError:
                valid = False
        if not valid:
            warnings.append("一项文字候选缺少明确原文依据，已略过")
            continue
        fields.append({"field": field, "value": value, "evidence": quote})
        seen.add(field)
    for item in raw.get("metrics", [])[:30]:
        if not isinstance(item, dict) or not isinstance(item.get("value"), dict) or not isinstance(item.get("evidence"), dict):
            warnings.append("一项评估项目结构无效，已略过")
            continue
        value, evidence = item["value"], item["evidence"]
        kind, quote = value.get("metric_type"), evidence.get("metric_type")
        if not isinstance(kind, str) or kind not in METRIC_EVIDENCE or not isinstance(quote, str) or not quote.strip() or quote not in source or len(quote) > 500 or not re.search(METRIC_EVIDENCE[kind], quote, re.I):
            warnings.append("一项评估项目类型没有原文依据，已略过")
            continue
        if not is_current_result(quote, source):
            warnings.append("历史、计划或未测项目不能当作本次结果，已略过")
            continue
        metric = {"metric_type": kind, "body_part": "", "score": None, "details": {}}
        kept_evidence = {"metric_type": quote}
        for key in ("body_part", "side", "context", "movement", "measurement_mode", "score", "result_code", "description"):
            candidate = value.get(key)
            if candidate in (None, ""):
                continue
            if grounded(candidate, evidence.get(key), quote, choice=key in ("side", "context", "measurement_mode", "result_code"), numeric=key == "score"):
                metric[key] = candidate
                kept_evidence[key] = evidence[key]
            else:
                warnings.append("评估项目中一项无依据的属性已清空，请人工补充")
        details = value.get("details") or {}
        if isinstance(details, dict) and kind == "special_test" and grounded(details.get("test_name"), evidence.get("details.test_name"), quote):
            metric["details"]["test_name"] = details["test_name"]
            kept_evidence["details.test_name"] = evidence["details.test_name"]
        # 没有结果的项目不自动加入整套检查；有明确结果但缺侧别等，可人工补齐。
        if metric.get("score") is None and not metric.get("result_code"):
            warnings.append("未提供实际结果的评估项目已略过")
            continue
        try:
            validate_metric_payload(metric)
        except MetricValidationError:
            warnings.append("一项评估项目结果不符合类型规则，已略过")
            continue
        metrics.append({"value": metric, "evidence": kept_evidence})
    return {"candidate": {"fields": fields, "metrics": metrics, "warnings": list(dict.fromkeys(warnings))}}


def persist(state: InputState) -> dict:
    """保存未采用候选；评估记录保持原样，人工采用后才随评估保存。"""
    result = {"input_version": 1, "assessment_type": state["assessment_type"], **state["candidate"]}
    draft = AiDraft.objects.create(
        therapist=state["therapist"], customer=state["customer"], assessment_id=state.get("assessment_id"),
        draft_type=AiDraftType.ASSESSMENT, status=AiDraftStatus.PENDING,
        input_text=state["input_text"], ai_result=result,
    )
    return {"draft": draft}


def organize_assessment_input(**context: Any) -> AiDraft:
    """运行明确的评估输入编排，返回持久化候选，异常由接口脱敏处理。"""
    graph = StateGraph(InputState)
    for name, node in (("authorize", authorize), ("extract", extract), ("validate", validate), ("persist", persist)):
        graph.add_node(name, node)
    graph.add_edge(START, "authorize")
    graph.add_edge("authorize", "extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("validate", "persist")
    graph.add_edge("persist", END)
    return graph.compile().invoke(context)["draft"]


def confirm_input_drafts(assessment: Assessment, draft_ids: list[int]) -> None:
    """与评估保存共用事务，阻止跨客户、跨评估和重复使用已采用候选。"""
    for draft_id in set(draft_ids):
        draft = AiDraft.objects.select_for_update().filter(
            id=draft_id, therapist=assessment.therapist, customer=assessment.customer,
            draft_type=AiDraftType.ASSESSMENT,
        ).first()
        if (draft is None or draft.ai_result.get("input_version") != 1
                or draft.ai_result.get("assessment_type") != assessment.assessment_type
                or draft.assessment_id not in (None, assessment.id)
                or draft.status not in (AiDraftStatus.PENDING, AiDraftStatus.CONFIRMED)):
            raise serializers.ValidationError({"ai_input_draft_ids": "候选不存在、已取消或不属于当前评估"})
        if draft.status == AiDraftStatus.CONFIRMED:
            continue
        from apps.assessments.serializers import AssessmentSerializer

        draft.status = AiDraftStatus.CONFIRMED
        draft.assessment = assessment
        draft.confirmed_result = dict(AssessmentSerializer(assessment).data)
        draft.confirmed_at = timezone.now()
        draft.save(update_fields=["status", "assessment", "confirmed_result", "confirmed_at", "updated_at"])
