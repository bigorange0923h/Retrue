# 表名去重实现计划（db_table 统一命名）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为所有 Django 模型显式设置 `db_table`，统一为干净的业务表名，消除 `app_模型` 拼接导致的命名重复（如 `customers_customer`、`therapists_therapist`）。

**Architecture:** 在模型 `Meta` 中显式声明 `db_table`，通过 Django `makemigrations` 自动生成 `AlterModelTable` 迁移（安全重命名物理表，数据保留）。同步更新 `docs/database/*.sql` 文档中的表名与 README 约定。

**Tech Stack:** Django 6 / PostgreSQL / DRF

---

## 表名映射总表

| App | 模型 | 当前表名 | 目标 db_table |
|-----|------|---------|--------------|
| therapists | Therapist | therapists_therapist | therapists |
| customers | Customer | customers_customer | customers |
| schedules | CourseSession | schedules_coursesession | course_sessions |
| courses | CoursePackage | courses_coursepackage | course_packages |
| courses | CourseAdjustment | courses_courseadjustment | course_adjustments |
| training | TrainingRecord | training_trainingrecord | training_records |
| training | TrainingExercise | training_trainingexercise | training_exercises |
| training | HomeTrainingPlan | training_hometrainingplan | home_training_plans |
| training | HomeTrainingExercise | training_hometrainingexercise | home_training_exercises |
| assessments | Assessment | assessments_assessment | assessments |
| assessments | AssessmentMetric | assessments_assessmentmetric | assessment_metrics |
| rehab | RehabPlan | rehab_rehabplan | rehab_plans |
| rehab | RehabStage | rehab_rehabstage | rehab_stages |
| ai | AiDraft | ai_aidraft | ai_drafts |
| ai | RiskAlert | ai_riskalert | risk_alerts |
| followups | FollowUpTask | followups_followuptask | followup_tasks |
| exercises | Exercise | exercises_exercise | exercises |
| exercises | ExerciseAlias | exercises_exercisealias | exercise_aliases |
| accounts | User | accounts_user | 保留不变 |
| audit | AuditLog | audit_auditlog | 保留不变 |

**说明：** accounts_user 与 audit_auditlog 本身无重复词根问题，且涉及 Django 内置关联，保留默认。

---

### Task 1: 为各模型添加 db_table

**Files:**
- Modify: `retrue-server/apps/{app}/models.py`（除 accounts、audit 外全部）

**Step 1:** 在每个模型的 `class Meta` 中添加 `db_table`。

`customers/models.py` 示例：
```python
class Meta:
    db_table = "customers"
    verbose_name = "客户"
    ...
```

**Step 2:** 逐个检查 18 个模型（therapists, customers, schedules, courses×2, training×4, assessments×2, rehab×2, ai×2, followups, exercises×2）均加上 `db_table`。

**Step 3:** 运行 `python manage.py makemigrations` 生成 `AlterModelTable` 迁移。

**Step 4:** 运行 `python manage.py check` 确认无模型冲突。

**Step 5:** Commit

---

### Task 2: 应用迁移并验证

**Files:**
- 生成的迁移文件

**Step 1:** 运行 `python manage.py migrate` 应用全部 `AlterModelTable` 迁移。

**Step 2:** 运行全部测试 `python manage.py test` 确认无回归。

**Step 3:** Commit

---

### Task 3: 同步 SQL 文档

**Files:**
- Modify: `docs/database/*.sql`（18 个文件中的表名）
- Modify: `docs/database/README.md`（命名约定）

**Step 1:** 更新每个 `.sql` 文件的 `CREATE TABLE` 表名与相关 `COMMENT`。

**Step 2:** 更新 README 表名约定说明。

**Step 3:** Commit

---

### 验证检查表
- [ ] `manage.py check` 无冲突
- [ ] 全部迁移应用成功
- [ ] 全部测试通过
- [ ] SQL 文档表名与实际一致
