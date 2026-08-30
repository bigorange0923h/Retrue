-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_rehab_plans（康复计划）与 tb_rehab_stages（康复阶段）
-- 说明：实际变更以 Django migration 为准。
-- AI 不自动修改康复阶段，阶段调整由康复师手动进行。
-- ============================================================

CREATE TABLE tb_rehab_plans (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    source_template_id BIGINT NULL,
    name VARCHAR(128) NOT NULL DEFAULT '默认康复计划',
    start_date DATE NOT NULL,
    end_date DATE NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'active',
    goals TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_rehabplan_therapist ON tb_rehab_plans (therapist_id, customer_id);
CREATE UNIQUE INDEX uniq_active_rehab_plan
    ON tb_rehab_plans (therapist_id, customer_id)
    WHERE status = 'active';

COMMENT ON TABLE tb_rehab_plans IS '客户课程计划表，定义客户一段课程计划的起止日期与总体目标';
COMMENT ON COLUMN tb_rehab_plans.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_rehab_plans.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_rehab_plans.source_template_id IS '创建时使用的课程计划模板，仅用于来源追溯；客户计划为独立快照';
COMMENT ON COLUMN tb_rehab_plans.status IS '状态：active/closed';
COMMENT ON COLUMN tb_rehab_plans.start_date IS '开始日期';
COMMENT ON COLUMN tb_rehab_plans.end_date IS '计划结束日期，可空';
COMMENT ON COLUMN tb_rehab_plans.goals IS '本周期总体康复目标';

CREATE TABLE tb_rehab_stages (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL,
    stage_type VARCHAR(12) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_rehabstage_plan ON tb_rehab_stages (plan_id, stage_type);
CREATE UNIQUE INDEX uniq_current_stage_per_plan
    ON tb_rehab_stages (plan_id)
    WHERE end_date IS NULL;

COMMENT ON TABLE tb_rehab_stages IS '康复阶段表，记录周期内阶段与调整历史；客户和康复师由周期派生';
COMMENT ON COLUMN tb_rehab_stages.plan_id IS '所属客户课程计划，必填';
COMMENT ON COLUMN tb_rehab_stages.stage_type IS '阶段：acute/recovery/strength/functional';
COMMENT ON COLUMN tb_rehab_stages.start_date IS '进入日期';
COMMENT ON COLUMN tb_rehab_stages.end_date IS '结束日期，空表示当前阶段';
