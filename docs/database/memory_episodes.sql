-- Retrue Memory Episode（实际结构以 Django migration 为准）

CREATE TABLE tb_memory_episodes (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    conversation_id BIGINT NULL,
    episode_key VARCHAR(120) NOT NULL,
    title VARCHAR(160) NOT NULL,
    summary TEXT NOT NULL,
    key_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    decisions JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    importance_score SMALLINT NOT NULL DEFAULT 3,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    status VARCHAR(12) NOT NULL DEFAULT 'candidate',
    source_start_message_id BIGINT NULL,
    source_end_message_id BIGINT NULL,
    decided_by_id BIGINT NULL,
    decided_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_episode_conversation_key UNIQUE (conversation_id, episode_key)
);

CREATE INDEX idx_episode_scope
    ON tb_memory_episodes (therapist_id, customer_id, status);
CREATE INDEX idx_episode_customer_time
    ON tb_memory_episodes (customer_id, created_at);

COMMENT ON TABLE tb_memory_episodes IS '值得跨会话回顾的历史讨论事件；不是正式训练或评估事实';
COMMENT ON COLUMN tb_memory_episodes.episode_key IS '同一会话同一主题使用的稳定事件键';
COMMENT ON COLUMN tb_memory_episodes.status IS 'candidate/active/rejected/deleted；只有 active 进入 AI 上下文';
COMMENT ON COLUMN tb_memory_episodes.source_start_message_id IS '事件来源消息范围起点';
COMMENT ON COLUMN tb_memory_episodes.source_end_message_id IS '事件来源消息范围终点';
