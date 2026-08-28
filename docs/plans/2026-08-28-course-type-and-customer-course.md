# 阶段 A：课程类型与客户疗程实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现"课程类型 → 客户疗程 → 课程排期 → 训练记录"四层语义，支持半课/全课课时单位，以及基于训练记录确认的自动扣课时。

**Architecture:** schedules app 新增 `CourseType`（课程目录）、`CustomerCourse`（客户疗程），`CourseSession` 迁移 `course_name→session_topic` 并新增 `customer_course` 关联与 `session_count` 课时单位；`CoursePackage` 课时单位改 Decimal 支持 0.5；服务层实现自动扣课时（课程完成 + 训练记录确认触发）。

---

## Task 1: 模型层扩展

**Files:**
- Modify: `retrue-server/apps/schedules/models.py`（新增 CourseType、CustomerCourse，扩展 CourseSession）
- Modify: `retrue-server/apps/courses/models.py`（CoursePackage 课时单位改 Decimal）
- Modify: `retrue-server/apps/training/models.py`（TrainingRecord 增加 confirmed 确认状态，供扣课时判定）

**Step 1:** schedules/models.py 新增 `CourseType`（therapist、name、description、is_active、default_duration、default_session_cost、default_stage、default_goals、default_notes）。

**Step 2:** schedules/models.py 新增 `CustomerCourse`（therapist、customer、course_type、rehab_plan 可选、start_date、end_date、status[pending/active/paused/completed/cancelled]、individual_goals、planned_sessions、session_cost/duration 快照、package 可选）。

**Step 3:** `CourseSession` 增加 `customer_course`（FK 可选）、`session_count`（Decimal 0.5/1.0），`course_name` 重命名为 `session_topic`（RenameField 保留数据）。

**Step 4:** courses/models.py `CoursePackage.total_sessions/used_sessions` 改 DecimalField（支持半课 0.5）。

**Step 5:** training/models.py `TrainingRecord` 增加 `confirmed` Boolean 字段（默认 False）。

**Step 6:** 运行 `makemigrations` 生成迁移，`check` 通过。

**Step 7:** Commit

---

## Task 2: 接口层（CourseType 与 CustomerCourse CRUD）

**Files:**
- Modify: `retrue-server/apps/schedules/serializers.py`
- Modify: `retrue-server/apps/schedules/views.py`
- Modify: `retrue-server/apps/schedules/urls.py`

**Step 1:** 新增 `CourseTypeSerializer` + `CourseTypeListView/DetailView`（CRUD，含数据隔离，停用而非删除）。

**Step 2:** 新增 `CustomerCourseSerializer`（含状态机、快照字段）+ `CustomerCourseListView/DetailView`（CRUD + 状态流转）。

**Step 3:** 更新 `CourseSessionSerializer` 支持 `customer_course`、`session_count`；排期校验客户/疗程归属一致。

**Step 4:** urls 新增 course-types/、customer-courses/ 路由。

**Step 5:** 运行 `manage.py check` + 测试。

**Step 6:** Commit

---

## Task 3: 自动扣课时服务

**Files:**
- Modify: `retrue-server/apps/courses/services.py`（新增扣减逻辑）
- Modify: `retrue-server/apps/training/views.py` 或相关确认触发点
- Modify: `retrue-server/apps/courses/models.py`（remaining_sessions 改 Decimal 支持）

**Step 1:** 实现 `deduct_sessions`：课程状态完成 + 训练记录已确认 + 疗程关联课时包 → 从 package 扣减 `session_count`，记录 `CourseAdjustment`/来源。

**Step 2:** 保证幂等（同一课程+训练记录只扣一次），取消/请假不扣。

**Step 3:** 补充单元测试。

**Step 4:** Commit

---

## Task 4: 前端

**Files:**
- Modify: `retrue-web/src/api/schedules.ts`（新增 course-types、customer-courses API）
- Modify: `retrue-web/src/types/api.ts`
- Create: `retrue-web/src/views/courses/CourseTypeListView.vue`（课程类型管理）
- Create: `retrue-web/src/views/customers/CustomerCourseView.vue`（客户疗程）
- Modify: 排课/课程管理页关联疗程
- Modify: 路由与菜单

**Step 1:** 前端类型与 API。
**Step 2:** 课程类型管理页（列表/新建/编辑/停用）。
**Step 3:** 客户疗程页（列表/新建/状态流转）。
**Step 4:** 排课关联疗程（创建课程时选择进行中的疗程）。
**Step 5:** `npm run build` 验证 + 路由/菜单。

**Step 6:** Commit

---

### 验证检查表
- [ ] `manage.py check` 无冲突
- [ ] 迁移应用成功（course_name→session_topic 数据保留）
- [ ] CourseType/CustomerCourse CRUD 测试通过
- [ ] 自动扣课时幂等且正确
- [ ] 前端构建通过
