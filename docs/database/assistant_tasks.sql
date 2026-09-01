-- Retrue AssistantTask 统一任务表（实际结构以 Django migration 为准）

CREATE TABLE tb_assistant_tasks (
    id BIGSERIAL PRIMARY KEY,
    therapist_id BIGINT NOT NULL,
    customer_id BIGINT NULL,
    conversation_id BIGINT NULL,
    skill_code VARCHAR(100) NOT NULL DEFAULT '',
    task_type VARCHAR(64) NOT NULL DEFAULT '',
    invocation_mode VARCHAR(32) NOT NULL DEFAULT 'manual',
    origin VARCHAR(64) NOT NULL DEFAULT '',
    context_resource_type VARCHAR(32) NOT NULL DEFAULT '',
    context_resource_id VARCHAR(100) NOT NULL DEFAULT '',
    business_key VARCHAR(255) NOT NULL DEFAULT '',
    client_request_id VARCHAR(128) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    current_step VARCHAR(128) NOT NULL DEFAULT '',
    missing_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    state_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    draft_resource_type VARCHAR(64) NOT NULL DEFAULT '',
    draft_resource_id VARCHAR(100) NOT NULL DEFAULT '',
    result_resource_type VARCHAR(64) NOT NULL DEFAULT '',
    result_resource_id VARCHAR(100) NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    last_activity_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    cancelled_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (status IN (
        'pending', 'running', 'waiting_user', 'waiting_confirmation',
        'blocked', 'completed', 'failed', 'cancelled', 'expired'
    ))
);

CREATE INDEX idx_astask_scope_status
    ON tb_assistant_tasks (therapist_id, status, updated_at);
CREATE INDEX idx_astask_customer_status
    ON tb_assistant_tasks (therapist_id, customer_id, status);
CREATE INDEX idx_astask_business_key
    ON tb_assistant_tasks (therapist_id, business_key);
CREATE INDEX idx_astask_client_request
    ON tb_assistant_tasks (therapist_id, client_request_id);

CREATE UNIQUE INDEX uniq_astask_client_request
    ON tb_assistant_tasks (therapist_id, client_request_id)
    WHERE client_request_id <> '';
CREATE UNIQUE INDEX uniq_astask_active_biz_customer
    ON tb_assistant_tasks (therapist_id, customer_id, business_key)
    WHERE business_key <> ''
      AND customer_id IS NOT NULL
      AND status IN ('pending', 'running', 'waiting_user', 'waiting_confirmation', 'blocked', 'failed');
CREATE UNIQUE INDEX uniq_astask_active_biz_general
    ON tb_assistant_tasks (therapist_id, business_key)
    WHERE business_key <> ''
      AND customer_id IS NULL
      AND status IN ('pending', 'running', 'waiting_user', 'waiting_confirmation', 'blocked', 'failed');

COMMENT ON TABLE tb_assistant_tasks IS '统一助手任务上下文、可恢复状态和草稿/结果资源引用；不保存提示词';
COMMENT ON COLUMN tb_assistant_tasks.therapist_id IS '康复师用户 ID，数据隔离依据；不建立物理外键';
COMMENT ON COLUMN tb_assistant_tasks.customer_id IS '可选客户 ID；由服务层校验归属';
COMMENT ON COLUMN tb_assistant_tasks.conversation_id IS '可选 AI 会话 ID；由服务层校验归属';
COMMENT ON COLUMN tb_assistant_tasks.skill_code IS '调用方定义的技能代码，不承载提示词';
COMMENT ON COLUMN tb_assistant_tasks.task_type IS '业务任务类型，例如 training_record';
COMMENT ON COLUMN tb_assistant_tasks.invocation_mode IS '调用模式，例如 manual/automatic/resume';
COMMENT ON COLUMN tb_assistant_tasks.context_resource_type IS '白名单资源类型：customer/course_session/assessment/training_record';
COMMENT ON COLUMN tb_assistant_tasks.context_resource_id IS '上下文资源标识，不建立物理外键';
COMMENT ON COLUMN tb_assistant_tasks.business_key IS '康复师和客户范围内未完成任务复用键';
COMMENT ON COLUMN tb_assistant_tasks.client_request_id IS '康复师范围内客户端幂等键';
COMMENT ON COLUMN tb_assistant_tasks.status IS '任务状态：pending/running/waiting_user/waiting_confirmation/blocked/completed/failed/cancelled/expired';
COMMENT ON COLUMN tb_assistant_tasks.missing_fields IS '继续任务前需要补充的字段名数组';
COMMENT ON COLUMN tb_assistant_tasks.state_data IS '任务恢复所需结构化状态，不保存完整敏感原文';
COMMENT ON COLUMN tb_assistant_tasks.draft_resource_id IS 'AI 草稿资源标识，不建立物理外键';
COMMENT ON COLUMN tb_assistant_tasks.result_resource_id IS '人工确认后的正式结果资源标识，不建立物理外键';
COMMENT ON COLUMN tb_assistant_tasks.version IS '恢复数据乐观锁版本，每次服务层变更递增';
COMMENT ON COLUMN tb_assistant_tasks.last_activity_at IS '最近一次任务活动时间';

