"""assessments：评估业务服务。"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractUser
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.assessments.metric_definitions import MetricValidationError, validate_metric_payload
from apps.assessments.models import Assessment, AssessmentStatus, AssessmentType
from apps.audit.models import AuditAction, write_audit_log


class AssessmentBusinessError(ValueError):
    """可安全返回给 API 的评估业务错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status


class InitialAssessmentExistsError(AssessmentBusinessError):
    """当前康复师与客户已经存在首次评估。"""

    def __init__(self, assessment: Assessment) -> None:
        super().__init__(
            "initial_assessment_exists",
            "该客户已有首次评估，请继续编辑已有记录",
            details={
                "assessment_id": assessment.id,
                "status": assessment.status,
            },
        )


class AssessmentCompletionError(AssessmentBusinessError):
    """评估不满足完成条件。"""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__(
            "assessment_incomplete",
            "评估信息尚未填写完整，请补充标记的内容",
            details={"errors": errors},
        )


def list_assessments(therapist: AbstractUser, customer_id: int) -> list:
    """查询某客户的评估列表，草稿和已完成记录均返回。"""
    return list(
        Assessment.objects.filter(therapist=therapist, customer_id=customer_id)
        .prefetch_related("metrics")
        .order_by("-assessment_date", "-created_at", "-id")
    )


def get_assessment(therapist: AbstractUser, assessment_id: int) -> Assessment | None:
    """获取属于当前康复师的评估。"""
    return (
        Assessment.objects.filter(therapist=therapist, id=assessment_id)
        .prefetch_related("metrics")
        .first()
    )


def get_initial_assessment(therapist: AbstractUser, customer_id: int) -> Assessment | None:
    """获取某客户的首次评估记录，不存在返回 None。"""
    return (
        Assessment.objects.filter(
            therapist=therapist,
            customer_id=customer_id,
            assessment_type=AssessmentType.INITIAL,
        )
        .order_by("assessment_date", "created_at", "id")
        .first()
    )


def validate_relationships(
    therapist: AbstractUser,
    data: dict[str, Any],
    *,
    instance: Assessment | None = None,
) -> None:
    """校验客户、计划和康复师三者归属关系。"""
    customer = data.get("customer") or (instance.customer if instance is not None else None)
    if customer is None:
        raise AssessmentBusinessError("customer_required", "请选择评估客户")
    if customer.therapist_id != therapist.id:
        raise AssessmentBusinessError("customer_therapist_mismatch", "无权操作该客户的评估", http_status=403)

    if instance is not None and instance.therapist_id != therapist.id:
        raise AssessmentBusinessError("assessment_therapist_mismatch", "无权操作该评估", http_status=403)

    plan = data.get("plan") if "plan" in data else (instance.plan if instance is not None else None)
    if plan is not None and (
        plan.therapist_id != therapist.id or plan.customer_id != customer.id
    ):
        raise AssessmentBusinessError(
            "plan_customer_mismatch",
            "康复计划必须属于当前康复师和当前客户",
        )


def ensure_initial_unique(
    therapist: AbstractUser,
    customer_id: int,
    assessment_type: str,
    *,
    exclude_id: int | None = None,
) -> None:
    """在数据库唯一约束之外提前返回可识别的重复首评错误。"""
    if assessment_type != AssessmentType.INITIAL:
        return
    queryset = Assessment.objects.filter(
        therapist=therapist,
        customer_id=customer_id,
        assessment_type=AssessmentType.INITIAL,
    ).order_by("assessment_date", "created_at", "id")
    if exclude_id is not None:
        queryset = queryset.exclude(id=exclude_id)
    existing = queryset.first()
    if existing is not None:
        raise InitialAssessmentExistsError(existing)


def _metric_payload_from_model(metric) -> dict[str, Any]:
    """把模型指标转换为纯业务校验输入。"""
    return {
        "metric_type": metric.metric_type,
        "body_part": metric.body_part,
        "side": metric.side,
        "context": metric.context,
        "movement": metric.movement,
        "measurement_mode": metric.measurement_mode,
        "score": metric.score,
        "score_max": metric.score_max,
        "scale_code": metric.scale_code,
        "unit": metric.unit,
        "result_code": metric.result_code,
        "details": metric.details,
        "description": metric.description,
    }


def validate_assessment_completion(assessment: Assessment) -> None:
    """运行完整完成校验；草稿保存不调用此函数。"""
    errors: list[dict[str, Any]] = []
    if assessment.assessment_date is None:
        errors.append({"field": "assessment_date", "code": "required", "message": "请填写评估日期"})
    if not str(assessment.chief_complaint or "").strip():
        errors.append({"field": "chief_complaint", "code": "required", "message": "请填写主要问题或不适部位"})
    if not assessment.onset_date and not str(assessment.onset_description or "").strip():
        errors.append({"field": "onset_date", "code": "required", "message": "请填写问题开始日期或描述"})
    if not str(assessment.rehab_goal or "").strip():
        errors.append({"field": "rehab_goal", "code": "required", "message": "请填写康复目标"})

    metrics = list(assessment.metrics.all())
    if not metrics:
        errors.append({"field": "metrics", "code": "required", "message": "请至少添加一项客观评估"})
    for index, metric in enumerate(metrics):
        try:
            validate_metric_payload(_metric_payload_from_model(metric), require_complete=True)
        except MetricValidationError as exc:
            errors.append(
                {
                    "field": f"metrics.{index}.{exc.field}",
                    "code": exc.code,
                    "message": exc.message,
                }
            )
    if errors:
        raise AssessmentCompletionError(errors)


@transaction.atomic
def complete_assessment(therapist: AbstractUser, assessment: Assessment) -> Assessment:
    """完整校验并将评估标记为已完成，同时记录审计。

    已完成评估被再次确认时采用“空转短路”：
    - 通过正常流程完成（``completed_at`` 非空）且完成之后未被修改
      （``updated_at <= completed_at``）的记录，直接返回，不再重复全量校验。
    - 若完成后被修订（``updated_at > completed_at``），说明内容可能已不满足
      完成条件，仍会按最新内容重新校验，避免“已完成但数据残缺”的状态。
    - 未正常完成（``completed_at`` 为空）的记录始终执行完整校验，防止绕过
      complete 接口伪造完成态。
    """
    locked = (
        Assessment.objects.select_for_update()
        .filter(therapist=therapist, id=assessment.id)
        .prefetch_related("metrics")
        .first()
    )
    if locked is None:
        raise AssessmentBusinessError("assessment_not_found", "评估不存在或无权访问", http_status=404)
    if (
        locked.status == AssessmentStatus.COMPLETED
        and locked.completed_at is not None
        and locked.updated_at <= locked.completed_at
    ):
        # 正常完成且完成后未修改：空转，直接返回。
        return locked
    # 其余情况（伪完成态、或完成后被修订）仍需按最新内容校验，不能因状态
    # 已完成而跳过完整性检查。
    validate_assessment_completion(locked)
    if locked.status == AssessmentStatus.COMPLETED:
        return locked

    before = assessment_to_dict(locked)
    locked.status = AssessmentStatus.COMPLETED
    locked.completed_at = timezone.now()
    locked.save(update_fields=["status", "completed_at", "updated_at"])
    after = assessment_to_dict(locked)
    log_assessment_change(
        therapist,
        locked,
        before=before,
        after=after,
        action=AuditAction.CONFIRM,
        reason="完成评估",
    )
    return get_assessment(therapist, locked.id) or locked


def assessment_to_dict(assessment: Assessment) -> dict:
    """将评估转为审计快照。"""
    metrics = []
    for metric in assessment.metrics.all():
        metrics.append(
            {
                "id": metric.id,
                "metric_type": metric.metric_type,
                "body_part": metric.body_part,
                "side": metric.side,
                "movement": metric.movement,
                "context": metric.context,
                "measurement_mode": metric.measurement_mode,
                "score": str(metric.score) if metric.score is not None else None,
                "score_max": str(metric.score_max) if metric.score_max is not None else None,
                "scale_code": metric.scale_code,
                "unit": metric.unit,
                "result_code": metric.result_code,
                "details": metric.details,
            }
        )
    return {
        "id": assessment.id,
        "assessment_type": assessment.assessment_type,
        "status": assessment.status,
        "completed_at": assessment.completed_at.isoformat() if assessment.completed_at else None,
        "assessment_date": assessment.assessment_date.isoformat(),
        "chief_complaint": assessment.chief_complaint,
        "rehab_goal": assessment.rehab_goal,
        "metric_count": len(metrics),
        "metrics": metrics,
    }


def log_assessment_change(
    therapist: AbstractUser,
    assessment: Assessment,
    *,
    before: dict | None,
    after: dict,
    action: str,
    reason: str,
) -> None:
    """记录评估变更审计。"""
    write_audit_log(
        actor=therapist,
        action=action,
        obj=assessment,
        before=before,
        after=after,
        reason=reason,
    )
