"""客户数据交付：按明确归属链导出正式记录，只读列出删除影响。

AI 原文和会话可能包含多客户信息，不在第一批导出中释放。
这里不提供删除、软删或脱敏执行；保留策略须另行确认。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.models import AuditAction, AuditJsonEncoder, AuditLog, write_audit_log
from apps.customers.models import Customer
from apps.customers.serializers import CustomerDetailSerializer

_PHONE_PATTERN = re.compile(r"(?<!\d)(1\d{10})(?!\d)")
_EXPORT_ROW_LIMIT = 10000


@dataclass(frozen=True)
class CustomerResource:
    """一个已明确归属的资源集；fields 非空时可以导出。"""

    key: str
    label: str
    queryset: object
    fields: tuple[str, ...] = ()


def customer_resources(therapist, customer: Customer) -> list[CustomerResource]:
    """逐项校验客户与康复师归属，子表沿已校验父表获取，不依赖数据库级联。"""
    own = {"therapist": therapist, "customer": customer}
    definitions = [
        ("aliases", "客户别称", "customers.CustomerAlias", own,
         "id alias normalized_alias is_active created_at"),
        ("assessments", "评估", "assessments.Assessment", own,
         "id plan_id assessment_type status assessment_date completed_at chief_complaint medical_history rehab_goal current_status note onset_date onset_description onset_mode aggravating_factors relieving_factors prior_care surgery_history medication exercise_habits work_demands sleep_impact created_at updated_at"),
        ("assessment_metrics", "评估指标", "assessments.AssessmentMetric",
         {"assessment__therapist": therapist, "assessment__customer": customer},
         "id assessment_id metric_type body_part score score_max description side scale_code unit context movement measurement_mode result_code details sort_order"),
        ("rehab_plans", "康复计划", "rehab.RehabPlan", own,
         "id name start_date end_date status goals note created_at updated_at"),
        ("rehab_stages", "康复阶段", "rehab.RehabStage",
         {"plan__therapist": therapist, "plan__customer": customer},
         "id plan_id stage_type start_date end_date note created_at updated_at"),
        ("plan_courses", "计划课程", "schedules.RehabPlanCourse",
         {"rehab_plan__therapist": therapist, "rehab_plan__customer": customer},
         "id rehab_plan_id course_type_id package_id status goals planned_count session_cost duration created_at updated_at"),
        ("plan_course_adjustments", "计划次数调整", "schedules.PlanCourseAdjustment",
         {"therapist": therapist, "plan_course__rehab_plan__therapist": therapist,
          "plan_course__rehab_plan__customer": customer},
         "id plan_course_id assessment_id delta_count before_count after_count reason created_at"),
        ("course_sessions", "排课", "schedules.CourseSession", own,
         "id plan_course_id arrangement_type session_topic session_count session_consumed date start_time end_time status note created_at updated_at"),
        ("course_packages", "课时包", "courses.CoursePackage", own,
         "id name total_sessions used_sessions note created_at updated_at"),
        ("course_adjustments", "课时流水", "courses.CourseAdjustment",
         {"therapist": therapist, "package__therapist": therapist, "package__customer": customer},
         "id package_id course_session_id adjustment_type delta reason created_at"),
        ("training_records", "训练记录", "training.TrainingRecord", own,
         "id course_session_id training_date customer_feedback therapist_observation next_plan note created_at updated_at"),
        ("training_exercises", "训练明细", "training.TrainingExercise",
         {"training_record__therapist": therapist, "training_record__customer": customer},
         "id training_record_id activity_type exercise_name sets reps quantity unit weight duration_seconds note sort_order"),
        ("home_training_plans", "家庭训练计划", "training.HomeTrainingPlan", own,
         "id title frequency note created_at updated_at"),
        ("home_training_exercises", "家庭训练动作", "training.HomeTrainingExercise",
         {"plan__therapist": therapist, "plan__customer": customer},
         "id plan_id exercise_name sets reps duration_seconds frequency note sort_order"),
        ("followups", "回访/复查", "followups.FollowUpTask", own,
         "id followup_type due_date content status result created_at updated_at"),
        ("risk_alerts", "风险提示", "ai.RiskAlert", own,
         "id training_record_id risk_level rule_code evidence suggested_action is_confirmed outcome created_at"),
        ("knowledge_items", "客户长期记忆", "knowledge.CustomerKnowledgeItem", own,
         "id category memory_type memory_key content source importance is_active status confidence confirmed_by_user effective_from effective_to last_confirmed_at created_at updated_at"),
        # 以下资源只列删除影响数量，不导出未审核内容或可能含其他客户的原文。
        ("knowledge_candidates", "待审记忆候选", "knowledge.KnowledgeCandidate", own, ""),
        ("memory_episodes", "讨论事件与摘要", "knowledge.MemoryEpisode", own, ""),
        ("conversations", "客户绑定会话与滚动摘要", "conversations.Conversation", own, ""),
        ("messages", "客户绑定会话消息", "conversations.Message",
         {"conversation__therapist": therapist, "conversation__customer": customer}, ""),
        ("ai_drafts", "AI 草稿", "ai.AiDraft", own, ""),
        ("assistant_tasks", "助手任务", "assistant_tasks.AssistantTask", own, ""),
        ("assistant_runs", "助手运行", "assistant_tasks.AssistantRun",
         {"task__therapist": therapist, "task__customer": customer}, ""),
        ("tool_executions", "工具执行记录", "assistant_tasks.ToolExecution",
         {"run__task__therapist": therapist, "run__task__customer": customer}, ""),
        ("task_events", "任务事件", "assistant_tasks.TaskEvent",
         {"task__therapist": therapist, "task__customer": customer}, ""),
        ("training_batch_items", "批量训练确认子项", "training.TrainingRecordBatchItem",
         {"assistant_task__therapist": therapist, "customer": customer}, ""),
    ]
    resources = [CustomerResource("customer", "客户档案", Customer.objects.filter(id=customer.id, therapist=therapist))]
    for key, label, model_name, filters, fields in definitions:
        model = apps.get_model(model_name)
        resources.append(CustomerResource(key, label, model.objects.filter(**filters).order_by("pk"), tuple(fields.split())))
    return resources


def customer_audit_queryset(therapist, resources: list[CustomerResource]):
    """查找本账号对客户资源的审计，不写入 ContentType，不释放其他账号快照。"""
    condition = Q(pk__in=[])
    for resource in resources:
        model = resource.queryset.model
        content_type = ContentType.objects.filter(app_label=model._meta.app_label, model=model._meta.model_name).first()
        if content_type is not None:
            object_ids = resource.queryset.annotate(export_object_id=Cast("pk", CharField())).values("export_object_id")
            condition |= Q(content_type=content_type, object_id__in=object_ids)
    return AuditLog.objects.filter(actor=therapist).filter(condition)


def deletion_preview(therapist, customer: Customer) -> dict:
    """只读列出关联数量和未决策略，绝不修改领域数据、向量或审计。"""
    resources = customer_resources(therapist, customer)
    counts = [{"key": item.key, "label": item.label, "count": item.queryset.count()} for item in resources]
    counts.append({"key": "audit_logs", "label": "本账号客户资源审计", "count": customer_audit_queryset(therapist, resources).count()})
    return {
        "customer_id": customer.id,
        "resources": counts,
        "can_delete": False,
        "execution_enabled": False,
        "policy_status": "待确认授权角色、保留期限、恢复期、审计与备份处理策略",
        "external_boundaries": ["备份、已下载导出文件与第三方模型记录无法由本预览统计或清除",
                                "未绑定客户或包含多客户的共享会话与草稿须单独审核，不按文本姓名自动认领"],
        "derived_content": ["长期记忆向量", "讨论事件摘要", "会话滚动摘要", "助手状态与外部持久化检查点"],
    }


def _mask_export(value, full_phone: str = ""):
    """递归脱敏结构化字段和自由文本中的手机号，保留临床内容。"""
    if isinstance(value, str):
        if full_phone:
            value = value.replace(full_phone, "[手机号已脱敏]")
        return _PHONE_PATTERN.sub(lambda match: match.group(1)[:3] + "****" + match.group(1)[-4:], value)
    if isinstance(value, dict):
        return {key: _mask_export(item, full_phone) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_export(item, full_phone) for item in value]
    return value


@transaction.atomic
def export_customer(therapist, customer: Customer, output: str) -> dict:
    """导出本账号客户的正式资料并记录访问元数据，不在日志复制健康资料。"""
    resources = customer_resources(therapist, customer)
    exported = {}
    row_count = 0
    for resource in resources:
        if not resource.fields:
            continue
        row_count += resource.queryset.count()
        if row_count > _EXPORT_ROW_LIMIT:
            raise ValidationError("客户记录数量较大，请分批导出；本次没有生成截断文件")
        rows = list(resource.queryset.values(*resource.fields))
        exported[resource.key] = rows
    profile = dict(CustomerDetailSerializer(customer).data)
    profile.pop("phone", None)
    payload = {"schema_version": 1, "exported_at": timezone.now().isoformat(), "privacy": "手机号脱敏",
               "customer": profile, "resources": exported,
               "excluded": ["AI 原始输入与未确认草稿", "可能包含多客户的会话原文、摘要和执行状态", "向量与密钥"]}
    payload = _mask_export(json.loads(json.dumps(payload, cls=AuditJsonEncoder, ensure_ascii=False)), customer.phone)
    if output == "report":
        content = _readable_report(payload, resources)
        filename, content_type = f"客户资料-{customer.id}.txt", "text/plain;charset=utf-8"
    else:
        content = payload
        filename, content_type = f"客户资料-{customer.id}.json", "application/json;charset=utf-8"
    log = write_audit_log(actor=therapist, action=AuditAction.EXPORT, obj=customer,
                          after={"output": output, "privacy": "masked", "record_count": row_count}, reason="客户资料导出")
    return {"filename": filename, "content_type": content_type, "content": content, "audit_id": log.id}


def _readable_report(payload: dict, resources: list[CustomerResource]) -> str:
    """生成不含 HTML 的中文文本报告，按领域标签和业务字段名称展示完整剂量。"""
    profile = payload["customer"]
    lines = [f"客户康复资料：{profile['name']}", f"导出时间：{payload['exported_at']}", "手机号已脱敏", "", "客户档案"]
    customer_fields = {field.name: str(field.verbose_name) for field in Customer._meta.fields}
    for key, value in profile.items():
        if key != "id" and not key.endswith("_display"):
            lines.append(f"{customer_fields.get(key, key)}：{value if value is not None else '未填写'}")
    for resource in resources:
        if not resource.fields:
            continue
        rows = payload["resources"][resource.key]
        labels = {field.attname: str(field.verbose_name) for field in resource.queryset.model._meta.fields}
        lines.extend(["", f"{resource.label}（{len(rows)}条）"])
        for index, row in enumerate(rows, 1):
            lines.append(f"{index}.")
            for field, value in row.items():
                lines.append(f"  {labels.get(field, field)}：{value if value is not None else '未填写'}")
    lines.extend(["", "未包含：" + "；".join(payload["excluded"])])
    return "\n".join(lines)
