-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_course_sessions（课程/日程）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 CourseSession 模型（apps/schedules/models.py）生成。
-- V1 最小课程表，用于今日工作台展示今日客户。
-- ============================================================

CREATE TABLE tb_course_sessions (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    course_name VARCHAR(128) NOT NULL DEFAULT '康复训练',
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

COMMENT ON TABLE tb_course_sessions IS '课程/日程表，V1 最小模型用于展示今日客户';
COMMENT ON COLUMN tb_course_sessions.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_course_sessions.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_course_sessions.course_name IS '本次课程主题，如初次评估、疼痛控制训练';
COMMENT ON COLUMN tb_course_sessions.date IS '上课日期';
COMMENT ON COLUMN tb_course_sessions.start_time IS '开始时间';
COMMENT ON COLUMN tb_course_sessions.end_time IS '结束时间';
COMMENT ON COLUMN tb_course_sessions.status IS '状态：scheduled/completed/cancelled/absent';
COMMENT ON COLUMN tb_course_sessions.created_at IS '创建时间';
COMMENT ON COLUMN tb_course_sessions.updated_at IS '更新时间';
