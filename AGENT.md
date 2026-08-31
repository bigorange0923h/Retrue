# Retrue 开发协作规范

本文件定义 Retrue 的通用开发约束。开始实现前先阅读本文件，并按需查阅详细规范：

- [产品设计文档 V1.0](docs/Retrue_项目设计文档_V1.0.md)：产品范围、业务闭环、领域规则与技术选型的权威来源。
- [项目执行计划](docs/project-execution-plan.md)：阶段目标、交付物、验收标准与进度状态。
- [后端、API 与数据库规范](docs/backend-development-standards.md)
- [前端开发规范](docs/frontend-development-standards.md)

## 必须遵守

1. 使用中文编写用户可见文案、注释和文档；代码标识符使用清晰的英文。
2. 后端 Python 命令统一使用 `retrue-server/.venv`；Windows 下解释器为
   `retrue-server\\.venv\\Scripts\\python.exe`。禁止在仓库根目录新建或使用 `.venv`。
3. 每个公共类、函数、接口与复杂业务逻辑都必须有简明注释或文档字符串，说明职责、参数、返回值与关键约束。
4. API 响应必须使用统一信封结构，不得直接返回裸数据。
5. 数据库结构变更必须同时提交 Django migration 与 `docs/database/` 下相应的 SQL 文件。
6. AI 只生成草稿；任何 AI 解析结果必须经康复师确认后才能写入正式业务数据。
7. 涉及客户健康信息、手机号和 AI Key 的内容不得写死在代码或提交到 Git；使用 `.env` 配置。
8. 每次修改应保持前后端类型、接口字段和迁移文件同步，并运行相关校验或构建。
9. 新增或变更接口时，必须同步更新后端实现、前端 API 类型和 `docs/api/` 接口文档。
10. 新增或变更数据表时，必须同步提交 Django Model、migration 与 `docs/database/` 对应 SQL 文件。
11. 实现业务功能前必须核对产品设计文档；设计文档未明确的重大业务规则、数据字段或流程，不得自行假定，应先补充设计或确认。
12. 所有 AI 提示词统一以独立文件管理（`retrue-server/apps/ai/prompts/` 下 `*.txt`），通过 `load_prompt`/`render_prompt` 加载；禁止将提示词硬编码在业务或 provider 代码中。提示词中的动态内容用 `{占位符}` 表示，由调用方在渲染时注入。
13. 后端业务表禁止使用数据库物理外键。Django 关联字段必须设置 `db_constraint=False`，关联对象的存在性、康复师数据归属和删除/置空/保护语义必须由 serializer、service 与 Django ORM 的 `on_delete` 业务规则校验和执行；不得依赖 SQL `FOREIGN KEY`、`REFERENCES` 或数据库级级联。
14. 目录型初始化数据（如课程类型、课程计划模板）统一维护到 `docs/database/seed_*.sql`，按康复师用户名通过 `tb_users` 关联取 `therapist_id`，且必须**幂等**（`INSERT ... SELECT ... WHERE NOT EXISTS(...)`），重复执行不产生重复数据。种子 SQL 是初始化数据的唯一来源，不额外维护等价的 Django management command；需要初始化数据时直接执行对应 `seed_*.sql` 即可，使用前先查阅 `docs/database/README.md` 的种子数据约定。

## 补充协作文件

- [系统架构](docs/architecture.md)
- [接口文档约定](docs/api/README.md)
- [数据库文档约定](docs/database/README.md)
- [测试规范](docs/testing-standards.md)
- [贡献指南](CONTRIBUTING.md)

## 统一 API 响应

所有业务接口成功或失败均返回以下 JSON 外层结构：

```json
{
  "code": 200,
  "message": "成功的消息",
  "data": null
}
```

具体状态码、分页与错误格式见详细规范。
