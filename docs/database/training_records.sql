-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_training_records（训练记录）与 tb_training_exercises（训练动作）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 TrainingRecord / TrainingExercise 模型生成。
-- 正式记录修订必须可追溯（配合 tb_audit_logs 保存前后快照与原因）。
-- ============================================================

CREATE TABLE tb_training_records (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    course_session_id BIGINT NULL REFERENCES tb_course_sessions(id) ON DELETE SET NULL,
    training_date DATE NOT NULL,
    customer_feedback TEXT NOT NULL DEFAULT '',
    therapist_observation TEXT NOT NULL DEFAULT '',
    next_plan TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_tr_therapist_customer ON tb_training_records (therapist_id, customer_id);
CREATE INDEX idx_tr_customer_date ON tb_training_records (customer_id, training_date);

COMMENT ON TABLE tb_training_records IS '训练记录表，记录康复师每节课的正式训练数据';
COMMENT ON COLUMN tb_training_records.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_training_records.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_training_records.course_session_id IS '关联课程 ID，可空';
COMMENT ON COLUMN tb_training_records.training_date IS '训练日期';
COMMENT ON COLUMN tb_training_records.customer_feedback IS '客户感受（自然语言）';
COMMENT ON COLUMN tb_training_records.therapist_observation IS '康复师观察';
COMMENT ON COLUMN tb_training_records.next_plan IS '下次计划方向';
COMMENT ON COLUMN tb_training_records.created_at IS '创建时间';
COMMENT ON COLUMN tb_training_records.updated_at IS '更新时间';

CREATE TABLE tb_training_exercises (
    id BIGSERIAL PRIMARY KEY,
    training_record_id BIGINT NOT NULL REFERENCES tb_training_records(id) ON DELETE CASCADE,
    exercise_name VARCHAR(128) NOT NULL,
    sets INT NULL,
    reps INT NULL,
    weight VARCHAR(32) NOT NULL DEFAULT '',
    duration_seconds INT NULL,
    note VARCHAR(255) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_training_exercises IS '训练动作明细表，一条训练记录含多个动作';
COMMENT ON COLUMN tb_training_exercises.training_record_id IS '所属训练记录 ID';
COMMENT ON COLUMN tb_training_exercises.exercise_name IS '动作名称';
COMMENT ON COLUMN tb_training_exercises.sets IS '组数';
COMMENT ON COLUMN tb_training_exercises.reps IS '次数';
COMMENT ON COLUMN tb_training_exercises.weight IS '负荷/重量';
COMMENT ON COLUMN tb_training_exercises.duration_seconds IS '时长（秒）';
COMMENT ON COLUMN tb_training_exercises.sort_order IS '展示排序';
