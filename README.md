# Retrue｜运动康复智能工作台

Retrue 是一个面向运动康复师的单体 Web 应用，用于把日常的客户管理、课程安排、训练记录与 AI 辅助整理到同一条可追溯的工作流中。

它关注的不是让模型替代专业判断，而是让康复师更快完成记录、备课与复盘：AI 只生成待确认的草稿，正式业务记录始终由康复师审核后写入。

> 这是一个持续迭代中的个人项目，不是医疗诊断或治疗建议系统。请勿在公开环境中导入真实客户健康信息。

## 为什么做这个项目

运动康复的日常工作常在课表、客户信息、训练笔记和后续备课之间来回切换。Retrue 围绕一条明确的业务闭环设计：

```text
今日课程 → 记录训练 → AI 整理草稿 → 人工确认 → 客户时间线 → 下次备课
```

在此基础上，课程计划、计划内课程、具体排期与正式训练记录保持关联，减少“已上课但记录和课时状态不同步”的问题。

## 主要能力

| 场景 | 当前能力 |
| --- | --- |
| 客户与评估 | 客户档案、首次评估与复评草稿/完成状态、客户时间线与数据隔离。 |
| 课程与课表 | 课程计划、课程模板、批量排课预览与确认、时间冲突校验、课程状态与课时流水。 |
| 训练记录 | 手动录入训练内容；正式保存后关联课程完成状态，并保留可追溯的记录。 |
| AI 工作台 | 训练补记、客户查询、专业问答、评估/随访草稿等统一任务入口，支持进度事件和中断后继续处理。 |
| 安全边界 | AI 输出先进入草稿或等待确认状态；身份不确定时要求选择客户；正式写入、权限和审计由后端领域服务控制。 |
| 知识与动作 | 客户私有知识库、动作库与家庭训练等业务模块。 |
| 日常交付 | 历史未补记课程、待确认草稿与回访待办；家庭训练编辑及完整文案复制；动作与客户别称维护。 |
| 数据管理 | 按当前康复师权限导出客户正式记录、查看删除影响预览；删除执行规则尚待确认。 |

## 核心设计取舍

- **人工确认优先**：模型不直接修改正式训练记录、评估、课时或风险处理结果。
- **先校验身份和权限，再读取上下文**：客户识别不明确时不自动猜测，也不提前暴露客户资料。
- **业务状态由服务端维护**：前端展示不决定课程是否完成、课时是否扣减或记录是否可写入。
- **单体优先**：V1 使用 Django 单体和 PostgreSQL，优先验证业务闭环，不预建微服务、消息队列或 Redis 等额外基础设施。

详细的业务规则与边界见 [产品设计文档](docs/Retrue_项目设计文档_V1.0.md)；课程计划到训练记录的关联关系见 [系统架构](docs/architecture.md)。

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Element Plus
- 后端：Django、Django REST Framework、Pydantic
- 数据库：PostgreSQL + pgvector
- AI 编排：LangGraph；模型服务通过配置切换，默认可使用 mock provider 本地开发
- 部署：前端静态文件由 Nginx 提供；Docker 运行 Django ASGI 后端，PostgreSQL 保持在宿主机

## 架构概览

```text
Vue 3 Web
    │ REST API / SSE
    ▼
Django + DRF
    ├── 客户、评估、课程、训练与审计等领域模块
    ├── LangGraph AI 编排（草稿与等待确认）
    └── Django Admin
    │
    ▼
PostgreSQL + pgvector
```

```text
RehabPlan → RehabPlanCourse → CourseSession → TrainingRecord
客户计划     计划内课程          具体排期          正式训练记录
```

## 快速开始（本地开发）

### 前置条件

- Python 3.12+（项目依赖 Django 5.2+）
- Node.js（建议使用当前 LTS）
- 可连接的 PostgreSQL 数据库，并启用 `pgvector` 扩展

### 1. 配置后端环境

在 `retrue-server` 下复制环境变量示例并填入本地数据库信息。请勿提交实际 `.env` 文件或任何模型密钥。

```powershell
cd retrue-server
Copy-Item .env.example .env
```

使用项目的虚拟环境安装依赖并执行迁移：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe manage.py migrate
```

若只做不接入真实模型的本地演示，请在 `retrue-server/.env` 中显式加入 `AI_CONFIG_FILE=`，以禁用默认 YAML 模型配置并使用示例文件中的 `AI_PROVIDER=mock`。接入真实模型前，再按 `ai_config.yaml` 和环境变量配置对应密钥。

可选：只为本地演示创建示例数据。该命令会创建固定的开发账号；不要在联网或生产环境执行。

```powershell
.venv\Scripts\python.exe manage.py init_demo_data
```

启动后端：

```powershell
.venv\Scripts\python.exe manage.py runserver
```

健康检查地址：`http://127.0.0.1:8000/api/health/`

业务依赖就绪检查：`http://127.0.0.1:8000/api/readiness/`。它检查数据库、迁移、登录缓存表、vector 扩展和模型配置；不会调用真实模型，200 不代表真实模型或生产链路已验收。

普通回复中的记忆候选评估会持久排队。开发时可手动消费；部署时需配置定时执行：

```powershell
.venv\Scripts\python.exe manage.py process_auxiliary_tasks --limit 20
```

该命令只生成待审核候选，同一来源不重复排队，失败最多重试三次。没有配置消费命令时，普通对话仍可回复，但辅助候选不会自动生成。

### 2. 启动前端

另开一个终端：

```powershell
cd retrue-web
npm ci
npm run dev
```

按终端输出的本地地址打开应用（通常是 `http://localhost:5173`）。按上一步启用 mock provider 后，无需真实模型密钥也可以浏览本地演示流程。

### 3. 独立验证

前端测试使用 Node.js 24：`npm test`；类型检查和生产构建：`npm run build`。

仓库根目录的 `scripts/verify.ps1` 会创建随机临时 pgvector 容器，在独立测试库串行运行后端检查及全部测试，再测试和构建前端，最后清理该容器。需要 Docker、现有项目虚拟环境和已安装的前端依赖；不连接业务数据库。

```powershell
.\scripts\verify.ps1 -PythonPath "$PWD\retrue-server\.venv\Scripts\python.exe"
```

课程目录通过 [seed_rehab_catalog.sql](docs/database/seed_rehab_catalog.sql) 初始化。完整执行前确认目标用户名；账号缺失或同账号目录重名会报错回滚，锁等待最多 10 秒。脚本不会更新已有目录项，也不会清理历史数据。

当前实现和验收限制见 [2026-10-04 收尾记录](docs/plans/2026-10-04-remediation-verification.md)。内置语音功能不在实现范围内。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [产品设计文档](docs/Retrue_项目设计文档_V1.0.md) | 产品定位、业务规则、AI 边界与数据模型。 |
| [系统架构](docs/architecture.md) | V1 架构、模块职责、课程闭环和 AI 数据流。 |
| [API 文档](docs/api/README.md) | 接口文档约定及各模块 API。 |
| [数据库文档](docs/database/README.md) | 表结构、迁移和初始化数据约定。 |
| [部署说明](DEPLOY.md) | 宿主机 PostgreSQL/Nginx 与 Django 容器的发布流程。 |
| [贡献指南](CONTRIBUTING.md) | 协作前提与提交前检查。 |

## 项目结构

```text
.
├── retrue-web/       # Vue 前端
├── retrue-server/    # Django 后端与 AI 编排
├── docs/             # 产品、架构、API 与数据库文档
├── DEPLOY.md         # 生产部署说明
└── AGENT.md          # 代码与数据协作约束
```

## 演示素材

仓库暂未放入产品截图或在线演示链接。若准备公开展示，建议只补充 3 张使用**脱敏演示数据**的截图：

1. 今日工作台：展示课程与待办如何汇总；
2. AI 草稿确认：展示“生成草稿 → 康复师确认 → 正式记录”的边界；
3. 客户详情或课表：展示时间线/计划与排课的关联。

截图不应包含真实姓名、手机号、健康资料、访问地址或 API Key。素材准备好后可放入 `docs/images/`，再在本节插入并补充图注。

## 贡献与安全

欢迎通过 Issue 或 Pull Request 讨论改进。在提交前请特别确认：

- 不包含 `.env`、密钥、真实客户数据、部署地址或构建产物；
- AI 相关改动仍保留“草稿 → 人工确认 → 正式写入”的边界；
- 接口、数据表变更同步更新对应前后端代码与文档；
- 至少运行与改动相关的后端检查/测试和前端构建。

具体约定见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [AGENT.md](AGENT.md)。
