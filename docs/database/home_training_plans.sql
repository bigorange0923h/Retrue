-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_home_training_plans（家庭训练计划）与 tb_home_training_exercises
-- 说明：实际变更以 Django migration 为准。
-- ============================================================

CREATE TABLE tb_home_training_plans (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    title VARCHAR(128) NOT NULL DEFAULT '家庭训练',
    frequency VARCHAR(64) NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_hometrain_therapist ON tb_home_training_plans (therapist_id, customer_id);

COMMENT ON TABLE tb_home_training_plans IS '家庭训练计划表';
COMMENT ON COLUMN tb_home_training_plans.therapist_id IS '康复师用户 ID，数据隔离依据';
COMMENT ON COLUMN tb_home_training_plans.customer_id IS '关联客户 ID';
COMMENT ON COLUMN tb_home_training_plans.title IS '标题';
COMMENT ON COLUMN tb_home_training_plans.frequency IS '训练频率';
COMMENT ON COLUMN tb_home_training_plans.note IS '注意事项';

CREATE TABLE tb_home_training_exercises (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES tb_home_training_plans(id) ON DELETE CASCADE,
    exercise_name VARCHAR(128) NOT NULL,
    sets INT NULL,
    reps INT NULL,
    duration_seconds INT NULL,
    frequency VARCHAR(64) NOT NULL DEFAULT '',
    note VARCHAR(255) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0
);

COMMENT ON TABLE tb_home_training_exercises IS '家庭训练动作表';
COMMENT ON COLUMN tb_home_training_exercises.plan_id IS '所属计划 ID';
COMMENT ON COLUMN tb_home_training_exercises.exercise_name IS '动作名称';
COMMENT ON COLUMN tb_home_training_exercises.sets IS '组数';
COMMENT ON COLUMN tb_home_training_exercises.reps IS '次数';
COMMENT ON COLUMN tb_home_training_exercises.duration_seconds IS '时长（秒）';
COMMENT ON COLUMN tb_home_training_exercises.frequency IS '动作频率';
