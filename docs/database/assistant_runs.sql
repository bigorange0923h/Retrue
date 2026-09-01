-- Retrue AssistantRun 单次执行表（实际结构以 Django migration 为准）

CREATE TABLE tb_assistant_runs (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    client_request_id VARCHAR(128) NOT NULL DEFAULT '',
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    trigger_message_id BIGINT NULL,
    provider VARCHAR(64) NOT NULL DEFAULT '',
    model VARCHAR(128) NOT NULL DEFAULT '',
    input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code VARCHAR(64) NOT NULL DEFAULT '',
    error_message VARCHAR(500) NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'timed_out'))
);

CREATE INDEX idx_asrun_task_status ON tb_assistant_runs (task_id, status);
CREATE INDEX idx_asrun_task_attempt ON tb_assistant_runs (task_id, attempt);
CREATE UNIQUE INDEX uniq_asrun_client_request
    ON tb_assistant_runs (task_id, client_request_id)
    WHERE client_request_id <> '';

COMMENT ON TABLE tb_assistant_runs IS '助手任务的一次执行尝试；执行状态与任务总体状态分离';
COMMENT ON COLUMN tb_assistant_runs.task_id IS '所属助手任务 ID，不建立物理外键';
COMMENT ON COLUMN tb_assistant_runs.client_request_id IS '任务内本次执行的幂等键';
COMMENT ON COLUMN tb_assistant_runs.trigger_message_id IS '触发本次运行的会话消息 ID，不复制消息正文';
COMMENT ON COLUMN tb_assistant_runs.status IS '单次执行状态：queued/running/succeeded/failed/cancelled/timed_out';
COMMENT ON COLUMN tb_assistant_runs.input_summary IS '输入脱敏摘要；禁止保存完整客户健康信息或原文';
COMMENT ON COLUMN tb_assistant_runs.output_summary IS '输出脱敏摘要；禁止保存完整敏感结果原文';

