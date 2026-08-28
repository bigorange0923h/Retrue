-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_followup_tasks（回访/复查待办）
-- 说明：实际变更以 Django migration 为准。
-- ============================================================

CREATE TABLE tb_followup_tasks (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    followup_type VARCHAR(12) NOT NULL DEFAULT 'visit',
    due_date DATE NOT NULL,
    content VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(12) NOT NULL DEFAULT 'pending',
    result VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_followup_therapist ON tb_followup_tasks (therapist_id, due_date);

COMMENT ON TABLE tb_followup_tasks IS '回访/复查待办表';
COMMENT ON COLUMN tb_followup_tasks.followup_type IS '类型：visit/review/other';
COMMENT ON COLUMN tb_followup_tasks.due_date IS '计划日期';
COMMENT ON COLUMN tb_followup_tasks.content IS '内容';
COMMENT ON COLUMN tb_followup_tasks.status IS '状态：pending/done/skipped';
COMMENT ON COLUMN tb_followup_tasks.result IS '完成结果';
