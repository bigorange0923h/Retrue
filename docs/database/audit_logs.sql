-- ============================================================
-- Retrue 数据库结构参考
-- 表：audit_logs（审计日志）
-- 说明：该文件仅用于审阅与交接，实际变更以 Django migration 为准。
-- 由 AuditLog 模型（apps/audit/models.py）生成。
-- 记录正式业务数据的变更历史，保留前后快照与修改原因。
-- ============================================================

CREATE TABLE audit_auditlog (
    id BIGSERIAL PRIMARY KEY,
    actor_id BIGINT NULL REFERENCES accounts_user(id) ON DELETE SET NULL,
    action VARCHAR(20) NOT NULL,
    content_type_id INT NULL REFERENCES django_content_type(id) ON DELETE CASCADE,
    object_id VARCHAR(64) NULL,
    before_data JSONB NOT NULL DEFAULT '{}',
    after_data JSONB NOT NULL DEFAULT '{}',
    reason VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_audit_content ON audit_auditlog (content_type_id, object_id);
CREATE INDEX idx_audit_created ON audit_auditlog (created_at);

COMMENT ON TABLE audit_auditlog IS '审计日志表，记录业务对象变更历史';
COMMENT ON COLUMN audit_auditlog.actor_id IS '操作人，空表示系统操作';
COMMENT ON COLUMN audit_auditlog.action IS '动作类型：create/update/delete/confirm/login/logout';
COMMENT ON COLUMN audit_auditlog.object_id IS '被操作业务对象 ID';
COMMENT ON COLUMN audit_auditlog.before_data IS '操作前数据快照（JSON）';
COMMENT ON COLUMN audit_auditlog.after_data IS '操作后数据快照（JSON）';
COMMENT ON COLUMN audit_auditlog.reason IS '修改原因，修改正式记录时必填';
COMMENT ON COLUMN audit_auditlog.created_at IS '记录时间';
