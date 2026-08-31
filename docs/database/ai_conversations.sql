-- Retrue AI 统一会话与消息归档（实际结构以 Django migration 为准）

CREATE TABLE tb_ai_conversations (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NULL,
    origin VARCHAR(32) NOT NULL DEFAULT 'general',
    conversation_type VARCHAR(32) NOT NULL DEFAULT 'general',
    context_resource_type VARCHAR(32) NOT NULL DEFAULT '',
    context_resource_id VARCHAR(100) NOT NULL DEFAULT '',
    title VARCHAR(120) NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    summarized_through_message_id BIGINT NULL,
    summary_updated_at TIMESTAMPTZ NULL,
    episode_analyzed_through_message_id BIGINT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_conversation_scope
    ON tb_ai_conversations (therapist_id, customer_id, status);
CREATE INDEX idx_conversation_origin
    ON tb_ai_conversations (therapist_id, origin);

COMMENT ON TABLE tb_ai_conversations IS '所有 AI 入口共用的会话；customer_id 为空表示康复师通用对话';
COMMENT ON COLUMN tb_ai_conversations.origin IS '发起入口：dashboard/customer_detail/lesson_preparation/training_record/assessment/knowledge/general';
COMMENT ON COLUMN tb_ai_conversations.context_resource_type IS '本次讨论关联的业务资源类型';
COMMENT ON COLUMN tb_ai_conversations.context_resource_id IS '关联业务资源标识，不建立数据库物理外键';
COMMENT ON COLUMN tb_ai_conversations.summary IS '最近 10 条之外的历史消息滚动摘要';
COMMENT ON COLUMN tb_ai_conversations.summarized_through_message_id IS '摘要已经覆盖到的最后一条消息 ID';
COMMENT ON COLUMN tb_ai_conversations.episode_analyzed_through_message_id IS 'Episode 提取器已经分析到的消息 ID';

CREATE TABLE tb_ai_messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL,
    role VARCHAR(12) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_message_conversation
    ON tb_ai_messages (conversation_id, created_at);

COMMENT ON TABLE tb_ai_messages IS 'AI 会话中的用户、助手、系统或工具消息';
COMMENT ON COLUMN tb_ai_messages.role IS '角色：user/assistant/system/tool';
