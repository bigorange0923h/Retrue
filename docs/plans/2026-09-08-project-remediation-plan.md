# Retrue 问题整改与能力补齐：后续 AI 执行计划

制定日期：2026-09-08。评估基线：`7d4c369`。

依据：[整体评估与 22 项问题清单](../reviews/2026-09-08-project-assessment.md)。本文件是未来执行交接，不表示已完成整改。

## 1. 使用方式与范围

本轮交付仅包括评估与计划。后续用户要求“执行本计划”后，按任务编号推进，每项先核实当前代码是否已变化，不重复实现已经修复的能力。

优先保留现有单体、课程领域主链、领域服务、LangGraph、任务表和 AI 草稿确认机制。不得以整改为由自动引入微服务、多人协作模型、全新 Agent 平台或全量业务重写。

开始每项前阅读根目录 `AGENT.md`、产品设计、相关 API/数据库/测试规范。发现历史文档冲突时，用本计划指出的位置核对当前实现；重大新业务规则先形成具体方案，不能自行假定。日常修复已有权限/字段/错误逻辑可以直接推进，不需重复确认。

执行期间：

1. 先检查工作区和当前基线，保留用户未提交改动。
2. 一项一个可验证变更集；实现、测试、API 类型、migration、SQL 和文档按需同步。
3. 本计划不授权清理真实数据、执行生产迁移、发布、向客户发送消息或提交私有配置。受影响项做完可审阅成果后，再按实际授权推进。
4. 没有数据库/真实模型/浏览器证据，就标明“待验证”，不能记为 done。
5. 任务状态更新到本文件底部交接记录；不修改 Codex 记忆文件。

## 2. 任务索引、依赖与顺序

全部实现状态初始为 `todo`；T00 在本轮已有部分证据，但尚未建立完整可运行基线。

| 任务 | 范围 | 对应问题 | 前置依赖 | 大小 | 状态 |
| --- | --- | --- | --- | --- | --- |
| T00 | 当前状态、依赖与验证基线 | F18、F20 | 无 | 小 | implemented（验证部分未全量） |
| T01 | 关联归属与 API 参数边界 | F01、F02、F08 | T00 的代码盘点 | 中 | implemented |
| T02 | 登录与账号安全 | F05 | T00 的配置盘点 | 中 | implemented |
| T03 | 训练字段无损、修订冲突、审计 | F03、F08 | T01 | 中 | implemented |
| T04 | 风险事实、知识有效性与检索 | F04、F11 | T01 | 中，可拆两次 | implemented |
| T05 | 排课/完成/扣课并发与纠正规则 | F06、F07、F21 | T01、T03；新规则见决策表 | 大，分子阶段 | todo |
| T06 | AI 入口统一与故障恢复 | F09、F10 | T03、T04 | 大，分子阶段 | todo |
| T07 | 今日待办、回访闭环、基础审计 | F08、F12、F13 | T01；涉及课程部分依赖 T05 | 中 | todo |
| T08 | 家庭训练交付、动作/别称维护 | F14 | T01、T03 | 中，可分功能 | todo |
| T09 | 客户切换与页面状态隔离 | F15 | T01 | 中 | todo |
| T10 | 导出、删除预览与保留设计 | F16 | T01、T03；删除执行需 D3 | 大，先设计 | todo |
| T11 | readiness、备份恢复与发布验证 | F17 | T00；最终发布门槛依赖 P0 清零 | 中/环境相关 | todo |
| T12 | 持续验证、性能、真实 AI 评测 | F18、F19、F22 | 基建可从 T00 开始；最终验收依赖相关修复 | 大，分批 | todo |
| T13 | 按职责拆分与文档收口 | F20 | 相关行为回归通过 | 中 | todo |

大小表示相对工作量，不是交付日期；未确定部署环境和试用规模前不承诺工期。

推荐单线顺序：`T00 → T01 → T03 → T04 → T02 → T05 → T06 → T09 → T07 → T08 → T10 → T11 → T12 → T13`。

T00/T12 的测试脚手架、T11 的手册草案可在业务整改中逐步完成；这不是要求创建并行子代理。若测试库不可用，可继续代码、文档和不依赖数据库的验证，但相关任务保持 `verification_pending`。

## 3. 决策表：只拦住依赖决策的子项

| 决策 | 默认保留的当前规则 | 待确定内容 | 何时需要 |
| --- | --- | --- | --- |
| D1 余额不足 | 训练保存与扣课同事务、余额不足整体回滚 | 是否允许“记录已发生、权益待核销”；若允许，明确状态、补核销和撤销 | T05 新核销能力前；不阻塞现有并发修复 |
| D2 错绑纠正 | 已关联课程不可随意更换；不自动修数据 | 作废/冲正/重建方式，课程恢复、退款/补扣、理由与审计 | T05 纠正流程实现前 |
| D3 删除与保留 | 不自动删除真实客户/审计/备份 | 授权角色、保留期限、恢复期、审计最小保留与备份处理 | T10 清除能力前；不阻塞导出/预览 |
| D4 风险规则 | 不自动诊断或改计划；去掉无证据结论 | 专业触发条件、连续性、测量场景、阈值及人工建议动作 | T04 新专业规则启用前 |
| D5 上线验收目标 | 沿用宿主机 PostgreSQL/Nginx + Docker 后端 | 试用人数/并发、数据量、延迟目标、备份 RPO/RTO、真实 AI 预算 | T11 演练与 T12 容量/质量门槛定稿前 |

需要决策时，先给用户可审阅方案、影响对象、异常路径和推荐选项，再问一个具体问题。不能以整份计划尚有决策为由停掉所有独立工作。

## 4. 任务卡

### T00：建立可信基线与当前状态索引

目标：后续 AI 能知道“实现了什么、当前测过什么、什么还没验证”。

主要文件：`docs/project-execution-plan.md`、`docs/testing-standards.md`、`docs/architecture.md`、产品文档、requirements、package.json、生产配置。

执行：

1. 检查 HEAD、工作区、解释器、数据库连接和模型配置来源；只输出存在性/模式，不打印密码、Key、主机私有信息。
2. 建立模块状态表，区分代码实现、Mock 测试、浏览器验收、真实模型、部署验证；链接保留的历史日志。
3. 修正文档中默认编排开关、测试数据库与现行部署拓扑冲突；历史内容标为历史，不抹除。
4. 使用后端 `.venv`、独立测试 PostgreSQL，串行运行后端测试；运行前端 build 与现有 SSE 测试。连接设短超时，失败报告原因，不反复挂起。
5. 为后续任务保存可重现命令和环境版本，不把真实配置写入仓库。

验收：基线记录含 commit、日期、命令、通过/失败/未运行状态。数据库未连通时迁移检查只能说“模型无差异、历史未验证”。

### T01：修复跨客户关联与输入校验

目标：任何更新入口都不能将本人资源关联到其他康复师客户。

主要文件：`training/views.py`、`training/home_views.py`、`training/serializers.py`、`common/exceptions.py`；扩展核查其他业务 serializer/view/service。

执行：

1. 先补 F01/F02 反例：两名康复师、各一客户，甲修改自己的无排课记录/家庭训练并传乙客户。
2. 创建后客户字段设为不可更换，传入不同值明确拒绝；如允许同客户原值，保持兼容。不要静默将错误请求当成功。
3. 关联 queryset 按当前康复师收窄，服务层验证 owner/customer/source 一致；不得依赖前端隐藏字段。
4. 建立所有创建/更新/确认入口的关联矩阵，核查评估、计划、课时包、知识、任务、动作等，只有查实的缺口才修改。
5. 统一非法 customer_id、日期、枚举、分页边界的 400；不存在/越权使用项目约定，避免泄露其他客户存在性。
6. 设计只读一致性检查脚本，输出异常计数与受控引用；不修改现有数据。

验收：甲对乙的读写/改绑均失败，数据库无变化、无业务审计误记录；合法甲客户流程通过；`customer_id=abc` 为 400；接口文档同步。不得只测“读取别人记录失败”，漏掉“改自己记录的关联”。

### T02：登录与账号边界

主要文件：`accounts/views.py`、`accounts/serializers.py`、`accounts/tests.py`、`config/settings*.py`、前端 auth/http、通用代理示例。

执行：建立登录专用 CSRF 获取/校验流程；使用 enforce_csrf_checks 的实际客户端测试；补账号/IP 维度速率限制与恢复策略；账号创建/重置共用密码验证器。限流不能只存单进程全局变量。新规则尽量使用现有数据库/部署设施，先说明成本。

验收：缺失/错误 token 与非法 Origin 的登录被拒；合法登录、刷新恢复、登出通过；创建/重置都拒绝弱密码；短期超限返回 429 并能恢复；响应不泄露账号存在性或内部异常。若改 429，检查统一异常处理不会错误映射成 400。

### T03：正式训练记录无损与可追溯修订

主要文件：`training/models.py/serializers.py/services.py/views.py`、`ai/services/training_parser.py`、`training/batch_service.py`、`ai/services/domain_drafts.py`、前端训练/草稿组件和类型。

执行：

1. 列出模型→输入→草稿→确认→输出→修订→时间线→审计字段矩阵，贯通 `activity_type/quantity/unit`。
2. 明确 exercise 与 therapy/massage 的字段校验，不用组数/次数替代治疗数量，不自动推断未提供剂量。
3. 复用正式记录保存服务，避免单客户/批量/手动各一套字段映射。
4. 修订使用版本/更新时间条件校验，在事务内取真实 before 状态并审计；过期编辑返回 409 或项目统一冲突码。
5. 动作差异更新或完整保真替换二选一；先保护稳定引用与已有字段，不仅凭减少代码选择。

必测：按摩 1 次，治疗 2 次，训练 3×12，时长动作；分别经过手动、单客户 AI、批量确认，再 GET 和修订；缺省/空值/0/非法单位；两个旧版本并发保存；确认重复提交；扣课失败整体回滚。

验收：草稿与正式记录字段一致，修订后无静默丢字段，重复确认不新增记录/扣课；审计反映真实前后值。历史缺失字段只报告，不猜测补齐。

### T04：风险证据与知识检索

T04-A 风险：`ai/services/risk.py`、RiskAlert、相关接口/前端。

1. 添加旧 8→新 1、旧 1→新 8、8→8、缺值、非法范围、不同场景和重复触发用例。
2. 先修解释不实：只陈述确实计算出的证据；规则未确认时走人工核查，不输出伪造的连续性。
3. 规则和来源记录可追踪、去重；处理结果由康复师确认。新的专业阈值/行动依赖 D4，不让 AI 自行制定。

T04-B 知识：`knowledge/services.py/views.py/memory_service.py`、context builder。

1. 单独召回有效安全限制，再合并相关自由文本；定义明确的上下文容量和截断提示。
2. 统一 owner/customer/status/is_active/有效期过滤；错误组合不能进入客户回答。
3. 编辑内容使旧向量失效，索引与内容版本绑定；重建分批可重试，显示成功/失败/待处理数。
4. embedding 不可用时明确是有限上下文/检索降级，不伪装成已做语义检索。

验收：6 条以上知识时，较旧高重要安全限制不被最近 top-k 排除；停用/替代/过期知识不进入回答；编辑后不会继续用旧向量；客户边界通过；提示注入只被视为数据。先做正确性，不建设新的向量平台。

### T05：排课、完成与扣课的并发闭环

主要文件：`schedules/services.py/views.py`、`courses/services.py`、`rehab/views.py/services.py`、训练确认服务及相关测试。

分阶段执行：

1. 写出不变量：有效排课不重叠、完成记录唯一、取消不消费、完成与扣课原子、余额不负、计划容量不超、历史日期一致。
2. 选康复师维度事务锁或等价数据库方案，说明锁顺序；将关键判断放入锁内，用最新数据复核。
3. 双连接 PostgreSQL `TransactionTestCase` 覆盖跨计划同时排课、单节/批量竞争、取消/确认竞争、计划调整/确认竞争、重复确认、余额不足。
4. 已完成课程日期修改采用明确策略；默认拒绝破坏既有记录日期一致性的修改。
5. D1/D2 未确认前保留当前扣课/不可改绑规则，提供具体设计与原型，独立记录为 `design_pending`。不阻塞前四步修复。

验收：在可控制的 Barrier 时序下运行并发用例；重叠请求仅一个成功，完成后不能被旧取消请求覆盖，任何失败不会留下半条记录或半次扣课；锁超时返回可重试业务错误。SQLite 不替代此验收。

### T06：统一 AI 边界与中断恢复

主要文件：`ai/orchestration/`、`assistant_tasks/`、`conversations/`、`knowledge/`、`ai/services/preparation.py`、前端 assistant/conversations/knowledge API。

分阶段执行：

1. 生成入口矩阵并列实际调用方，区分主聊天、客户知识问答、备课、摘要/记忆提取、旧训练解析/确认。不得看见旧文件就直接删除。
2. 被使用入口转入统一图或兼容适配器；复用身份、Tool、草稿与输出清洗边界，保持旧 API 的兼容期限和明确错误。
3. 先给回复结果，再处理可延后的辅助评估；需要可靠后台执行时先定义持久任务和重启恢复语义，不能用“捕获异常”假装异步。
4. 定义 run/attempt 归属、开始/心跳/终止/超时状态。旧执行晚到不覆盖新状态；失效执行不创建可确认新草稿。
5. 将单次模型超时、总回合时间、SSE 时限和 stale 判定统一；UI 区分仍处理中、已完成但断线、确实失败，提供查结果入口。

验收：未绑客户不能读私有事实；跨客户恢复被拒；旧入口也不泄露内部引用/未经确认写入；断网/180 秒超时/worker 重启/旧执行晚返回/同 request_id 重试都不重复正式记录和扣课。真实 Nginx/ASGI 的首事件、心跳、终态在 T11 联调，Mock 不代替它。

### T07：今日工作与回访结果闭环

主要文件：PC/手机 Dashboard、`AuxiliaryServices.vue`、followups、首页聚合接口、customers/services。

执行：补今日课程、跨日待回填、今日/逾期回访、明确已安排的待复评、待确认草稿；每项可定位具体客户/资源。复评到期不能由 AI 猜日期。手机超过 5 节要有明确剩余数量/查看更多。

回访完成需输入真实结果，跳过填写原因，需继续处理时显式建下一项；后端状态与结果校验、事务、审计同步。客户更新、家庭训练父子写入等已确认缺口补原子性。不要只让前端刷新数字而未改变领域状态。

验收：用一天 6 节课、昨天漏回填、逾期回访、已安排复评、待确认草稿的合成场景，逐项操作后首页/详情状态一致；取消/跳过不伪装完成；失败保留输入并可重试；两端有相同业务含义。

### T08：补齐家庭训练、动作与别称维护

执行子项可独立交付：

- 家庭训练：现有计划编辑、动作/剂量/频率/注意事项展示、一键复制客户版完整文案，复制前可核对。
- 动作库：官方只读，个人可维护；常用选择器复用，别名与正式名边界明确；不增加视频生产工作流。
- 客户别称：详情中新增/编辑/停用，复用目录归一化与歧义检测，不因别称唯一就跨康复师匹配。

验收：编辑与重新读取一致；复制含完整训练量和注意事项，不带内部 ID；官方动作不能被普通用户改；别称与其他客户正式名冲突不自动绑定；手机可完成主要操作。

### T09：客户切换与异步状态隔离

主要文件：`CustomerDetailView.vue`、`AuxiliaryServices.vue`、相关子组件、layouts/router；按需同查训练/评估详情。

执行：路由客户由响应式来源获取；改变客户时清状态、更新子组件、取消或忽略旧请求；保存捕获稳定目标，不读取已变化的全局选择。未保存内容的处理可用现有退出保护，不自动保存到另一客户。

验收：浏览器/自动化真实模拟 A 请求慢、切 B 后 B 先返回，最终内容全是 B；任何写请求的目标与画面客户一致；前进/后退、直接刷新、编辑中切换均覆盖。API 正确并不能替代此项验收。

### T10：客户导出与数据生命周期

先交付设计：资源清单、归属链、派生内容、导出字段、保留策略、删除影响预览、审计、备份边界；不将数据库 CASCADE 当产品删除策略。

第一批可实施：有权限的客户级结构化导出和可读报告；默认脱敏，按需求授权完整信息；导出访问可追踪。删除预览只读列出范围，不执行清除。

D3 明确后再实施软删/脱敏/清除，防止对话摘要、Episode、Memory、向量继续被检索。正式审计是否保留以及保留什么，以已确认方案为准。

验收：甲不能导出乙，导出能核对训练/评估/课程/流水；删除预览无副作用；确认删除后所有读取入口遵循生命周期；真实数据操作另有明确授权。不得为满足“删除”测试直接清生产。

### T11：运行状态、恢复与发布

执行：保留 liveness，补不泄密且短超时的 readiness；数据库不可用与模型不可用分别呈现。补通用备份、恢复、迁移预检、前后端版本、回滚步骤、SSE 代理检查，真实主机信息仍放忽略目录。

在隔离环境演练数据库恢复并核对记录/流水；验证迁移失败停止发布，前端子路径刷新、Session/CSRF、静态资源与 Nginx/ASGI SSE。D5 确定 RPO/RTO/目标环境后填实测，不宣称“有 pg_dump 命令即备份可用”。

验收：数据库断开 readiness 失败且业务错误可理解，liveness 仍表进程；恢复后数据与关键约束可核对；发布/回滚操作有执行记录。未取得生产操作授权时交付隔离演练成果，不自动部署。

### T12：持续验证、性能和真实 AI 评测

三部分分批做：

1. **可重复构建**：选择与当前 Python/生产镜像兼容的依赖锁定方式；干净环境安装；统一前后端 test 命令与 CI/本地等价脚本。后端 PostgreSQL + pgvector 独立测试服务，测试串行；普通 CI 不用真实 Key。
2. **业务 E2E 与性能**：覆盖建客户→首评→计划→排课→草稿→确认→扣课→时间线→回访；加入权限、路由竞态、刷新恢复、重复提交。会话列表改摘要，消息/时间线分页；消除已定位 N+1，记录改前改后 SQL 数、载荷、p95。按慢网络测 chunk 和关键加载，不为消警告盲拆。
3. **真实 AI 质量**：版本化合成样本至少覆盖姓名歧义、多客户、查询与写入区分、治疗数量、缺训练效果、提示注入、过期知识、网络失败。记录身份/意图正确率、草稿字段保真、人工修订量、首进度/总延迟、调用次数、tokens/成本、降级原因。D5 确定预算和阈值后少量真实评测，不在常规测试中自动调用真实模型。

验收：干净环境可按文档运行；危险行为用例硬性零容忍（越权、未确认写入、重复扣课）；性能和 AI 质量有样本/版本/阈值/实测证据。测试数不是唯一成功标准。

### T13：按职责拆分与文档收口

在相关回归通过后，把 nodes 按身份/查询/草稿/恢复职责划分；前端 AssistantView 提取聊天状态、历史加载、业务卡片动作等稳定模块。每次小步保持公开契约，不能以降低行数为唯一目标。

同步当前产品状态表、架构、接口、数据库 SQL、测试和本计划。说明兼容入口、待定决策、未验收环境。删除旧代码前证明无调用方，旧业务记录不因清理代码而删除。

验收：行为回归不退化；新 AI 读索引能找到当前事实，不会按已废弃客户疗程/旧部署方案重做；所有状态有证据链接。

## 5. 执行命令与验证约束

后端在 `retrue-server` 目录，确认连接的是开发/测试环境后运行：

```powershell
$env:PGCONNECT_TIMEOUT = '5'
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test apps.training apps.courses apps.schedules --keepdb --noinput
```

按任务替换测试模块；共享 `test_retrue` 时禁止并发跑多个 Django 测试进程。最终集成验收再跑全量，不在仓库根目录运行而误认 `Ran 0 tests` 通过。不得把本地真实模型配置当测试前提，显式 Mock。

前端在 `retrue-web`：

```powershell
node --test tests/sse.test.mjs
npm run build
```

E2E 框架在 T12 引入并记录真实命令；现在不提供仓库尚不存在的 `npm test` 或 Playwright 命令。数据库结构变化的 migration 与 SQL 同步，仅在授权的开发/测试库应用。

## 6. 完成定义与分阶段门槛

单项完成必须具备：问题证据→修复/设计→相关验证→文档/类型同步→风险与回退说明。若只完成实现，写 `verification_pending`，不能写 done。

- **门槛 G1：数据正确性**：F01/F02 越权被拒、F03 字段无损、F04 风险解释正确、F11 安全知识不会被简单 top-k 漏掉；相关 PostgreSQL 回归通过。
- **门槛 G2：稳定试用**：认证、课程并发、AI 中断、客户切换、回访完成场景通过；真实代理 SSE 有验证；错误不会要求用户重复操作而产生重复记录。
- **门槛 G3：可运维交付**：独立构建/CI、数据导出、备份恢复与回滚证据、试用目标和 AI 质量基线齐备。未决删除/欠费/纠正能力明确标出范围，不能隐式扩展上线承诺。

P2 不必全部完成才试用；但不能用大量 P2 页面优化掩盖 P0 未关闭。

## 7. 后续 AI 启动指令

可直接复制：

```text
请执行 docs/plans/2026-09-08-project-remediation-plan.md。
先读 AGENT.md 和配套整体评估，核对当前 HEAD、工作区与已完成变更。
从 T00 建立当前验证基线，然后按计划修复 T01，继续处理不依赖未决业务规则的任务。
每个任务先复现问题，再最小修复，按需同步测试、前后端类型、API、migration、SQL 和文档。
保留现有课程主链、单体架构、LangGraph 和 AI 草稿人工确认；不要自行增加新业务规则。
如数据库或真实环境不可用，继续可独立完成的工作，将相关验证标记为 verification_pending。
涉及 D1-D5 的子项先提供具体可审阅方案；不要因为单个决策停掉其他独立工作。
不清理真实数据、不自动生产迁移或部署、不提交私有配置、不自动向客户发消息。
每完成一个可验证变更集，在本计划交接区写清结果、证据、限制和下一项。
```

指定单项时可用：“只执行 T03，其他任务不改；先核实 T01 的归属修复前置条件”。

## 8. 交接记录模板

后续每次执行追加，任务索引同时更新，历史不覆盖：

```text
日期 / 执行任务：
代码基线 / 当前变更集：
状态：todo | in_progress | implemented | verification_pending | design_pending | done
已解决的 F 编号：
修改文件与业务结果：
新增或更新的设计决定：
验证命令与结果（含数据库/模型/浏览器类型）：
没有验证的部分及原因：
迁移、历史数据影响与回退方式：
下一项及前置条件：
```

初始交接（2026-09-08）：仅评估与计划完成。`manage.py check`、前端构建、4 项 SSE 测试通过；迁移检查显示模型无差异但数据库历史连接超时；全量后端测试未完成。局部复现的坏行为详见评估第 6 节，所有整改任务尚未完成。

交接 T00（2026-09-08，执行批 1）：
代码基线 / 变更集：HEAD `7d4c369`；无业务代码改动，仅文档漂移修正。
状态：implemented（验证部分未全量）
已解决的 F 编号：F20 文档漂移中的「默认编排开关」「测试库写法」「部署拓扑」三项。
修改文件与业务结果：`docs/architecture.md`（编排默认开启，链接评估）、`docs/testing-standards.md`（独立测试 PostgreSQL，旧 Compose 写法标为历史）、`docs/Retrue_项目设计文档_V1.0.md`（31 节早期容器化方案标为历史并指 README/DEPLOY）。未删除历史内容。
验证命令与结果：`manage.py check` 0 issues；`makemigrations --check --dry-run` No changes（本次数据库已连通）；本机 5433 开发库与独立测试库可用；`apps.training apps.schedules` 69 测试 OK；`apps.training apps.courses apps.rehab` 50 测试 OK；前端 `npm run build` 通过、SSE 4/4 通过。环境版本：Python 3.14.5（retrue-server/.venv），Django 6.0.8。
没有验证的部分及原因：全量后端测试（所有 app）因耗时未跑完，批次内逐模块回归替代；真实浏览器/真实 AI 未验证。
迁移、历史数据影响与回退方式：无数据改动。
下一项及前置条件：T01（已在本批一并完成，见下条）。

交接 T01（2026-09-08，执行批 1）：
代码基线 / 变更集：基于 `7d4c369`；仅 `apps/training/views.py`、`apps/training/home_views.py`、`apps/training/tests.py`、`docs/api/training.md`。
状态：implemented
已解决的 F 编号：F01（训练记录修订改绑他人客户）、F02（家庭训练修改改绑他人客户）、F08 中「非法 customer_id 返回 500」部分。
修改文件与业务结果：
- `training/views.py`：新增 `_parse_customer_id`，列表/时间线非法 `customer_id`（abc、负数）返回 400；PUT 修订校验请求中 customer 与记录原值一致才放行，不同值返回 400「正式训练记录不能更换客户」，并把 customer 从写数据中剔除，杜绝无排课记录被改绑。
- `training/home_views.py`：列表复用 `_parse_customer_id`；PUT 更新同样拒绝改绑客户，仅允许原值兼容。
- `apps/training/tests.py`：新增 7 个回归用例（记录/家庭训练不能改绑他人客户、同客户值兼容、非法 customer_id 400）。
- `docs/api/training.md`：同步修订/更新接口「客户不可更换」说明。
新增或更新的设计决定：创建后 customer 字段不可更换；错绑纠正按 T01 结论保留为「走受控流程」，不做自动改绑。
验证命令与结果：`apps.training` 29 测试 OK（含新增 7 例）；`apps.training apps.courses apps.rehab` 50 测试 OK；lint 无错误。
没有验证的部分及原因：跨康复师只读行为既有测试已覆盖；浏览器端真实改绑操作未做（API 层证据充分）；其他业务 app 的归属矩阵由代码盘点确认无同型缺口（assessments/rehab/followups/knowledge/assistant_tasks/schedules 均已封堵或丢弃请求 customer）。
迁移、历史数据影响与回退方式：无数据改动；若需回退还原三个源码文件即可。
下一项及前置条件：T03（训练字段无损与可追溯修订）。

交接 T03（2026-09-09，执行批 1 续）：
代码基线 / 变更集：基于 `7d4c369` + T01 已改文件。
状态：implemented（F03 字段贯通 + F08 修订冲突/审计；两个既有失败与本次无关）
已解决的 F 编号：F03（activity_type/quantity/unit 贯通正式保存与输出）、F08 的「修订无版本冲突、审计前后值不全」子项。
修改文件与业务结果：
- `training/serializers.py`：TrainingExerciseSerializer 增 activity_type/quantity/unit；TrainingRecordRevisionSerializer 增 expected_updated_at（可选乐观锁）。
- `training/services.py`：record_to_dict 审计快照补 activity_type/quantity/unit/note；新增 get_record_for_update（行锁 of=self）。
- `training/views.py`：PUT 修订改在事务内 get_record_for_update 锁行 + 锁内取 before + 支持 expected_updated_at 不匹配返回 409。
- `training/home_views.py`、`training/views.py`：列表/时间线非法 customer_id 400（T01 配套）。
- `ai/serializers.py`：ConfirmedExerciseSerializer 补 activity_type（枚举）/quantity/unit，修 confirm 入口静默丢字段。
- `ai/services/training_parser.py`：confirm_training_draft 创建正式动作写入 activity_type/quantity/unit。
- `ai/providers/mock.py`：_parse_single_segment 识别按摩/治疗 massage|therapy + quantity/unit，不再套 sets/reps；修正 unit 正则分组。
- `ai/prompts/parse_training_text.txt`：单客户解析提示补活动类型/数量规则。
- 前端：`TrainingRecordEditView.vue` 修订携带 expected_updated_at 并识别 409 不覆盖；`types/api.ts` 增 ApiCode.CONFLICT；`api/training.ts` TrainingRecordForm 增 expected_updated_at。
- 文档：`docs/api/training.md`（修订 409 与动作字段）、`docs/api/ai.md`（确认 exercises 活动类型字段）。
新增测试：mock 按摩/治疗解析、手动创建/修订保留 massage 字段、AI 确认草稿正式记录字段无损 + GET 读回、修订旧 updated_at 返回 409。
新增或更新的设计决定：修订采用「行锁 + 可选 expected_updated_at 乐观锁」；未带期望版本时保持旧行为兼容；版本冲突用统一码 409。
验证命令与结果：`apps.training apps.ai` 171 测试中 169 通过，2 失败为基线既有（`IntentModelTests` 意图分类断言，intent.py/mock.classify_intent 非本批改动，已 stash 验证基线同样失败）；`apps.training.tests.TrainingApiTests` 15 OK；`apps.ai.providers.test_mock` OK；前端 `vue-tsc -b && vite build` 通过；lint 无错误。
没有验证的部分及原因：真实浏览器并发修订 UI 未做人工 E2E（后端 API 层证据充分）；批量确认场景通过既有 batch 测试（confirm_item_record 复用 confirm_training_draft，字段已贯通）；无 migration 改动。
迁移、历史数据影响与回退方式：无数据改动/无 migration。历史丢失字段只报告不猜测补齐，符合 T03 验收。
下一项及前置条件：T04（风险事实与知识检索）。

交接 T04（2026-09-09，执行批 1 续）：
代码基线 / 变更集：基于 `7d4c369` + 本计划前几批改动。
状态：implemented
已解决的 F 编号：F04（风险提醒伪造“连续未明显改善”）、F11（知识生命周期过滤与旧向量失效、安全限制被 top-k 排除）。
修改文件与业务结果：
- T04-A 风险（`apps/ai/services/risk.py`、`apps/ai/models.py`、`migrations/0008_*`、`docs/database/risk_alerts.sql`、`docs/api/ai.md`、`apps/ai/test_risk.py`）：
  - `RiskAlert` 新增 `rule_code`（`nrs_high_v1`）与组合索引，用于追踪与去重。
  - 规则改为：最近 3 条至少 2 条合法 NRS(0-10) 且最高 ≥6 才触发；**只陈述可计算证据**（评分序列、最高、最近一次、缺值/越界计数），不再输出“连续未明显改善”类无证据结论；最近一次低于 6（较历史高位下降）降为 `medium + review`，由康复师人工复核；同规则未确认提醒去重更新而非重复创建。
  - 新增 7 个规则用例（8→8、8→1、1→8、缺值、越界、去重、低于阈值）。
- T04-B 知识（`apps/knowledge/services.py`、`views.py`、`memory_service.py`、`memory_evaluator.py`、`tests.py`、`test_services.py`、`docs/api/knowledge.md`、前端 `KnowledgeView.vue`/`MobileKnowledgeView.vue`/`api/knowledge.ts`/`types/api.ts`）：
  - 统一生命周期过滤 helper：`is_active=True + status=active + effective_from/effective_to` 有效期，知识检索、索引重建、长期记忆上下文、候选评估四处一致。
  - `search_knowledge` 改为「安全/高重要独立召回（上限 8）+ 相似/最近文本补充」，安全限制不再被相似度 top-k 或最近 top-k 排除；返回项带 `matched`（vector/keyword）。
  - 编辑内容、停用、删除时清空 embedding，重建索引按新内容向量化，避免命中旧向量。
  - 索引重建接口返回 `indexed/pending/embedding_available`；RAG 响应加 `retrieval_mode`；embedding 不可用时如实标注 `keyword`，前端展示“有限检索”提示，不伪装语义检索。
新增或更新的设计决定：风险规则保留“最高≥6 且 ≥2 条评分”触发；明显下降走人工复核而非自动暂停。新医学阈值与建议动作仍待 D4，本次未新增专业阈值。
验证命令与结果：`apps.ai` 146 测试仅 2 基线既有失败（IntentModelTests，属并发方 intent 域，非本批改动，已 stash 验证基线同样失败）；`apps.knowledge` 26 测试 OK（含新增 8 例）；`apps.conversations apps.ai.test_risk apps.knowledge.test_services` 19+7 OK；前端 `vue-tsc -b && vite build` 通过；lint 无错误。
没有验证的部分及原因：embedding 真实服务/真实向量相似度未调用（离线 Fake 验证结构）；重建“分批可重试”在嵌入服务单次失败时整批返回 0 而非逐条重试，接口已报告 pending 可再次触发；前端仅验证有限检索提示逻辑，未做浏览器人工 E2E。
迁移、历史数据影响与回退方式：`ai.0008_riskalert_rule_code_and_more` 已生成（新增可空默认列），SQL 参考文档已同步；未在生产库执行。回退可删除该列/迁移。
下一项及前置条件：T02（登录与账号边界，无额外前置）或按推荐顺序继续 T05 前可先处理 T02。计划推荐顺序为 T04→T02→T05。

交接 T02（2026-09-09，执行批 2）：
代码基线 / 变更集：基于 `7d4c369` + 本计划前几批改动。
状态：implemented
已解决的 F 编号：F05（登录缺独立 CSRF、无登录限流、账号创建/重置密码验证不完整）。
修改文件与业务结果：
- 登录 CSRF（已按确认方案「新增 CSRF 获取端点 + 登录强制校验」）：
  - `config/settings.py` 增加 `CSRF_FAILURE_VIEW=apps.accounts.views.csrf_failure_json`。
  - `accounts/views.py` 新增 `CsrfTokenView`（GET /api/auth/csrf/，ensure_csrf_cookie 种 Cookie + 返回 token）、`csrf_failure_json`（统一 {code:403,message,data:{error_code:csrf_failed}}）。
  - `LoginView.post` 在 DRF as_view 默认豁免 CSRF 的情况下，通过手动调用 `CsrfViewMiddleware.process_view` 强制校验（尊重测试客户端 `_dont_enforce_csrf_checks`），缺失/错误 token 或非法 Origin 返回 403。
  - 前端 `api/auth.ts` 增 `apiGetCsrfToken`；`LoginView.vue` 挂载与提交前先 GET /csrf/ 种 Cookie，提交自动携带 `X-CSRFToken`。
- 登录限流（已按确认方案「DatabaseCache + 建表」）：
  - `config/settings.py` 配置 `CACHES`（默认 DatabaseCache，`retrue_cache`），新增 `LOGIN_THROTTLE_*` 阈值/窗口环境变量。
  - 新增 `apps/accounts/login_throttle.py`：账号（username 小写）与来源 IP 双维度计数，达阈值返回 429（`error_code=login_throttled`），窗口过期自动恢复，成功登录清除计数；计数在 PostgreSQL DatabaseCache 上跨进程共享。
  - migration `accounts/0003_retrue_cache.py` 建 cache 表 + `docs/database/retrue_cache.sql` 文档。
- 密码验证：`accounts/serializers.py` 账号创建与密码重置统一走 `_validate_password_strength`（Django `validate_password`，含长度/常见弱口令/纯数字/与账号相似度）。
- 429 语义：`apps/common/response.py` 增 `CODE_TOO_MANY_REQUESTS=429`；`apps/common/exceptions.py` 将 DRF `Throttled` 映射为 429，避免被统一异常处理误映射成 400。
- 测试：`apps/accounts/tests.py` 新增 6 个用例（CSRF 端点种 Cookie、enforce_csrf_checks 下缺 token 被拒、带 token 成功、CSRF 失败统一 JSON、连续失败 429 且恢复后可登录、创建与重置拒绝弱密码）。
- 文档：`docs/api/auth.md` 增 CSRF 端点、登录 403/429、限流语义；`docs/database/retrue_cache.sql` 新增。
新增或更新的设计决定：登录失败采用“短期失败限流 + 自动恢复”，不做永久锁号；登录接口单独强制 CSRF，不因 DRF 视图默认豁免而暴露。
验证命令与结果：`apps.accounts apps.common apps.knowledge apps.conversations apps.ai.test_risk` 64 测试 OK；`apps.accounts` 19 测试 OK（含新 6 例）；`makemigrations --check` No changes；前端 `vue-tsc -b && vite build` 通过；lint 无错误。
没有验证的部分及原因：非法 Origin（Referer/Origin 不匹配）在 HTTPS 下由 Django CSRF 中间件兜底，未用真实跨站浏览器验证；限流“恢复”以手动清除计数模拟窗口过期；登录限流依赖 DatabaseCache 表已随 migration 建立，生产部署需确认 cache 表迁移成功。
迁移、历史数据影响与回退方式：新增 `accounts.0003_retrue_cache`（cache 表）与 `ai.0008`（前批）。cache 表非业务表，回退仅影响登录限流；无业务数据改动。
下一项及前置条件：T05（排课/完成/扣课并发与纠正规则）——本任务较大且包含 D1/D2 设计子项，建议下一批单独推进。
