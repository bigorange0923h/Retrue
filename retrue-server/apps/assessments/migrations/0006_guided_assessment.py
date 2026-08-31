"""引导式评估字段、指标规则与首次评估唯一性。

旧评估已经是历史正式记录，迁移时标记为已完成，避免发布后所有客户被
错误地重新提示首次评估。若历史数据存在重复首评，保留最早记录，其余
改为阶段复评后再创建条件唯一约束。
"""

from django.db import migrations, models
from django.db.models import Count, F


def migrate_legacy_assessments(apps, schema_editor):
    """将旧记录视为已完成，并按稳定顺序消解历史重复首评。"""
    Assessment = apps.get_model("assessments", "Assessment")

    # 保留原有更新时间作为完成时间，避免为所有历史数据制造同一时间点。
    Assessment.objects.all().update(status="completed", completed_at=F("updated_at"))

    duplicate_groups = (
        Assessment.objects.filter(assessment_type="initial")
        .values("therapist_id", "customer_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for group in duplicate_groups:
        records = Assessment.objects.filter(
            therapist_id=group["therapist_id"],
            customer_id=group["customer_id"],
            assessment_type="initial",
        ).order_by("assessment_date", "created_at", "id")
        # QuerySet 切片更新会生成单独 SQL，按 id 列表更新可避免在不同数据库
        # 上对带 offset 的 UPDATE 产生兼容性问题。
        duplicate_ids = list(records.values_list("id", flat=True)[1:])
        if duplicate_ids:
            Assessment.objects.filter(id__in=duplicate_ids).update(assessment_type="reassessment")


def reverse_legacy_assessments(apps, schema_editor):
    """数据迁移不可安全逆推，字段/约束回滚时保留记录类型。"""


class Migration(migrations.Migration):

    dependencies = [
        ("assessments", "0005_alter_assessment_customer_alter_assessment_plan_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="assessment",
            name="aggravating_factors",
            field=models.TextField(blank=True, default="", verbose_name="加重因素"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="完成时间"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="exercise_habits",
            field=models.TextField(blank=True, default="", verbose_name="运动习惯快照"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="medication",
            field=models.TextField(blank=True, default="", verbose_name="用药情况"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="onset_date",
            field=models.DateField(blank=True, null=True, verbose_name="问题开始日期"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="onset_description",
            field=models.TextField(blank=True, default="", verbose_name="问题开始描述"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="onset_mode",
            field=models.CharField(
                choices=[
                    ("injury", "受伤"),
                    ("sudden", "突然发作"),
                    ("gradual", "逐渐加重"),
                    ("postoperative", "术后"),
                    ("other", "其他"),
                    ("unknown", "不清楚"),
                ],
                default="unknown",
                max_length=16,
                verbose_name="发生方式",
            ),
        ),
        migrations.AddField(
            model_name="assessment",
            name="prior_care",
            field=models.TextField(blank=True, default="", verbose_name="既往就医与治疗"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="relieving_factors",
            field=models.TextField(blank=True, default="", verbose_name="缓解因素"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="surgery_history",
            field=models.TextField(blank=True, default="", verbose_name="手术史快照"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="sleep_impact",
            field=models.TextField(blank=True, default="", verbose_name="睡眠影响"),
        ),
        migrations.AddField(
            model_name="assessment",
            name="status",
            field=models.CharField(
                choices=[("draft", "草稿"), ("completed", "已完成")],
                default="draft",
                max_length=16,
                verbose_name="评估状态",
            ),
        ),
        migrations.AddField(
            model_name="assessment",
            name="work_demands",
            field=models.TextField(blank=True, default="", verbose_name="工作负荷快照"),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="context",
            field=models.CharField(
                blank=True,
                choices=[
                    ("rest", "静息"),
                    ("activity", "活动时"),
                    ("pre_training", "训练前"),
                    ("post_training", "训练后"),
                    ("night", "夜间"),
                    ("custom", "自定义"),
                ],
                default="",
                max_length=24,
                verbose_name="评估场景",
            ),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="details",
            field=models.JSONField(blank=True, default=dict, verbose_name="扩展信息"),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="measurement_mode",
            field=models.CharField(
                blank=True,
                choices=[("active", "主动 AROM"), ("passive", "被动 PROM")],
                default="",
                max_length=16,
                verbose_name="测量方式",
            ),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="movement",
            field=models.CharField(blank=True, default="", max_length=128, verbose_name="动作/肌群"),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="result_code",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="分类结果"),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="scale_code",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="量表代码"),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="side",
            field=models.CharField(
                blank=True,
                choices=[
                    ("left", "左侧"),
                    ("right", "右侧"),
                    ("bilateral", "双侧"),
                    ("not_applicable", "不适用"),
                ],
                default="",
                max_length=16,
                verbose_name="侧别",
            ),
        ),
        migrations.AddField(
            model_name="assessmentmetric",
            name="unit",
            field=models.CharField(blank=True, default="", max_length=16, verbose_name="单位"),
        ),
        migrations.AddIndex(
            model_name="assessment",
            index=models.Index(
                fields=["therapist", "customer", "assessment_type"],
                name="idx_assess_identity",
            ),
        ),
        migrations.RunPython(migrate_legacy_assessments, reverse_legacy_assessments),
        migrations.AddConstraint(
            model_name="assessment",
            constraint=models.UniqueConstraint(
                condition=models.Q(assessment_type="initial"),
                fields=("therapist", "customer"),
                name="uniq_initial_assessment",
            ),
        ),
    ]

