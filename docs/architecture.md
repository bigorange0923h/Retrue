# Retrue 系统架构

## V1 边界

V1 采用单体架构，优先跑通「今日客户 → 训练记录 → AI 草稿确认 → 正式保存 → 客户时间线 → 下次备课」闭环，并补齐「课程计划 → 课表 → 训练记录」的排课闭环。

```text
Vue 3 Web
    │ REST API
    ▼
Django + DRF
    ├── 业务 Apps
    ├── AI Service（仅生成草稿）
    └── Django Admin
    │
    ▼
PostgreSQL
```

## 业务模块边界

| 模块 | 职责 |
| --- | --- |
| accounts / therapists | 登录、账号与康复师身份 |
| customers | 客户档案、隐私字段脱敏与数据隔离 |
| schedules / courses | 课表、课程与课时流水 |
| assessments / rehab | 首次评估、复评、康复计划与阶段 |
| training / exercises | 训练记录、动作库、家庭训练 |
| followups | 回访、复查与轻量待办 |
| ai | AI 草稿解析、备课建议、风险提示、专业问答与客户上下文编排 |
| assistant_tasks | 统一 AI 助理任务、执行、Tool 日志、恢复、幂等与状态事件 |
| audit | 正式记录变更的审计追踪 |

## 课程计划与课表联动

课程计划和课表分别承担不同职责，但通过计划内课程建立可追踪的闭环：

```text
RehabPlan（客户课程计划）
    ↓ 包含
RehabPlanCourse（某门课程、计划次数、时长和课时快照）
    ↓ plan_course
CourseSession（具体日期、时间和状态）
    ↓ course_session
TrainingRecord（正式训练记录）
```

- 创建客户课程计划只保存计划和计划内课程，不静默生成课表。保存成功后，PC/移动端向康复师提供“现在安排”或“稍后再说”；康复师也可以从客户详情或课表再次点击“安排课程”。
- 批量安排使用 `POST /api/courses/batch/preview/` 先生成日期/时间预览，再由 `POST /api/courses/batch/confirm/` 写入课表；从某门计划内课程进入时，`/api/rehab/plan-courses/{id}/schedule/preview/` 和 `/confirm/` 是同一能力的带课程快捷路由。
- 批量请求使用 `customer`、`plan_course`、`start_date`、`weekly_count`、`weekdays` 和 `start_time`。`weekdays` 采用 `0=周日、1～6=周一至周六`。开始日期受计划日期范围限制，候选数量按计划的待安排次数生成。
- 预览不写数据库；确认时重新锁定计划内课程、检查有效排课数量和时间冲突，并在一个事务中全部创建或全部失败。有效时间冲突只检查同一康复师的待上课/已完成课程；取消和请假不占用时间。
- V1 的时间冲突依靠服务层查询与事务复查；同一计划内课程会加行锁，正常单人操作可安全阻止重复安排。若未来出现多个终端同时为同一康复师的不同计划课程排课，仍存在极小的并发重叠窗口，届时应增加 PostgreSQL 排他约束或康复师维度的事务锁。
- `CourseSession.arrangement_type` 只有 `plan`、`initial_assessment`、`reassessment`、`other` 四种值。`plan` 必须有关联计划内课程，其他三种必须不关联计划内课程，分别用于首次评估、阶段复评和其他事项。
- 计划课程的 `completed_count`、`scheduled_count`、`unscheduled_count`、`overdue_count` 和 `next_session` 都根据课表实时计算。新增有效排课前，服务层保证“已完成 + 待上课”不超过计划次数；调减次数、暂停/取消课程或关闭计划前，必须先处理会受影响的待上课课程。
- 正式训练记录保存后沿用既有事务：课程变为已完成，课时包按排期快照幂等扣减，计划课程进度随之更新。

业务层错误使用康复师可执行的提示（例如“9月8日 14:00 已有其他客户课程，请调整时间”），前端向导使用“安排课程、已安排、待安排、下次上课”等自然文案，不要求康复师理解数据库字段或内部 ID。

## AI 数据流

```text
原始输入 → AI 结构化草稿 → 康复师编辑/确认 → 正式业务记录 → 审计日志
```

- AI 草稿与正式记录必须分表或通过明确状态字段隔离。
- AI 不得直接更新训练记录、评估、阶段、课时或风险处理结果。
- 客户识别不确定时必须返回候选项，禁止自动猜测并保存。

统一 AI 助理额外采用“统一任务编排、业务内容分域保存”：Conversation 只保存对话；AssistantTask 保存跨页面可恢复的业务进度；AssistantRun 保存一次 AI 执行；ToolExecution 保存脱敏的工具执行过程；训练、评估和随访草稿仍保存在各自领域表。任务与资源关联不依赖数据库物理外键，service 必须校验登录康复师、客户与来源资源一致。

AI 对话流程编排由 `apps/ai/orchestration` 基于 LangGraph 实现，但 LangGraph 只负责意图识别、分支路由、Tool 调用顺序与等待节点；权限校验、任务状态迁移、正式业务写入和审计仍由 Django 领域服务统一负责。图状态只保存任务、会话、客户、意图、下一步与必要引用 ID，不保存完整聊天记录、手机号、原始敏感资料、完整工具输出或提示词。编排功能受 `AI_ORCHESTRATION_ENABLED` 开关控制（默认关闭），编排器故障时可一键退回原有 Conversation + 训练补记流程，已有任务仍可通过原确认 API 完成。

编排图按意图分派：`general_knowledge` 直接回答；`customer_lookup` 按姓名查询客户，唯一匹配直接绑定、多个同名进入等待选择、无匹配等待补充姓名；`customer_question` 走只读 Tool（`get_customer_context` 等）后带事实回答；`training_record` 先确保客户已绑定，再复用 `training_parser` 生成 `pending` 草稿并进入等待确认；`assessment`/`training_revision`/`followup` 复用统一 `AiDraft`（按 `draft_type` 区分）生成领域草稿，确认后分别创建评估（`status=draft`）、更新目标训练记录、创建随访待办；`risk_review` 提示人工核查，不自动诊断。意图分类采用确定性规则优先，规则无法判定时由模型补充（受白名单约束）。等待点映射到任务状态：`wait_customer_name`/`wait_customer_selection` 为 `waiting_user`，`wait_draft_confirmation` 为 `waiting_confirmation`。统一回合接口 `POST /api/assistant/turns/`、`POST /api/assistant/tasks/{id}/resume/`、`POST /api/assistant/tasks/{id}/customer-selection/` 是新增并行入口，与现有训练补记确认 API 并存，不替换。

真实 AI 回复由节点调用 provider 生成并写入 Conversation，回复正文只在当轮内存中返回（`reply_content`），绝不写入任务状态或 checkpoint；回复区分“系统记录”与“建议”，不伪造客户历史。恢复严格从暂停节点继续：不重新意图识别、不重新猜客户姓名、不重复生成草稿，草稿待确认时只重新返回已有 `draft_id`。Tool 执行落实单轮上限、相同 Tool+参数组合去重、失败最多重试 1 次并安全降级；客户未确认时只允许客户匹配，禁止读取训练、评估、课程等客户数据。每次统一回合创建一条可追溯的 `AssistantRun`，关键节点、等待、恢复、Tool 调用与失败均写入 `TaskEvent`，事件只保存节点名、分支原因、资源 ID 与脱敏摘要。

### 客户身份解析

AI 不再靠“正则猜姓名→按姓名精确查”来确认客户，而是用**当前康复师的最小客户目录**对原文做确定性匹配：

- 目录服务 `apps/customers/catalog.py` 只返回 `id/name/aliases/phone_masked`（绝不含完整手机号、病史），并严格限定在当前康复师名下，绝不跨康复师或模糊枚举。
- `CustomerAlias` 表（`therapist` 内 `normalized_alias` 唯一，`db_constraint=False`）承载别称（如“阿成”→正式名），本期仅建表 + 迁移，维护入口后续补。
- 匹配归一化：NFKC、去称谓（客户/病人/患者）、去空白、折叠大小写；短名含于长名、别称与他人正式名冲突一律视为歧义，不自动绑定。
- 匹配结果三态并落到卡片：
  - `preselected`（唯一精确命中，`customer_preselected` 卡，可换/确认）——训练补记会据此生成 `pending` 草稿并停在 `wait_draft_confirmation`，正式保存仍由康复师确认，不绕过把关；
  - `ambiguous`（同名/多候选，`customer_selection` 卡，绝不自动绑定）；
  - `unmatched`/无姓名（`wait_customer_name`，请补充或主动搜索）。
- 身份解析结果仅以最小摘要 `identity_resolution{status, matched_customer_ids, source}` 落状态（不含姓名原文）；`preselected_customer_id`、候选、目录均为仅内存字段，恢复时按目录重算、不信任历史。

### 多客户批量训练补记

当一轮输入包含多位客户的训练描述时（意图 `multi_customer_training_record`），编排进入批量补记流程：先用共享训练语义分段器 `apps/ai/segmentation.py` 把原文按“客户训练起点”切段（名称后须紧跟训练叙述，避免误切寒暄/叙述），再对每段做客户目录匹配，创建父级 `AssistantTask`（`task_type=multi_customer_training_record`，`customer=null`）与有序子项 `TrainingRecordBatchItem`，随后按 `sequence` 严格逐项推进，绝不并行猜测客户。是否多客户由“真实分段段数 ≥ 2”决定，而非两套割裂的正则数片段，保证判定与实际拆分一致。

```text
输入描述 → 拆分校验（MultiCustomerTrainingSplit）
  → 父任务 + 有序子项（pending）
  → 逐项：搜索客户 → 确认客户 → 生成草稿（pending）
  → 康复师编辑/确认 → 正式训练记录（幂等）
  → 推进下一子项 → 全部终态 → 父任务 completed
```

- 子项状态机：`pending → searching_customer → waiting_customer → waiting_draft → saving → completed | skipped | failed | cancelled`；父任务状态映射等待点 `waiting_user`（客户确认）与 `waiting_confirmation`（草稿确认），等待态之间不允许直接转换（先转 `running` 再转目标，保留两段审计事件）。
- 顺序约束：存在更早未终态子项时，禁止处理当前子项；已完成/已跳过/已失败/已取消视为终态，可被跳过推进。
- 客户识别绝不自动猜测：每个子项的 `customer_name_hint` 优先用客户目录匹配（`catalog.resolve_customers_from_text`，支持别称/近似命中，唯一命中带出、歧义返回多候选、无命中回落到去称谓精确查询兜底）；同名或多候选必须由康复师选择；未确认客户的子项禁止写入。
- 每个子项的草稿复用 `AiDraft`（`status=pending`），通过 `TrainingRecordBatchItem.ai_draft` 关联而非父任务，绕开父任务类型与 `training_parser` 的任务类型校验；正式保存复用 `training_parser.confirm_training_draft` 的幂等闭环，重复确认不创建第二条训练记录。
- 父任务在全部子项达到终态后才转为 `completed`；任一步失败可单独重试，不影响已成功写入的正式记录。

批量补记接口挂在 `/api/assistant/` 下：`GET /tasks/{id}/batch/`（概览）、`POST /tasks/{id}/items/{item_id}/customer-search/`、`/customer-selection/`、`PATCH /tasks/{id}/items/{item_id}/draft/`、`POST /tasks/{id}/items/{item_id}/confirm/`、`POST /tasks/{id}/items/{item_id}/skip/`。前端在统一聊天流中以 `batch_overview`、`batch_draft`、`batch_summary` 三类卡片按时间顺序渲染，客户确认、草稿编辑、正式确认与汇总全部在聊天内完成。

## 评估生命周期与指标规则

评估记录统一使用 `status=draft|completed`：康复师在引导式五步流程中点击“下一步”时自动保存草稿，保存成功后才进入下一阶段；只有服务端完成完整校验后才转为 `completed`。客户详情的首次评估完成判断、时间线、趋势分析、阶段进展和 AI 上下文均只查询已完成评估；草稿不作为正式事实。

首次评估由 `therapist_id + customer_id + assessment_type=initial` 条件唯一约束保护，已有草稿时进入继续编辑流程，不创建第二份。指标定义由后端统一提供，疼痛（NRS 0～10）和肌力（MRC 0～5）的 `score_max`、量表和单位由服务端派生；ROM 使用角度，特殊测试和功能动作使用分类结果，页面不要求康复师填写满分。

指标更新采用**按 id 差异同步**而非整体删除重建：提交项携带 `id` 时更新原指标（保留原 id），未携带 `id` 的为新增，本次未提交的已存在指标才被删除。这样避免重建导致指标自增 `id` 变化、前端按 id 做 diff/高亮时失配。新建评估的指标仍由服务端按类型派生量表与满分。

评估完成接口负责状态转换、指标专用校验、权限/计划归属校验和审计记录。已完成评估重复确认采用**空转短路**：通过正常流程完成（`completed_at` 非空）且完成后未再修改（`updated_at <= completed_at`）的记录直接返回，不再重复全量校验；若完成后被修订过，则按最新内容重新校验，缺失必填项会返回 `assessment_incomplete`。AI 仅可提出待康复师确认的结构化建议，不能自动完成评估或修改正式结果。

前端“去评估 / 继续评估”引导通过首评直达接口 `GET /api/assessments/initial/?customer_id={id}` 判断首评状态（`{exists, status, assessment_id}`），避免各页面自行遍历列表查找 `assessment_type=initial` 造成逻辑分散与重复判断。

## 客户私有知识库与 AI 记忆（后续扩展）

AI 能力使用两类相互隔离的知识：通用专业知识（动作、测试、风险原则）和客户私有康复知识（经康复师确认的限制、偏好、康复结论与会话摘要）。

```text
AI 请求
  ↓
权限与客户绑定校验
  ├── 通用专业检索
  └── 客户私有上下文：therapist_id + customer_id 强制过滤
  ↓
AI Context Builder（近期记录、阶段、风险、有效知识、会话摘要）
  ↓
LLM / 规则服务
```

- 未绑定客户的通用问答不得携带任何客户健康信息。
- AI 只能提出“建议写入知识”的候选；康复师确认后才可形成正式客户知识或长期会话摘要。
- 业务数据库仍是权限和事实来源；未来 pgvector 只用于受过滤的召回，不能绕过业务权限。

## 本地环境

- 开发 PostgreSQL 独立准备，旧开发环境使用 `127.0.0.1:5433`，以 `retrue-server/.env` 为准。
- 生产 Compose 仅管理 Django，通过 `host.docker.internal` 访问宿主机 PostgreSQL；宿主机 Nginx 提供前端静态文件和 API 代理。
- 开发环境示例为 `retrue-server/.env.example`，生产示例为根目录 `.env.example`，完整部署步骤见 [DEPLOY.md](../DEPLOY.md)。
