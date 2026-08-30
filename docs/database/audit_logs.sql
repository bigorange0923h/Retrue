-- ============================================================
-- Retrue 数据库结构参考
-- 表：audit_logs（审计日志）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 AuditLog 模型（apps/audit/models.py）生成。
-- 记录正式业务数据的变更历史，保留前后快照与修改原因。
-- ============================================================

CREATE TABLE tb_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT NULL,
    action VARCHAR(20) NOT NULL,
    content_type_id INT NULL,
    object_id VARCHAR(64) NULL,
    before_data JSONB NOT NULL DEFAULT '{}',
    after_data JSONB NOT NULL DEFAULT '{}',
    reason VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_audit_content ON tb_audit_logs (content_type_id, object_id);
CREATE INDEX idx_audit_created ON tb_audit_logs (created_at);

COMMENT ON TABLE tb_audit_logs IS '审计日志表，记录业务对象变更历史';
COMMENT ON COLUMN tb_audit_logs.actor_id IS '操作人，空表示系统操作';
COMMENT ON COLUMN tb_audit_logs.action IS '动作类型：create/update/delete/confirm/login/logout';
COMMENT ON COLUMN tb_audit_logs.object_id IS '被操作业务对象 ID';
COMMENT ON COLUMN tb_audit_logs.before_data IS '操作前数据快照（JSON）';
COMMENT ON COLUMN tb_audit_logs.after_data IS '操作后数据快照（JSON）';
COMMENT ON COLUMN tb_audit_logs.reason IS '修改原因，修改正式记录时必填';
COMMENT ON COLUMN tb_audit_logs.created_at IS '记录时间';
