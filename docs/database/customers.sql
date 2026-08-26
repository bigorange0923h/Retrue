-- ============================================================
-- Retrue 数据库结构参考
-- 表：customers（客户档案）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 Customer 模型（apps/customers/models.py）生成。
-- 客户归属于康复师，用于数据隔离；列表场景默认脱敏手机号。
-- ============================================================

CREATE TABLE customers_customer (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    phone VARCHAR(20) NOT NULL DEFAULT '',
    phone_masked VARCHAR(20) NOT NULL DEFAULT '',
    gender VARCHAR(10) NOT NULL DEFAULT '',
    birth_date DATE NULL,
    occupation VARCHAR(64) NOT NULL DEFAULT '',
    sport VARCHAR(64) NOT NULL DEFAULT '',
    main_issue VARCHAR(255) NOT NULL DEFAULT '',
    injury_date DATE NULL,
    surgery_date DATE NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'active',
    first_visit_date DATE NULL,
    note VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_customer_therapist_status ON customers_customer (therapist_id, status);
CREATE INDEX idx_customer_therapist_name ON customers_customer (therapist_id, name);

COMMENT ON TABLE customers_customer IS '客户档案表，归属康复师用于数据隔离';
COMMENT ON COLUMN customers_customer.therapist_id IS '主负责康复师用户 ID，隔离依据';
COMMENT ON COLUMN customers_customer.phone IS '完整手机号，仅受控编辑场景返回';
COMMENT ON COLUMN customers_customer.phone_masked IS '脱敏手机号（如 138****1234），列表默认展示';
COMMENT ON COLUMN customers_customer.gender IS '性别：male/female';
COMMENT ON COLUMN customers_customer.main_issue IS '当前主要康复问题';
COMMENT ON COLUMN customers_customer.status IS '状态：active/paused/closed';
COMMENT ON COLUMN customers_customer.note IS '代课等备注';
COMMENT ON COLUMN customers_customer.created_at IS '创建时间';
COMMENT ON COLUMN customers_customer.updated_at IS '更新时间';
