-- ============================================================
-- Retrue 数据库结构参考
-- 表：assessments（评估）与 assessment_metrics（评估指标）
-- 说明：实际变更以 Django migration 为准。
-- 支持首次评估与阶段复评，指标含疼痛 NRS、肌力分级、活动度等。
-- ============================================================

CREATE TABLE assessments_assessment (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES customers_customer(id) ON DELETE CASCADE,
    plan_id BIGINT NULL REFERENCES rehab_rehabplan(id) ON DELETE SET NULL,
    assessment_type VARCHAR(16) NOT NULL DEFAULT 'initial',
    assessment_date DATE NOT NULL,
    chief_complaint TEXT NOT NULL DEFAULT '',
    medical_history TEXT NOT NULL DEFAULT '',
    rehab_goal TEXT NOT NULL DEFAULT '',
    current_status TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_assess_therapist ON assessments_assessment (therapist_id, customer_id);

COMMENT ON TABLE assessments_assessment IS '评估表，支持首次评估与阶段复评';
COMMENT ON COLUMN assessments_assessment.assessment_type IS '类型：initial/reassessment';
COMMENT ON COLUMN assessments_assessment.assessment_date IS '评估日期';
COMMENT ON COLUMN assessments_assessment.chief_complaint IS '主诉';
COMMENT ON COLUMN assessments_assessment.medical_history IS '病史';
COMMENT ON COLUMN assessments_assessment.rehab_goal IS '康复目标';
COMMENT ON COLUMN assessments_assessment.current_status IS '当前状态（复评用）';

CREATE TABLE assessments_assessmentmetric (
    id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL REFERENCES assessments_assessment(id) ON DELETE CASCADE,
    metric_type VARCHAR(16) NOT NULL,
    body_part VARCHAR(64) NOT NULL DEFAULT '',
    score DECIMAL(5,2) NULL,
    score_max DECIMAL(5,2) NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE assessments_assessmentmetric IS '评估指标表，记录疼痛/肌力/活动度/特殊测试等';
COMMENT ON COLUMN assessments_assessmentmetric.metric_type IS '类型：pain/strength/rom/special_test/functional';
COMMENT ON COLUMN assessments_assessmentmetric.body_part IS '部位，如左膝';
COMMENT ON COLUMN assessments_assessmentmetric.score IS '评分（疼痛 NRS、肌力 0-5 级等）';
COMMENT ON COLUMN assessments_assessmentmetric.score_max IS '评分满分';
COMMENT ON COLUMN assessments_assessmentmetric.description IS '描述（诱发动作、阳性意义等）';
