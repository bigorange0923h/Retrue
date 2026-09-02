# LangGraph 多分支 AI 助理编排执行计划

> 状态：待实施  
> 适用范围：统一 AI 助理的意图识别、只读 Tool 路由、客户歧义处理、人工确认与可恢复多步骤流程  
> 前置条件：现有 `AssistantTask`、`AssistantRun`、`ToolExecution`、`TaskEvent` 和训练补记草稿闭环已可用。  
> 核心原则：LangGraph 只编排流程；权限、任务状态、正式业务写入和审计仍由 Django 领域服务负责。

## 1. 建设目标

把“根据一句话判断要做什么、查哪些真实数据、何时需要康复师选择或确认”的多分支流程收敛到一个可审计、可恢复的图，而不是继续在前端或单个 view 中堆叠条件判断。

首批范围只覆盖日常咨询与训练补记：

```text
用户消息
  → 意图与风险初筛
  ├─ 通用知识咨询 → 直接回答
  ├─ 客户姓名未明确 → 查询同名候选 → 等康复师选择
  ├─ 已确定客户的历史问题 → 调用只读 Tool → 带事实回答
  ├─ 训练补记 → 生成草稿 → 等康复师检查/确认
  └─ 涉及正式写入 → 永远停在人工确认节点
```

评估、随访、课程调整和记录修订在首批流程稳定后逐项接入；不得因为接入 LangGraph 而改变“AI 不直接写正式数据”的边界。

## 2. 架构边界

```text
Vue Assistant 页面
      │ 发送消息 / 选择客户 / 确认草稿
      ▼
Django Assistant Orchestrator
      │ 创建或恢复 AssistantTask / AssistantRun
      ▼
LangGraph（意图、分支、Tool 调用顺序、等待节点）
      │
      ├─ 现有只读 Tool 注册表
      ├─ AI Provider（结构化输出）
      └─ Django 领域 service（仅通过确认节点调用写入）
      ▼
AssistantTask / Run / ToolExecution / TaskEvent
Conversation / AiDraft / TrainingRecord 等领域表
```

- LangGraph 不直接访问 ORM 写正式业务表，也不接收客户端提供的 `therapist_id`。
- `AssistantTask` 是业务恢复的权威来源；图的节点名称、已选客户、缺失字段和资源 ID 必须回写任务事件与结构化状态。
- Conversation 保存原始对话；Graph checkpoint 不保存完整消息、病史、手机号、提示词或 Tool 原始输出。
- Tool 仍通过现有白名单、参数 schema、康复师/客户归属校验和脱敏日志执行。
- 任何正式训练、评估、随访或课程变更仍由康复师点击确认后调用领域 service。

## 3. 首期图与分支

```text
receive_turn
  → classify_intent
  ├─ general_knowledge ─────────────→ answer_general → end
  ├─ customer_lookup
  │    ├─ no_match ────────────────→ wait_customer_name
  │    ├─ one_match ───────────────→ bind_customer
  │    └─ multiple_matches ────────→ wait_customer_selection
  ├─ customer_question ────────────→ choose_read_tools
  │                                    → execute_read_tools
  │                                    → answer_with_context → end
  └─ training_record ──────────────→ ensure_customer
                                       ├─ unresolved → wait_customer_selection
                                       └─ resolved → create_training_draft
                                                       → wait_draft_confirmation
                                                           ├─ confirm → domain_confirm → end
                                                           ├─ edit/retry → create_training_draft
                                                           └─ cancel → end
```

### 用户可见等待点

| 图节点 | 任务状态 | 页面表现 | 恢复输入 |
| --- | --- | --- | --- |
| `wait_customer_name` | `waiting_user` | 提示补充客户姓名 | 新姓名文本 |
| `wait_customer_selection` | `waiting_user` | 同名客户候选栏 | 客户 ID |
| `wait_draft_confirmation` | `waiting_confirmation` | 可编辑训练草稿 | 确认、重新解析或取消 |
| `blocked` | `blocked` | 清晰说明数据变化和可选处理 | 康复师明确操作 |

“等待”不是异常：页面关闭后可从未完成任务恢复到相同节点，绝不让模型重新猜测进度。

## 4. 意图与 Tool 路由规则

采用“确定性规则优先 + 结构化模型分类补充 + 服务端最终校验”的三层方式：

| 信号 | 路由结果 | Tool / 动作 |
| --- | --- | --- |
| 明确补记、训练量、观察、下次计划 | `training_record` | 进入草稿流程 |
| 客户姓名且未绑定客户 | `customer_lookup` | 按姓名查当前康复师客户 |
| 已绑定客户 + 最近/历史/进展/上次 | `customer_question` | 近期训练、评估状态、课程等只读 Tool |
| 动作做法、通用训练知识 | `general_knowledge` | 不读客户数据，直接回答 |
| 提到风险或禁忌 | `risk_review` | 读取必要上下文，提示康复师核查；不自动诊断 |

模型分类输出必须是受 schema 约束的 JSON，例如 `intent`、`customer_name`、`required_tools`、`needs_confirmation` 和 `confidence`。低置信度时不自动执行 Tool，而是追问或提供选项。

## 5. Graph State 与恢复

Graph State 仅保存：

```json
{
  "assistant_task_id": 12,
  "conversation_id": 39,
  "customer_id": 35,
  "intent": "customer_question",
  "next_node": "wait_customer_selection",
  "missing_fields": ["customer_id"],
  "resource_refs": {"draft_id": null},
  "tool_result_refs": ["tool_execution:81"]
}
```

不得把原始对话正文、完整健康信息、手机号、模型提示词或 Tool 原始结果写入 Graph checkpoint。原文仍分别保存在 Conversation、AiDraft 和领域表；Graph 只保存其引用。

实现时新增一个适配器，把每次节点转换同步到：

1. `AssistantTask.current_step`、`missing_fields`、安全的 `state_data`；
2. `TaskEvent`（含节点、分支原因、Run ID、脱敏摘要）；
3. `AssistantRun`、`ToolExecution` 的状态与脱敏结果。

首期不直接启用 LangGraph 默认的全量消息持久化 checkpointer。若后续需要 LangGraph 持久化，必须实现仅存上述安全状态的 `TaskStateCheckpointer`，或将存储字段单独设计、脱敏并纳入迁移与 SQL 文档。

## 6. Tool 与写入约束

- 一轮最多调用 3 个只读 Tool，总参数和返回摘要受现有上限约束。
- 同一个 Tool 参数组合在同一 Run 内去重；失败最多重试 1 次。
- 客户不明确时，只允许客户匹配 Tool；不得先查询其他客户的训练、评估或课程。
- `create_training_draft` 是草稿动作，可由图调用，但仍生成 `AiDraft(pending)`。
- `confirm_training_record` 只能由康复师点击确认的 API 触发，不能作为模型自动分支。
- Tool 失败时图转为 `blocked` 或给出降级回答；不得伪造不存在的客户历史。

## 7. 接口与前端调整

新增统一回合接口，而不是让前端自行组合 Tool：

```text
POST /api/assistant/turns/
POST /api/assistant/tasks/{id}/resume/
POST /api/assistant/tasks/{id}/customer-selection/
```

- `turns` 接收当前会话、可选客户和用户消息；先保存 Conversation 消息，再运行图。
- `resume` 只接收允许继续的信息，不接受客户端伪造节点或任务状态。
- `customer-selection` 接收候选客户 ID，重新校验归属后从中断节点继续。
- 前端只展示“请选择客户”“正在查询”“待你确认”等业务语言；不展示 Graph、节点名或 Tool 名。
- 同名客户候选栏继续放在输入框上方；选择后以新的客户上下文创建或恢复会话。

## 8. 分期实施

### 阶段 1：编排基座（已完成）

- 引入 LangGraph 及固定版本依赖。
- 建立 `apps/ai/orchestration/`，只放图、节点 schema、路由器和适配器；提示词继续使用独立文件。
- 实现安全 Graph State、TaskEvent/Run 同步适配器和节点次数限制。
- 不迁移现有训练补记确认逻辑。

验收：可运行空图和恢复图；不会把原始对话写进任务状态或 checkpoint。

已落地内容：
- `requirements.txt` 固定 `langgraph>=1.2.0,<1.3`、`langchain-core>=1.6.0,<1.7`。
- `config/settings.py` 新增 `AI_ORCHESTRATION_ENABLED`（默认关闭）、`AI_ORCHESTRATION_MAX_STEPS`、`AI_ORCHESTRATION_MAX_TOOL_CALLS` 功能开关与上限。
- `apps/ai/orchestration/`：`state.py`（安全 Graph State + 白名单序列化）、`graph.py`（空图/恢复图）、`limits.py`（节点与 Tool 次数限制）、`adapter.py`（TaskEvent/Run 同步适配器）。
- 测试 `apps/ai/test_orchestration.py`：空图可运行、恢复图可运行、状态序列化不写敏感数据、节点/Tool 次数上限、开关默认关闭。

### 阶段 2：客户歧义与只读问答（已完成）

- 接入客户名称匹配、同名选择中断、客户上下文、近期训练、课程、首次评估 Tool。
- 实现 `general_knowledge` 与 `customer_question` 分支。
- 对低置信度、Tool 失败、无结果和跨客户请求编写测试。

验收：同名客户必须由康复师选择；所有客户数据查询有 ToolExecution 审计。

已落地：`intent.py`（确定性意图分类）、`nodes.py`（classify_intent/customer_lookup/choose_read_tools/execute_read_tools/answer_general/answer_with_context 等节点）、图分支与只读 Tool 路由。

### 阶段 3：训练补记图迁移（已完成）

- 将现有训练补记的意图入口和草稿生成接入 Graph。
- 保留现有 `AiDraft`、确认 API、事务锁和幂等键作为最终写入边界。
- 支持重新解析、取消、超时和页面关闭恢复。

验收：新图与现有补记产生相同正式业务结果；重复提交、重开页面和同一课程并发均不重复写入。

已落地：`ensure_customer`/`create_training_draft`/`wait_draft_confirmation` 节点复用 `training_parser.parse_training_draft`，草稿仍为 `pending`，正式写入仍由康复师确认 API 触发。

### 阶段 4：风险与扩展业务（已完成首期）

- 增加风险核查分支和人工复核提示。
- 逐项接入评估草稿、随访草稿、训练记录修订；每项单独验收（仍未实施）。
- 评估模型工具选择准确率、人工改写率、等待节点完成率和失败率（仍未实施）。

已落地：`risk_review` 分支（提示人工核查，不自动诊断）、统一回合接口
`POST /api/assistant/turns/`、`POST /api/assistant/tasks/{id}/resume/`、
`POST /api/assistant/tasks/{id}/customer-selection/`。前端接入统一回合接口、
评估/随访草稿接入等仍为后续项。

### 阶段 5：多客户批量训练补记（已完成）

- 新增意图 `multi_customer_training_record`：一轮输入含多位客户训练描述时，provider 将原文拆分为有序子项（`MultiCustomerTrainingSplit` schema 校验）。
- 父级 `AssistantTask`（`task_type=multi_customer_training_record`，`customer=null`）+ 有序子项 `TrainingRecordBatchItem`，按 `sequence` 严格逐项推进，绝不并行猜测客户。
- 每个子项独立走「搜索客户 → 确认客户 → 生成 `pending` 草稿 → 康复师编辑/确认 → 正式写入」闭环；正式保存复用 `training_parser.confirm_training_draft` 幂等，重复确认不建第二条记录。
- 顺序约束：存在更早未终态子项时禁止处理当前子项；父任务全部子项终态后才 `completed`。
- 前端在统一聊天流以 `batch_overview`、`batch_draft`、`batch_summary` 卡片按时间顺序渲染完整顺序推进交互。

验收：`客户A 深蹲 10 次、康复按摩 1 次；客户B 俯卧撑每组 10 次共 5 组` 拆为 2 项，逐项确认客户、编辑草稿、正式保存，最后展示汇总并完成父任务。

## 9. 验收与回滚

- 同一输入在没有客户事实需求时不调用客户 Tool。
- 需要客户事实时，未确认客户绝不越权读取数据。
- 多个同名客户始终显示选择，而不是模型猜测。
- 每次图分支、Tool 调用、等待、恢复、失败和确认均可追溯到 TaskEvent/Run。
- LangGraph 故障时可关闭 feature flag，退回当前 Conversation + 训练补记流程；已有任务仍可通过原确认 API 完成。

## 10. 当前不做

- 自动提交任何正式业务数据。
- 将完整 Conversation 或健康信息写入 LangGraph checkpoint。
- 让模型任意决定 Python 函数、数据库查询或跨客户访问。
