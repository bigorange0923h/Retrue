# 受控 ReAct 客户查询改造计划

> 状态：待实施  
> 创建日期：2026-09-03  
> 适用范围：统一 AI 助理中的客户查询、训练进展分析、评估与课程事实查询  
> 前置条件：现有 LangGraph 编排、`AssistantTask`、`AssistantRun`、`ToolExecution`、客户身份解析与只读 Tool 注册表可用。

## 1. 目标与架构定位

将当前客户问题的固定流程：

```text
customer_question
  -> choose_read_tools
  -> execute_read_tools
  -> answer_with_context
```

升级为有限、可审计的 ReAct 查询子图。该子图只负责根据已获得的事实决定是否需要继续调用**已注册的只读 Tool**；不得接管业务写入、草稿确认、权限判定或客户身份确认。

目标示例：

> 黄伟成最近训练怎么样？

系统应完成：

1. 理解这是一项客户训练进展查询，并提取“黄伟成”作为姓名线索；
2. 仅在当前康复师的客户目录内解析身份；
3. 唯一命中后绑定客户，多命中时等待康复师选择；
4. 由模型从服务端提供的只读 Tool 子集中选择所需数据；
5. 根据 Tool 的脱敏观察结果决定继续查询或给出最终回答；
6. 将每次 Tool 调用、失败与最终结果保留为可追溯审计记录。

整体采用“业务状态机为主，受控 ReAct 为辅”的单 Agent 架构：

```text
用户消息
  -> 意图理解与风险初筛
     |- 通用知识问答 -> 直接回答
     |- 客户查询/分析 -> 身份解析 -> 受控 ReAct 查询子图 -> 回答
     `- 草稿/写入类业务 -> 固定 LangGraph 流程 -> 人工确认 -> 领域服务
```

## 2. 不在本次范围内

- AI 自动创建或修改正式训练记录、评估、随访、课程等业务数据；
- 模型自行选择其他客户、康复师、数据库记录或资源 ID；
- 模型生成 Python、SQL、网络请求或任意函数调用；
- 将原始对话、完整健康信息、完整 Tool 返回或模型推理过程持久化到 Graph State；
- 多 Agent 协作编排。

训练补记、评估草稿、随访草稿和记录修订仍应沿用现有固定工作流与康复师确认边界。

## 3. 目标流程

```text
用户：黄伟成最近训练怎么样？
  -> 理解请求
     - intent = customer_analysis
     - customer_name_hint = 黄伟成
     - query_goal = recent_training
  -> 客户身份解析（当前康复师目录）
     |- 唯一命中 -> 绑定可信 customer_id
     |- 多个命中 -> wait_customer_selection
     `- 未命中   -> wait_customer_name
  -> prepare_react_tools
  -> react_decide
     |- tool_call -> execute_react_tool -> react_decide
     `- final     -> react_finalize -> END
```

ReAct 循环的安全终止条件：

- 单回合最多 3 次 Tool 调用；
- 单回合最多 3 次模型决策；
- 相同 Tool 与相同规范化参数在同一回合只执行一次；
- 单个 Tool 最多重试一次；
- Tool 失败、达到上限或模型无法形成有效动作时，转入安全降级回答；
- 最终回答必须明确资料不足之处，不能补全或伪造不存在的事实。

## 4. 意图与查询目标

### 4.1 新增意图

新增 `customer_analysis`，用于需要读取已确认客户事实的查询、比较、汇总或趋势判断。现有 `customer_question` 可以在兼容期内保留，随后统一迁移到 `customer_analysis`。

以下请求应进入该意图：

- “黄伟成最近训练怎么样？”
- “她近两周一共训练了几次？”
- “疼痛有没有改善？”
- “结合训练和评估，建议下次重点关注什么？”
- “最近有没有缺课？”

### 4.2 查询目标

`IntentResult` 增加以下结构化字段：

```python
query_goal: str
requires_customer_context: bool
```

首批支持的 `query_goal`：

| 查询目标 | 示例 | 初始 Tool 子集 |
| --- | --- | --- |
| `customer_profile` | “他的基础情况是什么？” | `get_customer_context` |
| `recent_training` | “最近训练怎么样？” | `list_recent_training_records` |
| `assessment_progress` | “评估有没有改善？” | `get_initial_assessment_status` |
| `attendance_or_course` | “最近来得勤不勤？” | `list_customer_course_sessions` |
| `comprehensive_progress` | “整体恢复进展如何？” | 客户上下文、训练、评估、课程 Tool |

初期可保留“确定性规则优先 + 模型补充”的实现。模型仅输出受 schema 约束的候选意图与查询目标，服务端仍负责确认其合法性。

## 5. 后端改造

### 5.1 Graph State

修改 `retrue-server/apps/ai/orchestration/state.py`，增加仅当前 `invoke` 内存可用的字段：

```python
react_iteration: int
react_actions: list[dict]
react_observations: list[dict]
react_final_answer: str
query_goal: str
available_react_tools: list[dict]
```

这些字段不得加入 `PERSISTED_STATE_KEYS`。`AssistantTask.state_data` 仍只持久化任务 ID、会话 ID、已确认客户、意图、下一节点、缺失字段、资源引用、Tool 执行引用和最小身份解析摘要。

### 5.2 受控 ReAct 节点

修改 `retrue-server/apps/ai/orchestration/nodes.py`，新增：

| 节点 | 职责 |
| --- | --- |
| `prepare_react_tools` | 按 `query_goal` 从服务端只读注册表构造可用 Tool 子集，不暴露 Python handler。 |
| `react_decide` | 调用模型，要求其输出一次受 schema 约束的“Tool 调用”或“最终回答”决策。 |
| `execute_react_tool` | 校验模型决策、服务端注入可信上下文、执行 Tool、保存脱敏 Observation 与审计引用。 |
| `react_finalize` | 基于已取得事实生成最终答复，区分系统事实与建议。 |

当前 `choose_read_tools_node()` 固定选择 `get_customer_context`。该节点不应再负责复杂客户分析；可在迁移期保留给兼容的旧 `customer_question`，然后逐步移除。

### 5.3 Graph 路由

修改 `retrue-server/apps/ai/orchestration/graph.py`：

```text
customer_analysis
  -> ensure_customer
  -> prepare_react_tools
  -> react_decide
     |- tool_call -> execute_react_tool -> react_decide
     `- final     -> react_finalize -> END
```

`ensure_customer` 必须位于任何客户数据 Tool 之前。未绑定、未唯一确定或未获康复师选择的客户，禁止进入 `prepare_react_tools` 或执行客户事实查询。

### 5.4 模型决策 Schema

新增 `retrue-server/apps/ai/schemas/react.py`，通过 Pydantic 校验模型返回。

允许的 Tool 决策：

```json
{
  "action": "tool_call",
  "tool_name": "list_recent_training_records",
  "arguments": {"days": 14},
  "reason": "需要读取近期训练频率和训练内容"
}
```

允许的最终决策：

```json
{
  "action": "final",
  "answer": "根据近 14 天训练记录……",
  "insufficient_information": false
}
```

Schema 必须：

- 将 `action` 限制为 `tool_call` 或 `final`；
- 将 `tool_name` 限制为本轮提供的 Tool 名称；
- 限制 `reason`、`answer` 和所有文本参数长度；
- 拒绝未知字段；
- 禁止模型提交 `customer_id`、`therapist_id`、资源归属字段或任意执行指令。

## 6. Tool 白名单与权限边界

`retrue-server/apps/assistant_tasks/tools.py` 中的 `TOOL_DEFINITIONS` 是唯一可信 Tool 注册表，现有 `READ_ONLY_TOOL_ALLOWLIST` 是 ReAct 查询子图可调用工具的最高权限边界。

模型得到的 Tool 清单必须来自 `list_tool_definitions()` 的安全描述，不能从提示词、前端或模型输出中构建注册表。

执行时采用如下规则：

1. 模型只能提出 `tool_name` 与低风险业务参数，例如 `days`、日期范围和 `limit`；
2. 服务端忽略或拒绝模型提供的 `customer_id`；
3. 服务端从已持久化的 `AssistantTask.customer_id` 注入可信客户上下文；
4. 继续使用 `_validate_arguments()` 校验字段、类型、日期跨度、数量和总长度；
5. 继续使用 `_resolve_customer()` 校验任务客户一致性及当前康复师归属；
6. 仅允许 `read_only=True` 的 Tool；写操作不进入 `execute_tool()` 的 ReAct 路径；
7. 每次执行创建 `AssistantRun`、`ToolExecution` 与脱敏审计摘要；
8. Tool 结果仅在当前回合以脱敏、限长 Observation 形式供模型使用。

建议首批 Tool 映射：

| 查询目标 | 允许 Tool |
| --- | --- |
| `customer_profile` | `get_customer_context` |
| `recent_training` | `list_recent_training_records` |
| `assessment_progress` | `get_initial_assessment_status` |
| `attendance_or_course` | `list_customer_course_sessions` |
| `comprehensive_progress` | 以上所有只读客户查询 Tool |

## 7. 提示词

新增独立提示词文件，符合项目提示词管理约定：

```text
retrue-server/apps/ai/prompts/react_tool_decision_system.txt
retrue-server/apps/ai/prompts/react_tool_decision.txt
retrue-server/apps/ai/prompts/react_customer_answer_system.txt
```

决策提示词仅包含：

- 用户问题；
- 已确认客户的最小脱敏标识；
- 当前查询目标；
- 本轮允许的 Tool 名称、说明和输入 schema；
- 已取得的脱敏 Observation；
- 剩余 Tool 调用和决策次数。

提示词必须要求模型：

- 不得虚构 Tool、数据、客户或调用结果；
- 信息不足时停止并如实说明；
- 不得输出推理链、代码、SQL 或客户 ID；
- 最终回答将“系统记录显示的事实”与“康复建议”分开表述；
- 对风险、禁忌或诊断不确定性，转人工核查提示而非自动下结论。

## 8. 前端调整

修改 `retrue-web/src/views/assistant/AssistantView.vue` 及相关卡片组件。

页面只展示业务语言，不暴露 ReAct、Graph、节点、Tool、Run 或内部推理：

- “正在查询近期训练记录……”
- “正在结合评估记录分析……”
- “请选择客户”
- “资料不足，建议补充……”

可选在最终答复下方增加可折叠的“参考资料”区域，展示用户能理解的来源，例如“近期训练记录、首次评估、课程安排”；不得展示 Tool 参数、原始结果和敏感日志。

## 9. 测试与验收

新增或扩展：

```text
retrue-server/apps/ai/test_react_orchestration.py
retrue-server/apps/ai/test_prompts.py
retrue-server/apps/assistant_tasks/test_tools.py
```

必须覆盖：

1. “黄伟成最近训练怎么样”先完成客户身份解析，再查询训练记录；
2. 同名客户必须进入人工选择，选择前不得查询训练、评估、课程；
3. 不存在的 Tool、写 Tool 和未在本轮子集中的 Tool 全部被拒绝；
4. 模型提交 `customer_id`、`therapist_id` 或其他越权字段会被拒绝；
5. 仅使用任务已绑定且属于当前康复师的客户；
6. 相同 Tool 与相同参数不会在同一回合重复执行；
7. Tool 调用与模型决策次数都严格受上限约束；
8. Tool 失败、无记录、模型 schema 不合法时不伪造客户事实；
9. 最终答复包含可验证的事实来源，并将事实和建议分开；
10. 每一次 Tool 调用、失败、完成均产生可追溯的 `ToolExecution`、`AssistantRun` 与 `TaskEvent`；
11. 训练补记、评估、随访和修订不会误入 ReAct 查询子图；
12. `AI_ORCHESTRATION_ENABLED=false` 时安全降级，既有确认接口仍可完成已有草稿。

## 10. 分阶段实施

### 阶段 A：最小可用查询循环

- 新增 `customer_analysis`、ReAct schema 与 4 个节点；
- 首批仅开放 `list_recent_training_records`；
- 覆盖训练次数、近期训练内容、训练记录是否不足等问题；
- 完成 Tool 越权与循环上限测试。

### 阶段 B：多源进展分析

- 新增 `get_customer_context`、`get_initial_assessment_status`、`list_customer_course_sessions` 的按目标 Tool 子集；
- 支持训练频率、评估状态、出勤和综合恢复进展；
- 增加最终回答的事实/建议格式校验。

### 阶段 C：质量监控与优化

- 记录脱敏指标：平均 Tool 调用次数、无效调用率、上限触发率、Tool 失败率、人工纠正率；
- 根据真实问法调整 `query_goal`、Tool 描述与提示词；
- 仅在数据证明必要时扩展其他只读 Tool。

## 11. 验收标准

- 用户可自然地询问已确认客户的训练、评估、课程和综合进展；
- 系统能按真实数据需要连续查询，但任何一轮都不会无限循环；
- 任何客户数据访问均可追溯到当前康复师、任务和 ToolExecution；
- AI 无法调用未注册 Tool、传入其他客户 ID 或写入正式业务数据；
- 草稿与正式写入流程行为不变，仍需康复师确认；
- Graph State 和审计日志不新增敏感原文或完整医疗数据持久化。
