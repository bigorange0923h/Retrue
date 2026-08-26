-- ============================================================
-- Retrue 数据库结构参考
-- 表：home_training_plans（家庭训练计划）与 home_training_exercises
-- 说明：实际变更以 Django migration 为准。
-- ============================================================

CREATE TABLE training_hometrainingplan (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES customers_customer(id) ON DELETE CASCADE,
    title VARCHAR(128) NOT NULL DEFAULT '家庭训练',
    frequency VARCHAR(64) NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_hometrain_therapist ON training_hometrainingplan (therapist_id, customer_id);

COMMENT ON TABLE training_hometrainingplan IS '家庭训练计划表';
COMMENT ON COLUMN training_hometrainingplan.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN training_hometrainingplan.customer_id IS '关联客户 ID';
COMMENT ON COLUMN training_hometrainingplan.title IS '标题';
COMMENT ON COLUMN training_hometrainingplan.frequency IS '训练频率';
COMMENT ON COLUMN training_hometrainingplan.note IS '注意事项';

CREATE TABLE training_hometrainingexercise (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES training_hometrainingplan(id) ON DELETE CASCADE,
    exercise_name VARCHAR(128) NOT NULL,
    sets INT NULL,
    reps INT NULL,
    duration_seconds INT NULL,
    frequency VARCHAR(64) NOT NULL DEFAULT '',
    note VARCHAR(255) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0
);

COMMENT ON TABLE training_hometrainingexercise IS '家庭训练动作表';
COMMENT ON COLUMN training_hometrainingexercise.plan_id IS '所属计划 ID';
COMMENT ON COLUMN training_hometrainingexercise.exercise_name IS '动作名称';
COMMENT ON COLUMN training_hometrainingexercise.sets IS '组数';
COMMENT ON COLUMN training_hometrainingexercise.reps IS '次数';
COMMENT ON COLUMN training_hometrainingexercise.duration_seconds IS '时长（秒）';
COMMENT ON COLUMN training_hometrainingexercise.frequency IS '动作频率';
