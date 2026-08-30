-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_rehab_plan_courses（周期课程）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 RehabPlanCourse / PlanCourseAdjustment 模型（apps/schedules/models.py）生成。
-- 一个康复周期包含多门课程，每门课程有独立的计划次数、单次时长和课时消耗。
-- ============================================================

CREATE TABLE tb_rehab_plan_courses (
    id BIGSERIAL PRIMARY KEY,
    rehab_plan_id BIGINT NOT NULL REFERENCES tb_rehab_plans(id) ON DELETE CASCADE,
    course_type_id BIGINT NOT NULL REFERENCES tb_course_types(id) ON DELETE RESTRICT,
    package_id BIGINT NULL REFERENCES tb_course_packages(id) ON DELETE SET NULL,
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

COMMENT ON TABLE tb_rehab_plan_courses IS '周期课程表，定义康复周期中的课程及其计划次数';
COMMENT ON COLUMN tb_rehab_plan_courses.rehab_plan_id IS '所属康复周期计划 ID，康复师与客户归属由计划确定';
COMMENT ON COLUMN tb_rehab_plan_courses.course_type_id IS '关联课程模板 ID';
COMMENT ON COLUMN tb_rehab_plan_courses.package_id IS '关联课时包 ID，可空';
COMMENT ON COLUMN tb_rehab_plan_courses.status IS '状态：active/paused/completed/cancelled';
COMMENT ON COLUMN tb_rehab_plan_courses.goals IS '该课程在本周期内的具体目标';
COMMENT ON COLUMN tb_rehab_plan_courses.planned_count IS '计划上课次数，可由康复师根据复评结果调整';
COMMENT ON COLUMN tb_rehab_plan_courses.session_cost IS '单次课时消耗快照，不受模板后续编辑影响';
COMMENT ON COLUMN tb_rehab_plan_courses.duration IS '单次时长（分钟）快照';

CREATE TABLE tb_plan_course_adjustments (
    id BIGSERIAL PRIMARY KEY,
    plan_course_id BIGINT NOT NULL REFERENCES tb_rehab_plan_courses(id) ON DELETE CASCADE,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE RESTRICT,
    assessment_id BIGINT NULL REFERENCES tb_assessments(id) ON DELETE SET NULL,
    delta_count INT NOT NULL,
    before_count INT NOT NULL CHECK (before_count >= 0),
    after_count INT NOT NULL CHECK (after_count >= 0),
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_plan_course_adjustments IS '周期课程计划次数调整记录';
COMMENT ON COLUMN tb_plan_course_adjustments.delta_count IS '次数调整量，正数增加、负数减少';
COMMENT ON COLUMN tb_plan_course_adjustments.reason IS '康复师填写的调整原因';
COMMENT ON COLUMN tb_plan_course_adjustments.assessment_id IS '可选关联复评 ID';
