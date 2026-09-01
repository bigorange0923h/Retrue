-- Retrue TaskEvent 任务事件表（实际结构以 Django migration 为准）

CREATE TABLE tb_task_events (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    run_id BIGINT NULL,
    actor_id BIGINT NULL,
    event_type VARCHAR(64) NOT NULL,
    from_status VARCHAR(20) NOT NULL DEFAULT '',
    to_status VARCHAR(20) NOT NULL DEFAULT '',
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_taskevent_task_time ON tb_task_events (task_id, created_at);
CREATE INDEX idx_taskevent_task_type ON tb_task_events (task_id, event_type);

COMMENT ON TABLE tb_task_events IS '助手任务生命周期、状态转换和编排事件的不可变记录';
COMMENT ON COLUMN tb_task_events.task_id IS '所属助手任务 ID，不建立物理外键';
COMMENT ON COLUMN tb_task_events.run_id IS '可选关联执行 ID，不建立物理外键';
COMMENT ON COLUMN tb_task_events.actor_id IS '可选操作康复师用户 ID，不建立物理外键';
COMMENT ON COLUMN tb_task_events.event_type IS '事件类型，例如 task_created/status_changed/task_cancelled';
COMMENT ON COLUMN tb_task_events.from_status IS '状态变更前值';
COMMENT ON COLUMN tb_task_events.to_status IS '状态变更后值';
COMMENT ON COLUMN tb_task_events.event_data IS '事件结构化数据；不得写入完整敏感原文';

