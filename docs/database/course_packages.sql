-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_course_packages（课时包）与 tb_course_adjustments（课时调整）
-- 说明：实际变更以 Django migration 为准。
-- 课时消耗需在课程完成且训练记录确认后触发；人工调整必须记录原因。
-- ============================================================

CREATE TABLE tb_course_packages (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES tb_customers(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL DEFAULT '默认课时包',
    total_sessions NUMERIC(8,1) NOT NULL DEFAULT 0,
    used_sessions NUMERIC(8,1) NOT NULL DEFAULT 0,
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_coursepkg_therapist ON tb_course_packages (therapist_id, customer_id);

COMMENT ON TABLE tb_course_packages IS '课时包表，记录客户课时总数与已消耗';
COMMENT ON COLUMN tb_course_packages.total_sessions IS '总课时数，支持半课 0.5';
COMMENT ON COLUMN tb_course_packages.used_sessions IS '已消耗课时数（剩余=总-已消耗）';

CREATE TABLE tb_course_adjustments (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL REFERENCES tb_users(id) ON DELETE CASCADE,
    package_id BIGINT NOT NULL REFERENCES tb_course_packages(id) ON DELETE CASCADE,
    delta NUMERIC(6,1) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_course_adjustments IS '课时人工调整表，记录调整量与原因';
COMMENT ON COLUMN tb_course_adjustments.delta IS '调整量，正为扣减、负为退还，支持半课 0.5';
COMMENT ON COLUMN tb_course_adjustments.reason IS '调整原因，必填';
