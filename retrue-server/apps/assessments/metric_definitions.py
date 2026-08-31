"""评估指标的单一规则来源。

康复师只需要填写临床结果，量表范围、单位、分类选项和计分方向由服务端
统一定义。Serializer 与完成评估服务都使用本模块，避免 API 和前端各自维护
一套容易漂移的规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class MetricValidationError(ValueError):
    """指标值不符合指标定义时抛出的可分类异常。"""

    code: str
    field: str
    message: str

    def __str__(self) -> str:
        return self.message


MRC_OPTIONS = (
    {"value": 0, "label": "0", "description": "未观察到肌肉收缩"},
    {"value": 1, "label": "1", "description": "可观察或触及轻微收缩"},
    {"value": 2, "label": "2", "description": "去除重力后可以完成活动"},
    {"value": 3, "label": "3", "description": "可以克服重力完成活动"},
    {"value": 4, "label": "4", "description": "可以抵抗一定阻力，但较正常弱"},
    {"value": 5, "label": "5", "description": "肌力正常"},
)

SIDE_OPTIONS = (
    {"value": "left", "label": "左侧"},
    {"value": "right", "label": "右侧"},
    {"value": "bilateral", "label": "双侧"},
    {"value": "not_applicable", "label": "不适用"},
)

CONTEXT_OPTIONS = (
    {"value": "rest", "label": "静息"},
    {"value": "activity", "label": "活动时"},
    {"value": "pre_training", "label": "训练前"},
    {"value": "post_training", "label": "训练后"},
    {"value": "night", "label": "夜间"},
    {"value": "custom", "label": "自定义"},
)

RESULT_CODE_OPTIONS = (
    {"value": "positive", "label": "阳性"},
    {"value": "negative", "label": "阴性"},
    {"value": "uncertain", "label": "无法判断"},
    {"value": "normal", "label": "正常"},
    {"value": "limited", "label": "受限"},
    {"value": "unable", "label": "无法完成"},
)


# 这里使用普通 dict 是为了让定义可以直接安全地转换为 JSON。数值范围用
# Decimal 保存，避免 ROM 小数和评分比较时受到浮点误差影响。
METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "pain": {
        "metric_type": "pain",
        "code": "NRS_0_10",
        "name": "疼痛",
        "result_type": "numeric",
        "min": 0,
        "max": 10,
        "step": 1,
        "unit": "point",
        "scoring_direction": "lower_is_better",
        "required_fields": ["body_part", "side", "context", "score"],
        "options": {"side": list(SIDE_OPTIONS), "context": list(CONTEXT_OPTIONS)},
        "description": "使用 0～10 分记录疼痛程度，0 为无痛，10 为可想象的最剧烈疼痛。",
    },
    "strength": {
        "metric_type": "strength",
        "code": "MRC_0_5",
        "name": "肌力",
        "result_type": "scale",
        "min": 0,
        "max": 5,
        "step": 1,
        "unit": "grade",
        "scoring_direction": "higher_is_better",
        "required_fields": ["body_part", "side", "movement", "score"],
        "options": {"side": list(SIDE_OPTIONS), "score": list(MRC_OPTIONS)},
        "description": "MRC 0～5 级肌力分级，选择最符合临床表现的等级。",
    },
    "rom": {
        "metric_type": "rom",
        "code": "",
        "name": "关节活动度",
        "result_type": "numeric",
        "min": 0,
        "max": 360,
        "step": 0.1,
        "unit": "degree",
        "scoring_direction": "neutral",
        "required_fields": ["body_part", "side", "movement", "measurement_mode", "score"],
        "options": {
            "side": list(SIDE_OPTIONS),
            "measurement_mode": [
                {"value": "active", "label": "主动 AROM"},
                {"value": "passive", "label": "被动 PROM"},
            ],
        },
        "description": "记录主动或被动关节活动角度，单位为度；正常参考范围按关节动作另行展示。",
    },
    "special_test": {
        "metric_type": "special_test",
        "code": "",
        "name": "特殊测试",
        "result_type": "categorical",
        "min": None,
        "max": None,
        "step": None,
        "unit": "",
        "scoring_direction": "neutral",
        "required_fields": ["details.test_name", "result_code"],
        "options": {"result_code": list(RESULT_CODE_OPTIONS[:3]), "side": list(SIDE_OPTIONS)},
        "description": "记录具体测试名称及阴性、阳性或无法判断结果，不使用数字评分。",
    },
    "functional": {
        "metric_type": "functional",
        "code": "",
        "name": "功能动作",
        "result_type": "categorical",
        "min": None,
        "max": None,
        "step": None,
        "unit": "",
        "scoring_direction": "neutral",
        "required_fields": ["movement", "result_code"],
        "options": {"result_code": list(RESULT_CODE_OPTIONS[3:])},
        "description": "记录动作完成情况和观察表现；第一期不折算为数字总分。",
    },
}


def get_metric_definition(metric_type: str) -> dict[str, Any] | None:
    """返回指定指标类型定义。"""
    return METRIC_DEFINITIONS.get(metric_type)


def metric_definitions_for_api() -> list[dict[str, Any]]:
    """返回供 API 输出的指标定义副本。"""
    # 通过递归构造普通容器，避免调用方修改模块级定义。
    import copy

    definitions = []
    for definition in METRIC_DEFINITIONS.values():
        item = copy.deepcopy(definition)
        # 保留语义明确的新字段，同时提供常见别名，方便旧前端平滑过渡。
        item["label"] = item["name"]
        item["min_value"] = item["min"]
        item["max_value"] = item["max"]
        item["score_direction"] = item["scoring_direction"]
        definitions.append(item)
    return definitions


def _value_is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MetricValidationError("metric_value_invalid", field, "指标结果必须是数字") from exc
    if not result.is_finite():
        raise MetricValidationError("metric_value_invalid", field, "指标结果必须是有限数字")
    return result


def _validate_choice(value: Any, choices: tuple[str, ...], field: str, label: str) -> None:
    if value not in choices:
        raise MetricValidationError("metric_value_invalid", field, f"{label}选项无效")


def _details_dict(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("details")
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise MetricValidationError("metric_value_invalid", "details", "指标扩展信息必须是对象")
    return details


def validate_metric_payload(payload: dict[str, Any], *, require_complete: bool = False) -> dict[str, Any]:
    """校验并返回服务端派生后的指标字段。

    草稿允许类型专用字段暂时为空，但只要填写了数值或分类结果，就必须
    符合范围和选项。完成评估时会严格要求每种指标的必填字段。

    ``score_max`` 永远由此函数按类型派生，调用方提交的值不会被信任。
    """
    metric_type = payload.get("metric_type")
    definition = get_metric_definition(metric_type)
    if definition is None:
        raise MetricValidationError("metric_type_invalid", "metric_type", "指标类型无效")

    normalized = dict(payload)
    details = _details_dict(payload)
    normalized["details"] = details

    required_fields = definition["required_fields"]
    if require_complete:
        for field in required_fields:
            if field.startswith("details."):
                value = details.get(field.split(".", 1)[1])
            else:
                value = payload.get(field)
            if _value_is_missing(value):
                raise MetricValidationError(
                    "metric_required_field_missing",
                    field,
                    f"{definition['name']}缺少必填项：{field.split('.', 1)[-1]}",
                )

    score = payload.get("score")
    if not _value_is_missing(score):
        decimal_score = _as_decimal(score, "score")
        minimum = definition["min"]
        maximum = definition["max"]
        if minimum is not None and decimal_score < Decimal(str(minimum)):
            raise MetricValidationError("metric_value_out_of_range", "score", f"{definition['name']}结果不能小于 {minimum}")
        if maximum is not None and decimal_score > Decimal(str(maximum)):
            raise MetricValidationError("metric_value_out_of_range", "score", f"{definition['name']}结果不能大于 {maximum}")
        step = definition["step"]
        if step == 1 and decimal_score != decimal_score.to_integral_value():
            raise MetricValidationError("metric_value_invalid", "score", f"{definition['name']}结果必须为整数")
        normalized["score"] = decimal_score
    elif require_complete and definition["result_type"] in {"numeric", "scale"}:
        # 缺失值已经由 required_fields 处理；这里保留清晰的兜底，避免未来
        # 修改定义后出现静默完成。
        raise MetricValidationError("metric_required_field_missing", "score", f"{definition['name']}缺少结果")

    side = payload.get("side")
    if not _value_is_missing(side):
        _validate_choice(side, ("left", "right", "bilateral", "not_applicable"), "side", "侧别")

    context = payload.get("context")
    if not _value_is_missing(context):
        _validate_choice(
            context,
            ("rest", "activity", "pre_training", "post_training", "night", "custom"),
            "context",
            "疼痛场景",
        )
        if context == "custom" and _value_is_missing(details.get("context_label")) and require_complete:
            raise MetricValidationError("metric_required_field_missing", "details.context_label", "自定义场景需要填写说明")

    measurement_mode = payload.get("measurement_mode")
    if not _value_is_missing(measurement_mode):
        _validate_choice(measurement_mode, ("active", "passive"), "measurement_mode", "测量方式")

    result_code = payload.get("result_code")
    if not _value_is_missing(result_code):
        allowed_result_codes = {
            "special_test": {"positive", "negative", "uncertain"},
            "functional": {"normal", "limited", "unable"},
        }.get(metric_type, set())
        if result_code not in allowed_result_codes:
            raise MetricValidationError("metric_value_invalid", "result_code", "指标结果选项无效")

    if metric_type == "special_test" and require_complete and _value_is_missing(details.get("test_name")):
        raise MetricValidationError("metric_required_field_missing", "details.test_name", "特殊测试需要填写测试名称")
    if metric_type == "functional" and require_complete and _value_is_missing(payload.get("movement")):
        raise MetricValidationError("metric_required_field_missing", "movement", "功能动作需要填写动作名称")

    # 类型专用的服务端派生字段。特殊测试和功能动作明确不使用分数。
    if metric_type == "pain":
        normalized.update({"scale_code": "NRS_0_10", "unit": "point", "score_max": Decimal("10")})
    elif metric_type == "strength":
        normalized.update({"scale_code": "MRC_0_5", "unit": "grade", "score_max": Decimal("5")})
    elif metric_type == "rom":
        normalized.update({"scale_code": "", "unit": "degree", "score_max": None})
    else:
        normalized.update({"scale_code": "", "unit": "", "score": None, "score_max": None})

    return normalized
