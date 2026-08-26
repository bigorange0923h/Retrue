-- ============================================================
-- Retrue 数据库结构参考
-- 表：course_sessions（课程/日程）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 CourseSession 模型（apps/schedules/models.py）生成。
-- V1 最小课程表，用于今日工作台展示今日客户。
-- ============================================================

CREATE TABLE schedules_coursesession (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES customers_customer(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    start_time TIME NULL,
    end_time TIME NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'scheduled',
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_course_therapist_date ON schedules_coursesession (therapist_id, date);
CREATE INDEX idx_course_customer ON schedules_coursesession (customer_id);

COMMENT ON TABLE schedules_coursesession IS '课程/日程表，V1 最小模型用于展示今日客户';
COMMENT ON COLUMN schedules_coursesession.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN schedules_coursesession.customer_id IS '关联客户 ID';
COMMENT ON COLUMN schedules_coursesession.date IS '上课日期';
COMMENT ON COLUMN schedules_coursesession.start_time IS '开始时间';
COMMENT ON COLUMN schedules_coursesession.end_time IS '结束时间';
COMMENT ON COLUMN schedules_coursesession.status IS '状态：scheduled/completed/cancelled/absent';
COMMENT ON COLUMN schedules_coursesession.created_at IS '创建时间';
COMMENT ON COLUMN schedules_coursesession.updated_at IS '更新时间';
