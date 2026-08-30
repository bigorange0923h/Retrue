-- ============================================================
-- Retrue 数据库结构参考
-- 表：tb_therapists（康复师）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 Therapist 模型（apps/tb_therapists/models.py）生成。
-- 康复师是客户数据归属主体，用于实现数据隔离。
-- ============================================================

CREATE TABLE tb_therapists (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    phone VARCHAR(20) NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_therapists IS '康复师表，与系统用户一对一关联';
COMMENT ON COLUMN tb_therapists.user_id IS '关联系统用户 ID，唯一';
COMMENT ON COLUMN tb_therapists.name IS '康复师姓名';
COMMENT ON COLUMN tb_therapists.is_active IS '是否在职';
COMMENT ON COLUMN tb_therapists.created_at IS '创建时间';
COMMENT ON COLUMN tb_therapists.updated_at IS '更新时间';
