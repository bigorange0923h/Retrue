import django.db.models.deletion
from django.db import migrations, models


def attach_historical_stages(apps, schema_editor):
    """把历史阶段归入周期，并清理即将受唯一约束的数据。"""
    RehabPlan = apps.get_model("rehab", "RehabPlan")
    RehabStage = apps.get_model("rehab", "RehabStage")

    active_groups = {}
    for plan in RehabPlan.objects.filter(status="active").order_by(
        "therapist_id", "customer_id", "-created_at", "-id"
    ):
        key = (plan.therapist_id, plan.customer_id)
        if key not in active_groups:
            active_groups[key] = plan.id
            continue
        plan.status = "closed"
        if plan.end_date is None:
            plan.end_date = plan.start_date
        plan.save(update_fields=["status", "end_date"])

    for stage in RehabStage.objects.filter(plan__isnull=True).order_by("start_date", "id"):
        plan = (
            RehabPlan.objects.filter(
                therapist_id=stage.therapist_id,
                customer_id=stage.customer_id,
                status="active",
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if plan is None:
            plan = (
                RehabPlan.objects.filter(
                    therapist_id=stage.therapist_id,
                    customer_id=stage.customer_id,
                )
                .order_by("-start_date", "-id")
                .first()
            )
        if plan is None:
            plan = RehabPlan.objects.create(
                therapist_id=stage.therapist_id,
                customer_id=stage.customer_id,
                name="历史康复周期",
                start_date=stage.start_date,
                end_date=stage.end_date,
                status="active" if stage.end_date is None else "closed",
                goals="",
                note="由历史康复阶段自动补建",
            )
        stage.plan_id = plan.id
        stage.save(update_fields=["plan"])

    plan_ids = (
        RehabStage.objects.filter(end_date__isnull=True)
        .values_list("plan_id", flat=True)
        .distinct()
    )
    for plan_id in plan_ids:
        current = list(
            RehabStage.objects.filter(plan_id=plan_id, end_date__isnull=True).order_by(
                "-start_date", "-id"
            )
        )
        if len(current) < 2:
            continue
        keep = current[0]
        for stage in current[1:]:
            stage.end_date = max(stage.start_date, keep.start_date)
            stage.save(update_fields=["end_date"])


class Migration(migrations.Migration):

    # PostgreSQL 不允许在同一原子事务中先更新外键数据、再变更该外键结构。
    atomic = False

    dependencies = [
        ("rehab", "0004_rehabplan_end_date_rehabplan_goals"),
    ]

    operations = [
        migrations.RunPython(attach_historical_stages, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="rehabstage",
            name="idx_rehabstage_customer",
        ),
        migrations.AlterField(
            model_name="rehabstage",
            name="plan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stages",
                to="rehab.rehabplan",
                verbose_name="所属计划",
            ),
        ),
        migrations.RemoveField(
            model_name="rehabstage",
            name="customer",
        ),
        migrations.RemoveField(
            model_name="rehabstage",
            name="therapist",
        ),
        migrations.AddIndex(
            model_name="rehabstage",
            index=models.Index(fields=["plan", "stage_type"], name="idx_rehabstage_plan"),
        ),
        migrations.AddConstraint(
            model_name="rehabplan",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=("therapist", "customer"),
                name="uniq_active_rehab_plan",
            ),
        ),
        migrations.AddConstraint(
            model_name="rehabstage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("end_date__isnull", True)),
                fields=("plan",),
                name="uniq_current_stage_per_plan",
            ),
        ),
    ]
