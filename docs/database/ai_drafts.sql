-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_ai_drafts（AI 生成草稿）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 AiDraft 模型（apps/ai/models.py）生成。
-- AI 只生成待确认草稿，不直接修改正式训练记录。
-- ============================================================

CREATE TABLE tb_ai_drafts (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'pending',
    input_text TEXT NOT NULL,
    ai_result JSONB NOT NULL DEFAULT '{}',
    confirmed_result JSONB NOT NULL DEFAULT '{}',
    error_message VARCHAR(500) NOT NULL DEFAULT '',
    confirmed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_ai_therapist_status ON tb_ai_drafts (therapist_id, status);

COMMENT ON TABLE tb_ai_drafts IS 'AI 生成草稿表，保存原始输入、AI 结果与确认结果';
COMMENT ON COLUMN tb_ai_drafts.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_ai_drafts.customer_id IS '关联客户 ID，客户不确定时可空';
COMMENT ON COLUMN tb_ai_drafts.status IS '状态：pending/confirmed/cancelled/failed';
COMMENT ON COLUMN tb_ai_drafts.input_text IS '用户原始输入';
COMMENT ON COLUMN tb_ai_drafts.ai_result IS 'AI 初始结构化结果（JSON）';
COMMENT ON COLUMN tb_ai_drafts.confirmed_result IS '人工确认后的最终结果（JSON）';
COMMENT ON COLUMN tb_ai_drafts.error_message IS '解析失败的错误信息';
COMMENT ON COLUMN tb_ai_drafts.confirmed_at IS '确认时间';
COMMENT ON COLUMN tb_ai_drafts.created_at IS '创建时间';
COMMENT ON COLUMN tb_ai_drafts.updated_at IS '更新时间';
