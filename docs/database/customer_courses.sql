-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_customer_courses（客户疗程）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 CustomerCourse 模型（apps/schedules/models.py）生成。
-- 疗程将课程类型分配给客户后形成的个体化执行单元，含快照与状态机。
-- ============================================================

CREATE TABLE tb_customer_courses (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    course_type_id BIGINT NOT NULL REFERENCES tb_course_types(id) ON DELETE RESTRICT,
    plan_id BIGINT NULL REFERENCES tb_rehab_plans(id) ON DELETE SET NULL,
    package_id BIGINT NULL REFERENCES tb_course_packages(id) ON DELETE SET NULL,
    stage_type VARCHAR(12) NOT NULL DEFAULT '',
    start_date DATE NULL,
    end_date DATE NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'pending',
    individual_goals TEXT NOT NULL DEFAULT '',
    planned_sessions NUMERIC(6,1) NULL,
    session_cost NUMERIC(4,1) NOT NULL DEFAULT 1.0,
    duration INT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_custcourse_therapist ON tb_customer_courses (therapist_id, customer_id);
CREATE INDEX idx_custcourse_customer_status ON tb_customer_courses (customer_id, status);

COMMENT ON TABLE tb_customer_courses IS '客户疗程表，将课程类型分配给客户后的执行单元';
COMMENT ON COLUMN tb_customer_courses.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_customer_courses.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_customer_courses.course_type_id IS '关联课程类型 ID';
COMMENT ON COLUMN tb_customer_courses.plan_id IS '可选关联康复计划';
COMMENT ON COLUMN tb_customer_courses.package_id IS '可选关联课时包';
COMMENT ON COLUMN tb_customer_courses.status IS '状态：pending/active/paused/completed/cancelled';
COMMENT ON COLUMN tb_customer_courses.session_cost IS '单节课时消耗快照，不受课程类型后续编辑影响';
COMMENT ON COLUMN tb_customer_courses.duration IS '单节课时长（分钟）快照';
COMMENT ON COLUMN tb_customer_courses.planned_sessions IS '计划课次/课时';
