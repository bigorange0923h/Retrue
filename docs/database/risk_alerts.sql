-- ============================================================
-- Retrue 数据库结构参考
-- 表：risk_alerts（风险提醒）
-- 说明：实际变更以 Django migration 为准。
-- AI 不替代诊断，仅生成提醒；确认与处理由康复师决定。
-- ============================================================

CREATE TABLE ai_riskalert (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES customers_customer(id) ON DELETE CASCADE,
    training_record_id BIGINT NULL REFERENCES training_trainingrecord(id) ON DELETE SET NULL,
    risk_level VARCHAR(10) NOT NULL DEFAULT 'medium',
    evidence TEXT NOT NULL DEFAULT '',
    suggested_action VARCHAR(10) NOT NULL DEFAULT 'check',
    is_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    outcome VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_risk_therapist ON ai_riskalert (therapist_id, customer_id);

COMMENT ON TABLE ai_riskalert IS '风险提醒表，记录 AI 检测到的异常风险';
COMMENT ON COLUMN ai_riskalert.risk_level IS '风险等级：low/medium/high';
COMMENT ON COLUMN ai_riskalert.evidence IS '发现依据（AI 依据哪些历史信息判断）';
COMMENT ON COLUMN ai_riskalert.suggested_action IS '建议动作：pause/review/check/refer';
COMMENT ON COLUMN ai_riskalert.is_confirmed IS '康复师是否确认';
COMMENT ON COLUMN ai_riskalert.outcome IS '康复师最终处理结果';
COMMENT ON COLUMN ai_riskalert.created_at IS '创建时间';
