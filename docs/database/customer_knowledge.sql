-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_customer_knowledge_items（客户知识条目）
--     tb_knowledge_candidates（AI 知识候选）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 knowledge 应用（apps/knowledge/models.py）生成。
-- 客户私有知识库按 therapist + customer 严格隔离，支持 pgvector 向量检索（RAG）。
-- ============================================================

-- 启用 pgvector 扩展（生产环境已在迁移中由 VectorExtension 创建）
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tb_customer_knowledge_items (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    category VARCHAR(16) NOT NULL DEFAULT 'other',
    memory_type VARCHAR(32) NOT NULL DEFAULT 'other',
    memory_key VARCHAR(100) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    normalized_value TEXT NOT NULL DEFAULT '',
    source VARCHAR(16) NOT NULL DEFAULT 'manual',
    source_type VARCHAR(32) NOT NULL DEFAULT '',
    source_id VARCHAR(100) NOT NULL DEFAULT '',
    source_message_id VARCHAR(100) NOT NULL DEFAULT '',
    importance VARCHAR(10) NOT NULL DEFAULT 'normal',
    importance_score SMALLINT NOT NULL DEFAULT 3,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(12) NOT NULL DEFAULT 'active',
    confirmed_by_user BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from TIMESTAMPTZ NULL,
    effective_to TIMESTAMPTZ NULL,
    last_confirmed_at TIMESTAMPTZ NULL,
    supersedes_memory_id BIGINT NULL,
    embedding VECTOR(1024) NULL,
    created_by_id BIGINT NULL,
    updated_by_id BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_knowledge_therapist ON tb_customer_knowledge_items (therapist_id, customer_id);
CREATE INDEX idx_knowledge_customer_active ON tb_customer_knowledge_items (customer_id, is_active);
CREATE INDEX idx_memory_customer_status ON tb_customer_knowledge_items (customer_id, status);

COMMENT ON TABLE tb_customer_knowledge_items IS '客户知识条目，客户私有知识库的正式知识';
COMMENT ON COLUMN tb_customer_knowledge_items.category IS '分类：medical/safety/recovery/preference/other';
COMMENT ON COLUMN tb_customer_knowledge_items.memory_type IS '长期记忆分类：preference/dislike/communication/habit/goal/concern/pattern/background/therapist_observation/other';
COMMENT ON COLUMN tb_customer_knowledge_items.status IS '生命周期：candidate/active/superseded/expired/deleted；只有 active 可进入 AI 上下文';
COMMENT ON COLUMN tb_customer_knowledge_items.content IS '知识内容';
COMMENT ON COLUMN tb_customer_knowledge_items.source IS '来源：manual/ai_confirmed/training/assessment/conversation';
COMMENT ON COLUMN tb_customer_knowledge_items.importance IS '重要级别：high/normal；安全限制高重要性优先呈现';
COMMENT ON COLUMN tb_customer_knowledge_items.is_active IS '是否生效；停用后不再参与 RAG 检索';
COMMENT ON COLUMN tb_customer_knowledge_items.embedding IS 'pgvector 向量（1024 维），用于相似度检索';
COMMENT ON COLUMN tb_customer_knowledge_items.created_by_id IS '创建人';
COMMENT ON COLUMN tb_customer_knowledge_items.updated_by_id IS '更新人';

CREATE TABLE tb_knowledge_candidates (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(16) NOT NULL DEFAULT 'other',
    memory_type VARCHAR(32) NOT NULL DEFAULT 'other',
    memory_key VARCHAR(100) NOT NULL DEFAULT '',
    normalized_value TEXT NOT NULL DEFAULT '',
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    importance_score SMALLINT NOT NULL DEFAULT 3,
    evidence TEXT NOT NULL DEFAULT '',
    conflict_type VARCHAR(16) NOT NULL DEFAULT 'none',
    conflict_memory_id BIGINT NULL,
    source_conversation_id BIGINT NULL,
    source_message_id BIGINT NULL,
    resolution_action VARCHAR(20) NOT NULL DEFAULT '',
    source_ref VARCHAR(255) NOT NULL DEFAULT '',
    suggested_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'pending',
    decided_by_id BIGINT NULL,
    decided_at TIMESTAMPTZ NULL,
    knowledge_item_id BIGINT NULL
);

CREATE INDEX idx_kc_therapist ON tb_knowledge_candidates (therapist_id, customer_id);
CREATE INDEX idx_kc_status ON tb_knowledge_candidates (status);

COMMENT ON TABLE tb_knowledge_candidates IS 'AI 建议候选记忆，需康复师确认后才转为正式知识';
COMMENT ON COLUMN tb_knowledge_candidates.content IS '拟写入内容';
COMMENT ON COLUMN tb_knowledge_candidates.source_ref IS '来源说明（训练记录/评估/对话）';
COMMENT ON COLUMN tb_knowledge_candidates.status IS '状态：pending/confirmed/rejected/deferred';
COMMENT ON COLUMN tb_knowledge_candidates.conflict_type IS '与现有有效记忆的关系：none/conflict/conditional/supplement';
COMMENT ON COLUMN tb_knowledge_candidates.conflict_memory_id IS '发生冲突或条件差异时关联的当前有效记忆';
COMMENT ON COLUMN tb_knowledge_candidates.resolution_action IS '康复师处理方式：confirm/reject/replace/keep_existing/coexist/defer';
COMMENT ON COLUMN tb_knowledge_candidates.knowledge_item_id IS '确认后生成的正式知识';
