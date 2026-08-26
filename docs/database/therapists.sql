-- ============================================================
-- Retrue 数据库结构参考
-- 表：therapists（康复师）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 Therapist 模型（apps/therapists/models.py）生成。
-- 康复师是客户数据归属主体，用于实现数据隔离。
-- ============================================================

CREATE TABLE therapists_therapist (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES accounts_user(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    phone VARCHAR(20) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE therapists_therapist IS '康复师表，与系统用户一对一关联';
COMMENT ON COLUMN therapists_therapist.user_id IS '关联系统用户 ID，唯一';
COMMENT ON COLUMN therapists_therapist.name IS '康复师姓名';
COMMENT ON COLUMN therapists_therapist.is_active IS '是否在职';
COMMENT ON COLUMN therapists_therapist.created_at IS '创建时间';
COMMENT ON COLUMN therapists_therapist.updated_at IS '更新时间';
