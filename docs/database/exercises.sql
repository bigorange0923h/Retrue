-- ============================================================
-- Retrue 数据库结构参考
-- 表：exercises（动作库）与 exercise_aliases（动作别名）
-- 说明：实际变更以 Django migration 为准。
-- 官方动作由系统维护，个人动作由康复师创建。
-- ============================================================

CREATE TABLE exercises_exercise (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NULL REFERENCES accounts_user(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL,
    body_part VARCHAR(64) NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    precautions TEXT NOT NULL DEFAULT '',
    contraindications TEXT NOT NULL DEFAULT '',
    is_official BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_exercise_therapist ON exercises_exercise (therapist_id);

COMMENT ON TABLE exercises_exercise IS '动作库表，官方动作与康复师个人动作';
COMMENT ON COLUMN exercises_exercise.therapist_id IS '创建者，官方动作为空';
COMMENT ON COLUMN exercises_exercise.name IS '动作名称';
COMMENT ON COLUMN exercises_exercise.body_part IS '训练部位';
COMMENT ON COLUMN exercises_exercise.description IS '动作说明';
COMMENT ON COLUMN exercises_exercise.precautions IS '注意事项';
COMMENT ON COLUMN exercises_exercise.contraindications IS '禁忌';
COMMENT ON COLUMN exercises_exercise.is_official IS '是否官方动作';

CREATE TABLE exercises_exercisealias (
    id BIGSERIAL PRIMARY KEY,
    exercise_id BIGINT NOT NULL REFERENCES exercises_exercise(id) ON DELETE CASCADE,
    alias VARCHAR(64) NOT NULL
);

COMMENT ON TABLE exercises_exercisealias IS '动作别名表，用于自然语言识别匹配';
