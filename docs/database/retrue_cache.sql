-- ============================================================
-- Retrue 数据库结构参考
-- 表：retrue_cache（Django DatabaseCache 缓存表）
-- 说明：登录限流与多进程共享计数使用 PostgreSQL 缓存后端。
--       本表不属于业务模型，由 accounts migration 0003 创建；
--       SQL 文件仅为结构参考，实际建表以迁移为准。
-- ============================================================

CREATE TABLE IF NOT EXISTS retrue_cache (
    cache_key varchar(255) NOT NULL PRIMARY KEY,
    value text NOT NULL,
    expires timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS retrue_cache_expires ON retrue_cache (expires);

COMMENT ON TABLE retrue_cache IS 'Django 数据库缓存表（登录限流等）';
COMMENT ON COLUMN retrue_cache.cache_key IS '缓存键';
COMMENT ON COLUMN retrue_cache.value IS '缓存值（base64 编码）';
COMMENT ON COLUMN retrue_cache.expires IS '过期时间';
