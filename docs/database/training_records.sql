-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_training_records（训练记录）与 tb_training_exercises（训练动作）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 TrainingRecord / TrainingExercise 模型生成。
-- 正式记录修订必须可追溯（配合 tb_audit_logs 保存前后快照与原因）。
-- ============================================================

CREATE TABLE tb_training_records (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    course_session_id BIGINT NULL,
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
-- 同一节非空排课只能有一条正式训练记录；未关联排课的补记允许多条。
CREATE UNIQUE INDEX uq_training_record_course_session
    ON tb_training_records (course_session_id)
    WHERE course_session_id IS NOT NULL;

COMMENT ON TABLE tb_training_records IS '训练记录表，记录康复师每节课的正式训练数据';
COMMENT ON COLUMN tb_training_records.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_training_records.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_training_records.course_session_id IS '关联课程 ID，可空';
COMMENT ON COLUMN tb_training_records.training_date IS '训练日期；TrainingRecord 本身即正式记录';
COMMENT ON COLUMN tb_training_records.customer_feedback IS '客户感受（自然语言）';
COMMENT ON COLUMN tb_training_records.therapist_observation IS '康复师观察';
COMMENT ON COLUMN tb_training_records.next_plan IS '下次计划方向';
COMMENT ON COLUMN tb_training_records.created_at IS '创建时间';
COMMENT ON COLUMN tb_training_records.updated_at IS '更新时间';

CREATE TABLE tb_training_exercises (
    id BIGSERIAL PRIMARY KEY,
    training_record_id BIGINT NOT NULL,
    activity_type VARCHAR(16) NOT NULL DEFAULT 'exercise',
    exercise_name VARCHAR(128) NOT NULL,
    sets INT NULL,
    reps INT NULL,
    quantity INT NULL,
    unit VARCHAR(16) NOT NULL DEFAULT '',
    weight VARCHAR(32) NOT NULL DEFAULT '',
    duration_seconds INT NULL,
    note VARCHAR(255) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_training_exercises IS '训练项目明细表，一条训练记录含多个项目';
COMMENT ON COLUMN tb_training_exercises.training_record_id IS '所属训练记录 ID';
COMMENT ON COLUMN tb_training_exercises.activity_type IS '项目类型：exercise 训练动作 / therapy 康复治疗 / massage 按摩';
COMMENT ON COLUMN tb_training_exercises.exercise_name IS '动作或治疗名称';
COMMENT ON COLUMN tb_training_exercises.sets IS '组数';
COMMENT ON COLUMN tb_training_exercises.reps IS '次数';
COMMENT ON COLUMN tb_training_exercises.quantity IS '数量（如按摩 1 次）';
COMMENT ON COLUMN tb_training_exercises.unit IS '单位（次/组/个等）';
COMMENT ON COLUMN tb_training_exercises.weight IS '负荷/重量';
COMMENT ON COLUMN tb_training_exercises.duration_seconds IS '时长（秒）';
COMMENT ON COLUMN tb_training_exercises.sort_order IS '展示排序';

CREATE TABLE tb_training_record_batch_items (
    id BIGSERIAL PRIMARY KEY,
    assistant_task_id BIGINT NOT NULL,
    sequence INT NOT NULL,
    source_message TEXT NOT NULL DEFAULT '',
    customer_name_hint VARCHAR(64) NOT NULL DEFAULT '',
    customer_id BIGINT NULL,
    parsed_payload JSONB NOT NULL DEFAULT '{}',
    ai_draft_id BIGINT NULL,
    training_record_id BIGINT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    confirmation_key VARCHAR(128) NOT NULL DEFAULT '',
    error_code VARCHAR(64) NOT NULL DEFAULT '',
    error_message VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_trb_item_task_status ON tb_training_record_batch_items (assistant_task_id, status);
CREATE INDEX idx_trb_item_task_seq ON tb_training_record_batch_items (assistant_task_id, sequence);
-- 同一批量任务内子项顺序唯一。
CREATE UNIQUE INDEX uniq_trb_item_task_sequence ON tb_training_record_batch_items (assistant_task_id, sequence);

COMMENT ON TABLE tb_training_record_batch_items IS '多客户批量训练补记的有序业务子项';
COMMENT ON COLUMN tb_training_record_batch_items.assistant_task_id IS '父级批量任务 ID（task_type=multi_customer_training_record）';
COMMENT ON COLUMN tb_training_record_batch_items.sequence IS '子项顺序，从 1 开始';
COMMENT ON COLUMN tb_training_record_batch_items.customer_name_hint IS '从原文识别的客户姓名提示';
COMMENT ON COLUMN tb_training_record_batch_items.status IS '子项状态：pending/searching_customer/waiting_customer/waiting_draft/saving/completed/skipped/failed/cancelled';
