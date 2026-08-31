-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_rehab_plan_courses（计划内课程）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 RehabPlanCourse / PlanCourseAdjustment 模型（apps/schedules/models.py）生成。
-- 一个客户课程计划包含多门课程，每门课程有独立的计划次数、单次时长和课时消耗。
-- 课程排期通过 tb_course_sessions.plan_course_id 关联本表；进度统计由 API
-- 根据排期实时计算，不在本表冗余保存，避免“计划次数”和“课表次数”脱节。
-- ============================================================

CREATE TABLE tb_rehab_plan_courses (
    id BIGSERIAL PRIMARY KEY,
    rehab_plan_id BIGINT NOT NULL,
    course_type_id BIGINT NOT NULL,
    package_id BIGINT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'active',
    goals TEXT NOT NULL DEFAULT '',
    planned_count INT NOT NULL DEFAULT 1 CHECK (planned_count >= 0),
    session_cost NUMERIC(4,1) NOT NULL DEFAULT 1.0,
    duration INT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_plancourse_plan_status ON tb_rehab_plan_courses (rehab_plan_id, status);
CREATE INDEX idx_plancourse_type ON tb_rehab_plan_courses (course_type_id);

COMMENT ON TABLE tb_rehab_plan_courses IS '计划内课程表，定义客户课程计划中的课程及其计划次数';
COMMENT ON COLUMN tb_rehab_plan_courses.rehab_plan_id IS '所属客户课程计划 ID，康复师与客户归属由计划确定';
COMMENT ON COLUMN tb_rehab_plan_courses.course_type_id IS '关联课程模板 ID';
COMMENT ON COLUMN tb_rehab_plan_courses.package_id IS '关联课时包 ID，可空';
COMMENT ON COLUMN tb_rehab_plan_courses.status IS '状态：active/paused/completed/cancelled';
COMMENT ON COLUMN tb_rehab_plan_courses.goals IS '该课程在本周期内的具体目标';
COMMENT ON COLUMN tb_rehab_plan_courses.planned_count IS '计划上课次数，可由康复师根据复评结果调整';
COMMENT ON COLUMN tb_rehab_plan_courses.session_cost IS '单次课时消耗快照，不受模板后续编辑影响';
COMMENT ON COLUMN tb_rehab_plan_courses.duration IS '单次时长（分钟）快照';

-- 以下字段是 GET /api/rehab/plan-courses/ 的实时计算结果，不是数据库列：
-- completed_count = 已完成且有正式训练记录的排期数
-- scheduled_count = status=scheduled 的有效排期数（逾期未处理仍计入）
-- unscheduled_count = max(planned_count - completed_count - scheduled_count, 0)
-- overdue_count = 日期早于今天且 status=scheduled 的排期数
-- next_session = 今天起最近一节 status=scheduled 的排期
-- remaining_count = 为兼容旧客户端保留，当前与 unscheduled_count 相同

-- 新增或改回“待上课”的计划课程排期时，服务层在事务中锁定本表记录，
-- 并保证“已完成次数 + 待上课次数”不超过 planned_count。
-- 调减 planned_count 时不得小于该两项次数；暂停/取消课程或关闭计划前，
-- 必须先处理仍为待上课的排期。时间重叠检查也由服务层完成，不是数据库唯一约束。

CREATE TABLE tb_plan_course_adjustments (
    id BIGSERIAL PRIMARY KEY,
    plan_course_id BIGINT NOT NULL,
    therapist_id BIGINT NOT NULL,
    assessment_id BIGINT NULL,
    delta_count INT NOT NULL,
    before_count INT NOT NULL CHECK (before_count >= 0),
    after_count INT NOT NULL CHECK (after_count >= 0),
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_plan_course_adjustments IS '计划内课程次数调整记录';
COMMENT ON COLUMN tb_plan_course_adjustments.delta_count IS '次数调整量，正数增加、负数减少';
COMMENT ON COLUMN tb_plan_course_adjustments.reason IS '康复师填写的调整原因';
COMMENT ON COLUMN tb_plan_course_adjustments.assessment_id IS '可选关联复评 ID';
