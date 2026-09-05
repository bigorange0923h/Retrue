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

## 统一回合编排接口

统一回合接口把一次用户输入送入受控的 LangGraph 编排图，由后端决定意图与分支；
前端不再自行组合 Tool。这些接口由 `AI_ORCHESTRATION_ENABLED` 功能开关控制，
默认关闭，关闭时返回 `503`（`error_code=orchestration_disabled`）。

### 发起一轮对话

`POST /api/assistant/turns/`

权限：已登录康复师。

请求体：

```json
{
  "message": "今天做了臀桥 3 组 12 次",
  "conversation_id": 39,
  "customer_id": 35,
  "customer_name": "张三",
  "client_request_id": "turn-request-20260901-001"
}
```

- `message`：本轮用户输入（仅用于编排，不写入任务状态）。
- `conversation_id`：可选会话；提供时先保存用户消息再运行图。
- `customer_id`：可选已绑定客户。
- `customer_name`：可选客户姓名提示，用于未绑定客户时的姓名检索。
- `client_request_id`：可选幂等键，兼容 `Idempotency-Key` 请求头。

成功响应 `data` 包含 `task_id`、`status`、`current_step`、`customer_id`、
`intent`、`missing_fields`、`resource_refs`、`customer_candidates`、
`needs_confirmation`、`reply_content`、`assistant_message_id`、`risk_notice`
和 `cards`。`cards` 是前端可渲染的结构化业务卡片数组，每张卡片包含
`id`、`type`、`status`、`resource_refs`、`allowed_actions` 等字段，前端据此渲染
可交互卡片，不展示内部节点名。语义如下：

- 通用咨询或客户事实问答：`reply_content` 为可直接展示的回复文本，同时已写入
  会话（`assistant_message_id` 为其消息主键）；回复区分“系统记录”与“建议”。
- 同名客户选择：`cards` 含 `type=customer_selection` 的卡片（`status=waiting_user`），
  `customer_candidates` 返回候选列表（脱敏），前端展示选择卡片，绝不自动猜测。
- 客户信息摘要：`cards` 含 `type=customer_summary` 的卡片，`summary` 为脱敏摘要
  （近期训练次数、首次评估状态、当前计划等），不默认展示完整病史或手机号。
- 训练补记草稿确认：`cards` 含 `type=training_draft` 的卡片
  （`status=waiting_confirmation`），`resource_refs` 含 `draft_id`，正式写入仍需
  康复师确认。
- 评估 / 随访 / 训练修订草稿：`cards` 分别含 `type=assessment_draft` /
  `domain_draft` 的卡片，同样等待康复师确认后才写入。
- 风险核查：`cards` 含 `type=risk_review` 的卡片（`status=blocked`），`risk_notice`
  为人工核查提醒，不生成正式记录。

### 恢复未完成任务

`POST /api/assistant/tasks/{id}/resume/`

权限：仅任务所属康复师。只接收允许继续的信息（可选 `message`），不接受客户端
伪造节点或任务状态。恢复严格从 `state_data.next_node` 表示的暂停节点继续，不
重新进行意图识别、不重新猜测客户姓名、不重复生成草稿：草稿待确认时只重新返回
已有 `draft_id`。

### 提交同名客户选择

`POST /api/assistant/tasks/{id}/customer-selection/`

权限：仅任务所属康复师。

请求体：

```json
{ "customer_id": 35 }
```

服务端重新校验客户归属后，按原意图从中断节点继续：客户历史问题进入只读 Tool
查询并回答，训练补记进入草稿生成。客户不属于当前康复师时返回 `403`。

## 对话实时进度（SSE 试用版）

`POST /api/assistant/turns/stream/`

请求体与原 `POST /api/assistant/turns/` 相同。前端使用 `fetch` 单次 POST，
`Accept: text/event-stream, application/json`，携带同源 Session Cookie 和
`X-CSRFToken`。不使用原生 EventSource 发起此 POST。原 JSON 接口继续可用；
流失败后不得自动降级重发。

未登录、CSRF 失败、输入错误、会话/客户越权、功能关闭和并发容量不足，在开流前
返回统一 JSON 错误。开流后响应为 `text/event-stream; charset=utf-8`，每个业务
事件的 `data` 都使用 `{code, message, data}` 信封。

```text
id: 1
event: progress
data: {"code":200,"message":"操作成功","data":{"stage":"understand","label":"正在识别需求","status":"running"}}

id: 2
event: progress
data: {"code":200,"message":"操作成功","data":{"stage":"understand","label":"正在识别需求","status":"completed"}}

```

| 事件 | data 内容 | 前端行为 |
| --- | --- | --- |
| `progress` | 固定的 `stage`、`label`、`status`（running/completed/failed） | 更新最近五个执行阶段 |
| `result` | 与原接口相同的 `AssistantTurnResult` | 结束 loading，展示回复与业务卡片 |
| `error` | 安全错误信封，code 非 200 | 结束 loading，提示错误 |

进度从 LangGraph `tasks` 开始/结束事件映射，只有固定业务文案可出站；不得发送
节点输入输出、工具参数、客户 ID、模型原文或推理内容。相同阶段可多次出现，例如
多轮资料查询；已完成只表示该执行阶段结束，不表示草稿已经人工确认或正式保存。
最终结果继续经过原有权限、输出过滤和持久化流程。

无事件时每 10 秒发送 `: heartbeat` 注释，心跳不推进步骤；最长等待 180 秒后发
`error`（504）。浏览器 30 秒无字节或总计 190 秒会断开；离开页面也会关闭接收。
断线、超时不等于业务取消，已开始的同步调用可能继续，用户应查看当前会话/任务后
再操作。此版没有自动重连、事件重放或后台任务持久执行保证，事件 id 只用于本流
顺序标记。每进程最多 4 次并发执行，过载返回 503；断线后的执行结束前仍占用名额。

当前只接入发送新消息；同名客户选择、任务恢复及草稿确认仍走原有 JSON 接口。
开发 `runserver` 使用同步迭代器；ASGI 使用异步迭代器，避免响应被整段缓冲。
正式部署需使用 ASGI 服务，并确保代理关闭此路径的 buffering/cache，读取超时
大于 190 秒。响应提供 `Cache-Control: no-cache, no-store, no-transform` 和
`X-Accel-Buffering: no`；是否被代理/CDN 采纳仍需部署现场验证。此次不新增依赖、
数据库表或迁移。

验证命令：后端 `manage.py test apps.assistant_tasks.test_streaming --keepdb`；
前端 `node --test tests/sse.test.mjs` 与 `npm run build`。

## 多客户批量训练补记接口

多客户批量补记使用父级 `AssistantTask`（`task_type=multi_customer_training_record`，
`customer=null`）加有序子项 `TrainingRecordBatchItem`。子项按 `sequence` 严格顺序
推进；客户、草稿、正式记录归属均由服务校验，正式保存幂等。

### 批次概览

`GET /api/assistant/tasks/{task_id}/batch/`

返回父任务与全部子项状态，含当前未完成子项 `current_item_id`，供前端恢复与概览。

### 子项客户搜索

`POST /api/assistant/tasks/{task_id}/items/{item_id}/customer-search/`

按子项 `customer_name_hint` 查询当前康复师名下客户，返回 `candidates`。只查询当前
康复师客户，不接受客户端 `therapist_id`。

### 子项客户确认

`POST /api/assistant/tasks/{task_id}/items/{item_id}/customer-selection/`

请求体 `{ "customer_id": 35 }`。确认后生成该子项的 `AiDraft`（pending）并进入等待
草稿确认；再次校验客户归属，且要求更早的子项已进入终态。

### 子项草稿保存

`PATCH /api/assistant/tasks/{task_id}/items/{item_id}/draft/`

请求体为草稿字段（训练日期、项目列表、客户感受、康复师观察、下次计划）。自动保存
草稿不写入正式记录。

### 子项正式确认

`POST /api/assistant/tasks/{task_id}/items/{item_id}/confirm/`

请求体 `{ "confirmed": {...}, "idempotency_key": "..." }`。调用既有训练记录领域服务
创建正式训练记录，标记子项 `completed`，并推进到下一子项；无下一子项时父任务
`completed`，返回 `summary` 汇总。重复确认（相同幂等键）不创建第二条记录。

### 子项跳过

`POST /api/assistant/tasks/{task_id}/items/{item_id}/skip/`

跳过当前子项并推进到下一子项；已保存的记录不受影响。
