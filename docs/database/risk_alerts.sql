-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_risk_alerts（风险提醒）
-- 说明：实际变更以 Django migration 为准。
-- AI 不替代诊断，仅生成提醒；确认与处理由康复师决定。
-- ============================================================

CREATE TABLE tb_risk_alerts (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    training_record_id BIGINT NULL,
    risk_level VARCHAR(10) NOT NULL DEFAULT 'medium',
    rule_code VARCHAR(32) NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    suggested_action VARCHAR(10) NOT NULL DEFAULT 'check',
    is_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    outcome VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_risk_therapist ON tb_risk_alerts (therapist_id, customer_id);
CREATE INDEX idx_risk_therapist_rule ON tb_risk_alerts (therapist_id, customer_id, rule_code);

COMMENT ON TABLE tb_risk_alerts IS '风险提醒表，记录 AI 检测到的异常风险';
COMMENT ON COLUMN tb_risk_alerts.risk_level IS '风险等级：low/medium/high';
COMMENT ON COLUMN tb_risk_alerts.rule_code IS '触发规则代码与版本（如 nrs_high_v1），用于追踪与重复触发去重';
COMMENT ON COLUMN tb_risk_alerts.evidence IS '发现依据（AI 依据哪些历史信息判断）';
COMMENT ON COLUMN tb_risk_alerts.suggested_action IS '建议动作：pause/review/check/refer';
COMMENT ON COLUMN tb_risk_alerts.is_confirmed IS '康复师是否确认';
COMMENT ON COLUMN tb_risk_alerts.outcome IS '康复师最终处理结果';
COMMENT ON COLUMN tb_risk_alerts.created_at IS '创建时间';
