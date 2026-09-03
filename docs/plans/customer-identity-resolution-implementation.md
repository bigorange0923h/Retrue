# 客户身份解析改造实施计划

> 依据：`docs/customer-identity-resolution-adjustment.md`
> 目标：把 AI 编排中的客户身份解析从「正则启发式猜姓名」升级为「目录预匹配 + 人工确认兜底」，
>       并让多客户批量补记从「按名字个数分段」改为「训练语义分段 + 每段目录匹配」。
> 范围：全部按文档 §3-§9 实施，跑通 §10 验收用例。CustomerAlias 仅建表 + 迁移，不接管理入口。

## 关键约束（贯穿全程）

1. AI 只做「建议/预判」，绝不自动决定客户身份写入；任何客户绑定的最终确认都需康复师点击。
2. 文本原文、手机号、病史绝不写入 LangGraph 状态 / checkpoint（仅保留脱敏后的匹配中间信息）。
3. 目录匹配只在当前康复师（therapist）名下进行，永不跨康复师匹配。
4. 同名/多候选/低置信一律回落「客户选择卡片」，绝不自动猜。
5. 每次身份解析都留审计事件，脱敏日志。
6. 用 `AI_ORCHESTRATION_ENABLED` 作为可回滚总开关；内部解析新能力可再以环境/常量逐步启停。
7. Django 外键一律 `db_constraint=False`；commit 中文信息用 `git commit -F` 避免乱码。

## 阶段划分与验收

### 阶段 0：基线
- 当前 commit `db9fc2c`，工作区干净（仅新增文档未跟踪）。
- 基线测试：后端 275 全通过、前端 build 通过。

### 阶段 1：CustomerAlias 表 + 迁移
- 新增模型 `CustomerAlias`：`therapist`(FK, db_constraint=False)、`customer`(FK)、`alias`、`normalized_alias`、
  `created_at`；Meta 唯一约束 `(therapist, normalized_alias)`，索引 `(therapist, normalized_alias)`。
- 生成迁移；`makemigrations --check` 通过。
- 本期不做 admin / serializer 维护入口。
- 验收：`manage.py check` 通过、迁移文件存在、`makemigrations --check --dry-run` 无遗漏。

### 阶段 2：客户目录服务 + 匹配算法
- 新增 `apps/customers/catalog.py`（或 apps/ai 下目录服务），提供：
  - 文本规范化 `normalize_name(name)`：全半角/大小写折叠、去空白与标点、保留汉字/字母/数字、过滤称谓词。
  - 别称/全名解析：把原文里候选姓名片段按「目录：正式 name + CustomerAlias.normalized_alias」精确/前缀匹配。
  - 目录加载：仅当前 therapist；可含 CustomerAlias 展开映射（如别称「老王」→ 正式「王建国」）。
  - 匹配打分 + 冲突检测：区分「唯一命中 / 多候选命中 / 低置信（候选为空需人工给姓名）」。
  - `match_referent(therapist, raw_text, ...)`：返回结构化 `ResolutionResult`（候选列表、是否歧义、是否唯一、置信档位）。
- 全套单元测试覆盖文档 §6.2 规则与 §6.3 冲突/边界。
- 验收：新增服务单测全绿；不改动既有 275 个测试结果。

### 阶段 3：编排状态携带解析结果（脱敏）
- 在 `OrchestrationState` 增加**仅内存**字段（不入 PERSISTED_STATE_KEYS）：
  `preselected_customer_id`（预选/唯一命中，仍需人工确认）、`customer_candidates`（候选列表）、`identity_status`（pending/lookup/resolving/unresolved/confirmed）。
- 明确哪些字段可入状态、哪些绝不入（原文等）。
- 验收：相关序列化/checkpoint 测试通过，确认无原文落盘。

### 阶段 4：单客户身份解析节点改造
- 重写 `classify_intent_node` / `customer_lookup_node` / `ensure_customer_node` 的身份解析链路：
  - 由「猜姓名 → 搜同名」改为「目录预匹配 → 唯一则 pre-select 卡片（仍需确认）/ 歧义则选择卡片」。
  - 保持既有意图代码不变；仅在「需要客户上下文」时进入目录匹配。
  - 前端返回结构化 `identity` 信息：`preselected_customer_id`、`candidates`、`status`。
- 更新对应编排测试（含 §10 前 5 条验收语义）。
- 验收：跑通 §10 单客户验收（问话/补记/同名客户/未确认不可写）。

### 阶段 5：多客户先分段再匹配
- 重写多客户识别与分段：去掉依赖「客户X 个数」的 `_is_multi_customer`/`_extract_customer_name` 启发式，
  改为：先判定是否训练补记（单或多），再用「训练语义分段」把原文切成若干段，每段独立做目录匹配。
  - mock/解析器新增「分段器」：按客户转折/新训练起点切段。
  - 每段目录匹配：唯一命中→候选填充「名字正式化」并 pre-select；歧义/空→该子项进入待选。
- 保留现有 `TrainingRecordBatchItem` 状态机与串行保存；只改「分段 + 命中客户」来源。
- 验收：跑通 §10 多客户验收（A/B 两位都唯一命中、混合含未命中客户、首尾含叙述等）。

### 阶段 6：前端卡片
- 新增/调整卡片类型：`identity_resolution`（用于单客户身份预选/选择展示）。
- 多客户概览中体现每子项的命中状态（唯一命中自动带出、需人工选择则高亮）。
- 适配 `AssistantCardRenderer` 与卡片组件、类型定义、API 类型。
- 验收：npm build / vue-tsc 通过；交互可用（点选确认绑定）。

### 阶段 7：审计与文档 + 全量验收 + 提交
- 关键身份解析/确认写入 `TaskEvent`，脱敏。
- 更新架构文档（身份解析策略）与执行计划、API 文档。
- 全量验收：`manage.py check` + `makemigrations --check` + 全量 test + 前端 build。
- 按阶段 git commit，最后推送。

## 验收用例映射（文档 §10）
1. 单客户问历史 → 目录唯一命中 → pre-select 卡片 → 康复师确认后绑定并答。
2. 训练补记（今天张三做了…）→ 目录唯一命中 → pre-select → 确认 → 建草稿。
3. 同名客户（目录两个「王伟」）→ 返回 2 候选 → 选择卡片 → 康复师选一个 → 继续。
4. 未确认客户前，任何写操作被拒（重复任务/状态校验兜底）。
5. 目录无此人 / 表述含糊 → unresolved → 请康复师提供完整姓名或选择。
6. 多客户 A+B 均唯一命中 → 各段带出正式名 → 串行补记。
7. 混合段（含未命中/歧义）→ 该子项转待选，其余继续。
8. 首尾带叙述/寒暄 → 分段不丢客户。
9. 工具失败安全降级 + 恢复。
10. 前端展示选择/预选卡片，离开页面可继续未完成任务。
