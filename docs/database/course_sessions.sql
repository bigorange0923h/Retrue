-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_course_sessions（课程排期）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 CourseSession 模型（apps/schedules/models.py）生成。
-- 排期是日历中的实际预约，可关联客户课程计划内的一门课程；保存正式训练记录后完成并扣减课时。
-- 2026-08-31 起由 schedules/0011_course_arrangement_type.py 增加安排类型，
-- 并把历史的“有关联计划课程/无关联计划课程”分别归为 plan/other。
-- ============================================================

CREATE TABLE tb_course_sessions (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    plan_course_id BIGINT NULL,
    arrangement_type VARCHAR(24) NOT NULL DEFAULT 'other',
    session_topic VARCHAR(128) NOT NULL DEFAULT '康复训练',
    session_count NUMERIC(4,1) NOT NULL DEFAULT 1.0,
    session_consumed BOOLEAN NOT NULL DEFAULT FALSE,
    date DATE NOT NULL,
    start_time TIME NULL,
    end_time TIME NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'scheduled',
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_course_therapist_date ON tb_course_sessions (therapist_id, date);
CREATE INDEX idx_course_customer ON tb_course_sessions (customer_id);
CREATE INDEX idx_course_arrangement_date ON tb_course_sessions (therapist_id, arrangement_type, date);

-- 计划课程必须关联计划内课程；首次评估、阶段复评和其他事项不关联计划课程。
ALTER TABLE tb_course_sessions
    ADD CONSTRAINT chk_session_arrangement_plan CHECK (
        (arrangement_type = 'plan' AND plan_course_id IS NOT NULL)
        OR (arrangement_type <> 'plan' AND plan_course_id IS NULL)
    );

COMMENT ON TABLE tb_course_sessions IS '课程排期表，日历中的实际预约条目';
COMMENT ON COLUMN tb_course_sessions.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_course_sessions.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_course_sessions.plan_course_id IS '关联计划内课程 ID，可空；计划外评估或训练可不关联';
COMMENT ON COLUMN tb_course_sessions.arrangement_type IS '安排类型：plan/initial_assessment/reassessment/other';
COMMENT ON COLUMN tb_course_sessions.session_topic IS '本节训练主题，如单腿稳定性与臀肌激活';
COMMENT ON COLUMN tb_course_sessions.session_count IS '课时单位：半课 0.5 / 全课 1.0';
COMMENT ON COLUMN tb_course_sessions.session_consumed IS '是否已扣课时（幂等标记）';
COMMENT ON COLUMN tb_course_sessions.date IS '上课日期';
COMMENT ON COLUMN tb_course_sessions.start_time IS '开始时间';
COMMENT ON COLUMN tb_course_sessions.end_time IS '结束时间';
COMMENT ON COLUMN tb_course_sessions.status IS '状态：scheduled/completed/cancelled/absent';
COMMENT ON COLUMN tb_course_sessions.created_at IS '创建时间';
COMMENT ON COLUMN tb_course_sessions.updated_at IS '更新时间';
