-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_rehab_plan_templates / tb_rehab_plan_template_courses
-- 说明：实际变更以 Django migration 为准。
-- 课程计划模板不属于客户；应用时复制为 RehabPlan / RehabPlanCourse 快照。
-- ============================================================

CREATE TABLE tb_rehab_plan_templates (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    name VARCHAR(128) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    suggested_duration_weeks SMALLINT NULL CHECK (suggested_duration_weeks >= 0),
    goals TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_rpt_therapist_active
    ON tb_rehab_plan_templates (therapist_id, is_active);

COMMENT ON TABLE tb_rehab_plan_templates IS '康复师维护的可复用课程计划模板，不承载客户进度';
COMMENT ON COLUMN tb_rehab_plan_templates.suggested_duration_weeks IS '应用模板时用于计算默认结束日期的建议周数';

CREATE TABLE tb_rehab_plan_template_courses (
    id BIGSERIAL PRIMARY KEY,
    template_id BIGINT NOT NULL,
    course_type_id BIGINT NOT NULL,
    planned_count INT NOT NULL DEFAULT 1 CHECK (planned_count > 0),
    session_cost NUMERIC(4,1) NOT NULL DEFAULT 1.0,
    duration INT NULL,
    goals TEXT NOT NULL DEFAULT '',
    sort_order SMALLINT NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uniq_rpt_course_type UNIQUE (template_id, course_type_id)
);

COMMENT ON TABLE tb_rehab_plan_template_courses IS '课程计划模板中的课程、默认次数、时长与单次课时扣减';
COMMENT ON COLUMN tb_rehab_plan_template_courses.planned_count IS '应用到客户周期时复制的默认计划次数';
COMMENT ON COLUMN tb_rehab_plan_template_courses.session_cost IS '应用到客户周期时复制的默认单次课时扣减';
