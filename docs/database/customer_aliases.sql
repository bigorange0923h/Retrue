-- 客户别称结构参考；实际结构变更以 customers migration 为准。
-- 停用保留匹配键和审计，不物理删除；不建立数据库物理外键。
CREATE TABLE tb_customer_aliases (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    alias VARCHAR(64) NOT NULL,
    normalized_alias VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uniq_therapist_normalized_alias UNIQUE (therapist_id, normalized_alias)
);
CREATE INDEX idx_alias_therapist_norm ON tb_customer_aliases (therapist_id, normalized_alias);
COMMENT ON TABLE tb_customer_aliases IS '客户别称，按康复师隔离并由领域服务校验归属和歧义';
COMMENT ON COLUMN tb_customer_aliases.therapist_id IS '康复师用户ID，必须与客户归属一致';
COMMENT ON COLUMN tb_customer_aliases.customer_id IS '明确关联的客户ID，不自动改绑';
COMMENT ON COLUMN tb_customer_aliases.normalized_alias IS '复用目录归一化规则产生的匹配键，同一康复师唯一';
COMMENT ON COLUMN tb_customer_aliases.is_active IS '启用标记；停用后退出自然语言客户匹配';
