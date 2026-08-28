-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_rehab_plans（康复计划）与 tb_rehab_stages（康复阶段）
-- 说明：实际变更以 Django migration 为准。
-- AI 不自动修改康复阶段，阶段调整由康复师手动进行。
-- ============================================================

CREATE TABLE tb_rehab_plans (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL DEFAULT '默认康复计划',
    start_date DATE NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'active',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_rehabplan_therapist ON tb_rehab_plans (therapist_id, customer_id);

COMMENT ON TABLE tb_rehab_plans IS '康复计划表，客户康复过程框架';
COMMENT ON COLUMN tb_rehab_plans.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_rehab_plans.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_rehab_plans.status IS '状态：active/closed';
COMMENT ON COLUMN tb_rehab_plans.start_date IS '开始日期';

CREATE TABLE tb_rehab_stages (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    plan_id BIGINT NULL REFERENCES tb_rehab_plans(id) ON DELETE CASCADE,
    stage_type VARCHAR(12) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_rehabstage_customer ON tb_rehab_stages (customer_id, stage_type);

COMMENT ON TABLE tb_rehab_stages IS '康复阶段表，记录客户阶段与调整历史';
COMMENT ON COLUMN tb_rehab_stages.stage_type IS '阶段：acute/recovery/strength/functional';
COMMENT ON COLUMN tb_rehab_stages.start_date IS '进入日期';
COMMENT ON COLUMN tb_rehab_stages.end_date IS '结束日期，空表示当前阶段';
