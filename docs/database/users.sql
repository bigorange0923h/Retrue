-- ============================================================
-- Retrue 数据库结构参考
-- 表：users（系统用户）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由自定义 User 模型（apps/accounts/models.py）生成。
-- ============================================================

CREATE TABLE tb_users (
    id BIGSERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMPTZ NULL,
    is_superuser BOOLEAN NOT NULL,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL,
    is_staff BOOLEAN NOT NULL,
    is_active BOOLEAN NOT NULL,
    date_joined TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE tb_users IS '系统用户表，V1 中一个用户对应一个康复师账号';
COMMENT ON COLUMN tb_users.username IS '登录用户名，唯一';
COMMENT ON COLUMN tb_users.is_active IS '账号是否启用，停用后无法登录';
