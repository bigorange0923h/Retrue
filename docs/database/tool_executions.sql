-- Retrue ToolExecution 工具调用表（实际结构以 Django migration 为准）

CREATE TABLE tb_tool_executions (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL,
    task_id BIGINT NULL,
    sequence INTEGER NOT NULL DEFAULT 0 CHECK (sequence >= 0),
    tool_name VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    input_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_write BOOLEAN NOT NULL DEFAULT FALSE,
    requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_by BIGINT NULL,
    confirmed_at TIMESTAMPTZ NULL,
    result_resource_type VARCHAR(64) NOT NULL DEFAULT '',
    result_resource_id VARCHAR(100) NOT NULL DEFAULT '',
    error_code VARCHAR(64) NOT NULL DEFAULT '',
    error_message VARCHAR(500) NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled'))
);

CREATE INDEX idx_toolexec_run_status ON tb_tool_executions (run_id, status);
CREATE INDEX idx_toolexec_task_status ON tb_tool_executions (task_id, status);

COMMENT ON TABLE tb_tool_executions IS '一次助手执行中的工具调用、写操作确认和资源结果引用';
COMMENT ON COLUMN tb_tool_executions.run_id IS '所属助手执行 ID，不建立物理外键';
COMMENT ON COLUMN tb_tool_executions.task_id IS '直接追溯所属助手任务 ID，可由 run 反查；不建立物理外键';
COMMENT ON COLUMN tb_tool_executions.tool_name IS '工具标识，不保存工具实现密钥';
COMMENT ON COLUMN tb_tool_executions.status IS '工具调用状态：pending/running/succeeded/failed/cancelled';
COMMENT ON COLUMN tb_tool_executions.input_summary IS '工具输入脱敏摘要，禁止保存完整敏感参数';
COMMENT ON COLUMN tb_tool_executions.output_summary IS '工具输出脱敏摘要，禁止保存完整敏感结果';
COMMENT ON COLUMN tb_tool_executions.is_write IS '是否会写入正式业务数据';
COMMENT ON COLUMN tb_tool_executions.requires_confirmation IS '写操作是否必须先经康复师确认';
COMMENT ON COLUMN tb_tool_executions.confirmed_by IS '执行确认的康复师用户 ID，不建立物理外键';
COMMENT ON COLUMN tb_tool_executions.result_resource_id IS '工具产生的业务资源标识，不建立物理外键';

