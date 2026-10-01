"""训练草稿的保守原文依据检查，不以推测补齐临床事实。"""

from __future__ import annotations

import re
from datetime import date, timedelta

from apps.ai.schemas.training import TrainingDraft


_CHINESE_NUMBERS = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}
_NUMBER = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千]+)"


def _number_value(token: str) -> float | None:
    """解析明确的数字表达，避免把“三”匹配到“十三”内部。"""
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return float(token)
    digits = {char: value for value, char in _CHINESE_NUMBERS.items()}
    digits.update({"零": 0, "〇": 0, "两": 2})
    total = current = 0
    for char in token:
        if char in digits:
            current = digits[char]
        elif char in {"十", "百", "千"}:
            total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            current = 0
        else:
            return None
    return float(total + current)


def _quantity_supported(value: int, context: str, units: str) -> bool:
    """数字和字段单位必须同时匹配，不能借用时长或其他剂量字段。"""
    values = {
        _number_value(match["number"])
        for match in re.finditer(rf"(?<![\d.零〇一二两三四五六七八九十百千])(?P<number>{_NUMBER})\s*(?:{units})", context)
    }
    return values == {value}


def _compact(value: str) -> str:
    """仅折叠空白和常见分隔符，用于比较原文片段。"""
    return re.sub(r"[\s，,。；;：:]", "", value or "").lower()


def _exercise_context(source: str, name: str, other_names: tuple[str, ...] = ()) -> str:
    """尽量把数量限定在项目所在短句，避免借用另一项目的相同数字。"""
    if not name.strip():
        return ""
    position = source.find(name)
    if position < 0:
        return ""
    separators = "，,。；;、\n"
    start = max((source.rfind(char, 0, position) for char in separators), default=-1) + 1
    if any(other and other != name and source.find(other, start, position) >= 0 for other in other_names):
        start = position
    ends = [source.find(char, position) for char in separators]
    end = min((value for value in ends if value >= 0), default=len(source))
    # “臀桥 3 组，每组 12 次”中逗号后的每组次数仍属于同一项目。
    while continuation := re.match(r"[，,、]\s*(?:每\s*组|每次|共|有|负重|负荷|阻力|重量)[^，,、。；;\n]*", source[end:]):
        end += len(continuation.group(0))
    # 同一句没有标点时，也不能借用下一个项目的剂量。
    next_positions = [source.find(other, position + len(name)) for other in other_names if other and other != name]
    end = min([end, *(value for value in next_positions if value >= 0)])
    return source[start:end]


def _duration_supported(seconds: int, context: str) -> bool:
    """允许原文分钟或“分+秒”明确换算为秒。"""
    if _quantity_supported(seconds, context, "秒"):
        return True
    for match in re.finditer(rf"(?P<minutes>{_NUMBER})\s*分(?:钟)?(?:\s*(?P<seconds>{_NUMBER})\s*秒)?", context):
        minutes = _number_value(match["minutes"])
        remainder = _number_value(match["seconds"]) if match["seconds"] else 0
        if minutes is not None and remainder is not None and minutes * 60 + remainder == seconds:
            return True
    return False


def _weight_supported(weight: str, context: str) -> bool:
    """只接受直接命中或公斤/千克与 kg 的等价写法。"""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:kg|公斤|千克)\s*", weight, re.IGNORECASE)
    if match:
        values = {
            _number_value(item["number"])
            for item in re.finditer(rf"(?<![\d.零〇一二两三四五六七八九十百千])(?P<number>{_NUMBER})\s*(?:kg|公斤|千克)", context, re.IGNORECASE)
        }
        return values == {float(match[1])}
    return _compact(weight) in _compact(context)


def review_training_evidence(parsed: TrainingDraft, source: str, *, trusted_date: str | None = None) -> list[dict[str, str]]:
    """核查训练候选的显式依据，清空无依据数值并返回可展示的问题。"""
    issues: list[dict[str, str]] = []
    compact_source = _compact(source)
    today = date.today()
    has_relative_date = ("今天" in source and parsed.training_date == today.isoformat()) or (
        "昨天" in source and parsed.training_date == (today - timedelta(days=1)).isoformat()
    )
    has_absolute_date = bool(parsed.training_date and parsed.training_date in source)
    if trusted_date:
        parsed.training_date = trusted_date
    elif not (has_relative_date or has_absolute_date):
        issues.append({"field": "training_date", "code": "date_needs_review", "message": "训练日期缺少可核对的原文依据，已预填日期，请确认"})

    if parsed.customer_hint and _compact(parsed.customer_hint) not in compact_source:
        parsed.customer_hint = None
        issues.append({"field": "customer_hint", "code": "unsupported_customer_hint", "message": "客户姓名提示在原文中没有依据，已清空；请按客户目录选择"})

    for index, exercise in enumerate(parsed.exercises):
        field = f"exercises.{index}"
        context = _exercise_context(source, exercise.exercise_name, tuple(item.exercise_name for item in parsed.exercises))
        if not exercise.exercise_name.strip() or _compact(exercise.exercise_name) not in compact_source:
            issues.append({"field": f"{field}.exercise_name", "code": "name_needs_review", "message": f"第 {index + 1} 个项目名称未在原文中直接找到，请核对"})
        uncertain_action = bool(re.search(r"未做|没(?:有)?做|不做|未完成|没(?:有)?完成|计划|下次|准备|打算", context))
        if uncertain_action:
            issues.append({"field": f"{field}.exercise_name", "code": "action_needs_review", "message": f"第 {index + 1} 个项目涉及未执行或计划描述，请确认是否应记录为本次训练"})
        for name, label in (("sets", "组数"), ("reps", "每组次数"), ("quantity", "数量"), ("duration_seconds", "时长")):
            value = getattr(exercise, name)
            if value is None:
                continue
            # 时长允许明确换算；其他数量必须与对应单位一致，冲突时清空待补充。
            units = {"sets": "组", "reps": "次|个|下", "quantity": re.escape(exercise.unit) if exercise.unit else "次|个|下"}
            supported = not uncertain_action and (_duration_supported(value, context) if name == "duration_seconds" else _quantity_supported(value, context, units[name]))
            if not supported:
                setattr(exercise, name, None)
                issues.append({"field": f"{field}.{name}", "code": "unsupported_number", "message": f"第 {index + 1} 个项目的{label}在原文中没有依据，已清空"})
        if exercise.weight and (uncertain_action or not _weight_supported(exercise.weight, context)):
            exercise.weight = ""
            issues.append({"field": f"{field}.weight", "code": "unsupported_weight", "message": f"第 {index + 1} 个项目的负荷在原文中没有依据，已清空"})
    for field, label in (("customer_feedback", "客户感受"), ("therapist_observation", "康复师观察"), ("next_plan", "下次计划")):
        value = getattr(parsed, field)
        if value and _compact(value) not in compact_source:
            issues.append({"field": field, "code": "text_needs_review", "message": f"{label}经过整理，无法逐字定位到原文，请核对含义"})
    return issues
