# AssistantTask 统一助手任务接口

所有接口要求当前登录康复师（Session + Cookie）。任务按 `therapist` 隔离；客户、会话和上下文资源均由服务端校验归属。所有响应遵循统一信封：

```json
{ "code": 200, "message": "成功的消息", "data": null }
```

## 查询与创建任务

`GET /api/assistant/tasks/`

权限：已登录康复师。

可选查询参数：

- `customer`（兼容 `customer_id`）：按客户 ID 筛选。
- `status`：按任务状态筛选；支持逗号分隔多个值。
- `resumable=true|false`：筛选可恢复任务。可恢复状态为 `pending`、`running`、`waiting_user`、`waiting_confirmation`、`blocked`、`failed`。

成功响应的 `data` 为任务数组，最多返回 100 条。

`POST /api/assistant/tasks/`

权限：已登录康复师。

请求体示例：

```json
{
  "customer": 35,
  "conversation": 12,
  "skill_code": "training.note",
  "task_type": "training_record",
  "invocation_mode": "manual",
  "origin": "training_record",
  "context_resource_type": "course_session",
  "context_resource_id": "88",
  "business_key": "training:88",
  "client_request_id": "mobile-request-20260901-001",
  "current_step": "collect_input",
  "missing_fields": ["customer_feedback"],
  "state_data": {"input_mode": "voice"}
}
```

`skill_code`、`task_type`、`invocation_mode` 和 `origin` 由调用方定义；任务服务不内置或持久化提示词。`client_request_id` 在当前康复师范围内幂等，也可通过 `Idempotency-Key` 请求头传入；若同一键用于不同客户、会话或资源上下文，返回 `409`，不会静默切换任务。相同 `business_key` 在同一客户范围内存在未完成任务时复用已有任务，但业务类型和来源资源必须一致。服务端不接受客户端直接指定任务终态、版本、过期、完成或取消时间；过期回收由后续后台调度接入。

上下文资源类型白名单：`customer`、`course_session`、`assessment`、`training_record`。资源必须属于当前康复师；若任务同时指定客户，资源客户必须一致。

## 获取任务详情与保存恢复数据

`GET /api/assistant/tasks/{id}/`

权限：仅任务所属康复师。返回任务、执行摘要、工具调用摘要和事件记录。

`PATCH /api/assistant/tasks/{id}/`

权限：仅任务所属康复师。

请求体必须携带当前 `version`，并且只允许 `current_step`、`missing_fields`、`state_data`、`customer`、`conversation`：

```json
{
  "version": 3,
  "current_step": "review",
  "missing_fields": [],
  "state_data": {"draft_id": 19}
}
```

更新成功后版本递增。版本不一致返回 `409`（`error_code=task_version_conflict`）；任务状态、结果资源和生命周期时间必须通过后端服务状态机更新，不能由客户端 PATCH 伪造。

## 聊天前按姓名确认客户

`GET /api/assistant/customers/by-name/?name={客户姓名}`

权限：已登录康复师。此接口是聊天上下文使用的只读客户匹配 Tool：仅在当前康复师名下按**精确姓名**查询，响应 `data` 始终是列表。每项只返回 ID、姓名、脱敏手机号、性别、状态、主要问题和首次到店日期，不返回完整手机号。

当结果为多条同名客户时，聊天页会显示候选选项栏，康复师必须选择具体档案；选择后会新建该客户的普通会话，避免混入上一位客户的对话上下文。

## 取消任务

`POST /api/assistant/tasks/{id}/cancel/`

权限：仅任务所属康复师。

请求体可选：

```json
{ "reason": "客户暂缓本次操作" }
```

任务取消后写入 `task_cancelled` 事件并设置 `cancelled_at`。重复取消已取消任务幂等返回成功；已完成或已过期任务不能取消。

## 状态和错误

任务状态：`pending`、`running`、`waiting_user`、`waiting_confirmation`、`blocked`、`completed`、`failed`、`cancelled`、`expired`。一次 `AssistantRun` 使用独立的 `queued`、`running`、`succeeded`、`failed`、`cancelled`、`timed_out` 状态，不能混用。

常见错误：`400` 参数/资源客户不一致；`401` 未登录；`403` 资源或任务不属于当前康复师；`404` 任务或资源不存在；`409` 恢复数据版本冲突；`500` 服务器内部错误。

`state_data`、执行输入/输出和工具输入/输出仅保存必要的脱敏摘要，不保存完整客户健康信息、原始消息、密钥或提示词。正式业务写入必须经过独立确认流程。

## 受控只读 Tool

统一助手在查询客户信息时只允许使用服务端注册的以下五个只读 Tool：

| 工具名 | 用途 | 主要参数 |
| --- | --- | --- |
| `search_customers` | 搜索当前康复师名下客户，返回脱敏手机号 | `keyword`/`query`、`status`、`limit` |
| `get_customer_context` | 查询客户资料、首次评估状态、当前计划摘要 | `customer_id`（可省略，使用任务客户） |
| `list_customer_course_sessions` | 查询客户课程排期和单节状态 | `customer_id`、`course_session_id`、日期范围、`limit` |
| `list_recent_training_records` | 查询近期训练记录（文本结果有限长） | `customer_id`、`days`/日期范围、`training_record_id`、`limit` |
| `get_initial_assessment_status` | 查询首次评估是否存在、状态和指标数 | `customer_id`（可省略，使用任务客户） |

工具名必须精确匹配服务端 `ToolDefinition` 注册表，未知名称、Python 函数路径
或写入工具均会被拒绝。康复师身份始终从 URL 对应的 `AssistantTask.therapist`
派生，客户端不能通过参数指定 `therapist_id`。

### 执行工具

`POST /api/assistant/tasks/{id}/tools/`

权限：仅任务所属的当前登录康复师；该接口只执行上述只读 Tool。

请求体：

```json
{
  "tool_name": "list_recent_training_records",
  "arguments": {
    "customer_id": 35,
    "days": 30,
    "limit": 10
  },
  "client_request_id": "tool-request-20260901-001"
}
```

也兼容将 `tool_name` 写作 `tool`，但二者不能同时指定不同工具。`limit` 最大
为 50；`days` 和日期范围最大为 366 天；日期必须为 `YYYY-MM-DD`，且起始日
不能晚于结束日。工具参数只接受对应 `ToolDefinition.input_schema` 声明的字段，
不接受任意附加参数。

任务已有客户时，工具参数中的 `customer_id` 必须与任务客户一致；任务绑定的
课程、评估或训练资源也会在每次执行时复核康复师和客户归属。跨康复师资源、
跨客户资源和不完整资源引用均拒绝，不会降级为按参数直接查询。

每次执行都会创建或更新一条 `AssistantRun` 与一条 `ToolExecution`，并返回
`run_id`、`tool_execution_id`、业务 `result` 和脱敏日志摘要。摘要只记录工具名、
参数键、数量、资源 ID 和日期等必要信息；不会保存完整手机号、病史、关键词、
客户原话或整段训练文本。工具返回的训练文本也会限制长度。执行失败同样会留
下失败状态和错误代码，便于恢复与审计；任何正式业务写入仍须经过独立的康复师
确认流程。
