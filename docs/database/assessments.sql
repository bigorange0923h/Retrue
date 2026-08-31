-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_assessments（评估）与 tb_assessment_metrics（评估指标）
-- 说明：实际变更以 Django migration 为准。
-- 支持首次评估与阶段复评。评估可保存为 draft，只有 completed 才进入
-- 客户详情的“已完成首次评估”判断、AI 上下文和趋势分析。
-- score_max 是兼容历史数据的字段，由服务端按指标定义派生，不由康复师填写。
-- 应用条件唯一索引前，必须先按 therapist_id + customer_id 清理历史重复首评。
-- assessment_type、status 及各指标枚举值由 Django choices 和服务层校验；
-- 本参考 SQL 不额外声明 migration 中不存在的 CHECK 约束。
-- ============================================================

CREATE TABLE tb_assessments (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    plan_id BIGINT NULL,
    assessment_type VARCHAR(16) NOT NULL DEFAULT 'initial',
    status VARCHAR(16) NOT NULL DEFAULT 'draft',
    completed_at TIMESTAMPTZ NULL,
    assessment_date DATE NOT NULL,
    chief_complaint TEXT NOT NULL DEFAULT '',
    medical_history TEXT NOT NULL DEFAULT '',
    onset_date DATE NULL,
    onset_description TEXT NOT NULL DEFAULT '',
    onset_mode VARCHAR(16) NOT NULL DEFAULT 'unknown',
    aggravating_factors TEXT NOT NULL DEFAULT '',
    relieving_factors TEXT NOT NULL DEFAULT '',
    prior_care TEXT NOT NULL DEFAULT '',
    surgery_history TEXT NOT NULL DEFAULT '',
    medication TEXT NOT NULL DEFAULT '',
    exercise_habits TEXT NOT NULL DEFAULT '',
    work_demands TEXT NOT NULL DEFAULT '',
    sleep_impact TEXT NOT NULL DEFAULT '',
    rehab_goal TEXT NOT NULL DEFAULT '',
    current_status TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_assess_therapist ON tb_assessments (therapist_id, customer_id);
CREATE INDEX idx_assess_identity ON tb_assessments (therapist_id, customer_id, assessment_type);

-- 每位康复师的每位客户只能有一份首次评估；复评不受此约束。
-- 执行此索引前应先输出并处理重复数据清单。
CREATE UNIQUE INDEX uniq_initial_assessment
    ON tb_assessments (therapist_id, customer_id)
    WHERE assessment_type = 'initial';

COMMENT ON TABLE tb_assessments IS '评估表，支持首次评估与阶段复评';
COMMENT ON COLUMN tb_assessments.assessment_type IS '类型：initial/reassessment';
COMMENT ON COLUMN tb_assessments.status IS '状态：draft/completed；只有 completed 进入 AI、趋势和首次评估完成判断';
COMMENT ON COLUMN tb_assessments.completed_at IS '完成评估的时间；草稿为空';
COMMENT ON COLUMN tb_assessments.assessment_date IS '评估日期';
COMMENT ON COLUMN tb_assessments.chief_complaint IS '主诉';
COMMENT ON COLUMN tb_assessments.medical_history IS '病史';
COMMENT ON COLUMN tb_assessments.onset_date IS '症状或伤病开始日期，可为空';
COMMENT ON COLUMN tb_assessments.onset_description IS '无法确认开始日期时的文字描述';
COMMENT ON COLUMN tb_assessments.onset_mode IS '发生方式：injury/sudden/gradual/postoperative/other/unknown';
COMMENT ON COLUMN tb_assessments.aggravating_factors IS '加重因素';
COMMENT ON COLUMN tb_assessments.relieving_factors IS '缓解因素';
COMMENT ON COLUMN tb_assessments.prior_care IS '既往就医与治疗';
COMMENT ON COLUMN tb_assessments.surgery_history IS '手术史快照';
COMMENT ON COLUMN tb_assessments.medication IS '用药情况快照';
COMMENT ON COLUMN tb_assessments.exercise_habits IS '运动习惯快照';
COMMENT ON COLUMN tb_assessments.work_demands IS '工作负荷快照';
COMMENT ON COLUMN tb_assessments.sleep_impact IS '睡眠影响';
COMMENT ON COLUMN tb_assessments.rehab_goal IS '康复目标';
COMMENT ON COLUMN tb_assessments.current_status IS '当前状态（复评用）';

CREATE TABLE tb_assessment_metrics (
    id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL,
    metric_type VARCHAR(16) NOT NULL,
    body_part VARCHAR(64) NOT NULL DEFAULT '',
    side VARCHAR(24) NOT NULL DEFAULT 'not_applicable',
    scale_code VARCHAR(32) NULL,
    unit VARCHAR(16) NULL,
    context VARCHAR(32) NOT NULL DEFAULT 'custom',
    movement VARCHAR(128) NOT NULL DEFAULT '',
    measurement_mode VARCHAR(16) NULL,
    result_code VARCHAR(32) NULL,
    score DECIMAL(5,2) NULL,
    score_max DECIMAL(5,2) NULL,
    description TEXT NOT NULL DEFAULT '',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_assessment_metrics IS '评估指标表，记录疼痛/肌力/活动度/特殊测试等';
COMMENT ON COLUMN tb_assessment_metrics.metric_type IS '类型：pain/strength/rom/special_test/functional';
COMMENT ON COLUMN tb_assessment_metrics.body_part IS '部位，如左膝';
COMMENT ON COLUMN tb_assessment_metrics.side IS '侧别：left/right/bilateral/not_applicable';
COMMENT ON COLUMN tb_assessment_metrics.scale_code IS '量表代码，如 NRS_0_10、MRC_0_5；由服务端按类型派生';
COMMENT ON COLUMN tb_assessment_metrics.unit IS '单位：point/grade/degree 等；由服务端按类型派生';
COMMENT ON COLUMN tb_assessment_metrics.context IS '评估场景：rest/activity/pre_training/post_training/night/custom';
COMMENT ON COLUMN tb_assessment_metrics.movement IS '动作、关节方向或肌群动作';
COMMENT ON COLUMN tb_assessment_metrics.measurement_mode IS 'ROM 测量方式：active/passive';
COMMENT ON COLUMN tb_assessment_metrics.result_code IS '分类结果，如 positive/negative/uncertain 或 normal/limited/unable';
COMMENT ON COLUMN tb_assessment_metrics.score IS '数值结果兼容字段：疼痛 0-10、肌力 0-5、ROM 角度；不是通用评分';
COMMENT ON COLUMN tb_assessment_metrics.score_max IS '兼容历史字段；仅服务端派生，疼痛=10、肌力=5，ROM/特殊测试/功能观察=null';
COMMENT ON COLUMN tb_assessment_metrics.details IS '指标类型专用扩展 JSON，如测试名称、疼痛性质、诱发动作和观察描述';
COMMENT ON COLUMN tb_assessment_metrics.description IS '描述（诱发动作、阳性意义等）';
