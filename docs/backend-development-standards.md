# Retrue 后端、API 与数据库开发规范

## 1. 后端规范（Django / DRF）

### 1.1 模块与分层

- 按业务域放入 `retrue-server/apps/`，例如客户在 `apps/customers/`、训练在 `apps/training/`。
- View 仅负责鉴权、请求校验、调用 service 和输出响应；不得堆放复杂业务逻辑。
- 业务规则放在 `services/`；序列化与输入输出校验放在 `serializers.py` 或 `schemas/`。
- 模型只承载数据关系、字段约束和紧密相关的简单行为。
- AI 供应商调用只能经 `apps/ai/services/` 与 provider 抽象层，不允许业务模块直接依赖具体模型 SDK。

### 1.2 注释、类型与命名

- 每个公共类和函数必须写 Python docstring，说明职责、参数、返回值和异常或业务限制。
- 非直观的判断、医疗业务规则、权限规则和审计逻辑必须在代码附近使用中文注释说明原因。
- 使用 `snake_case` 命名函数、变量和文件；类使用 `PascalCase`；常量使用 `UPPER_SNAKE_CASE`。
- 类型标注应覆盖函数参数和返回值；复杂数据结构使用 Pydantic 或明确的类型定义。

### 1.3 API 响应与错误

所有接口统一返回：

```json
{
  "code": 200,
  "message": "成功的消息",
  "data": null
}
```

- `code`：业务状态码。成功使用 `200`；参数错误使用 `400`；未登录 `401`；无权限 `403`；不存在 `404`；服务器错误 `500`。
- `message`：面向前端的中文短消息，不暴露内部堆栈、SQL 或敏感信息。
- `data`：成功时为对象、数组或 `null`；失败时可为 `null` 或结构化字段错误。
- 分页数据放入 `data`：`{ "items": [], "page": 1, "page_size": 20, "total": 0 }`。
- 使用统一响应工具与统一异常处理，不在每个 View 中手写不同格式的 `Response`。

### 1.4 数据安全与业务边界

- API 默认要求身份认证，并按康复师隔离客户数据。
- 客户列表默认返回脱敏手机号；完整手机号仅在受控的资料编辑场景返回。
- 密钥、密码和真实客户数据仅能来自环境变量或受控数据库，禁止提交到仓库、日志和异常消息。
- AI 原始输入、AI 草稿与最终确认数据需分开保存；AI 不得自动修改正式训练、评估或阶段数据。
- 所有正式记录变更必须可追溯，保留修改前后数据、修改原因、操作人和时间。
- 业务表关联采用业务规则而非数据库物理外键：Django 的 `ForeignKey`、`OneToOneField` 必须设置 `db_constraint=False`；在 serializer 或 service 中校验关联对象存在性、康复师数据归属与访问权限，并通过 Django ORM 的 `on_delete` 执行删除、置空或保护语义。禁止使用 SQL `FOREIGN KEY`、`REFERENCES` 或数据库级级联来保证业务关联。

## 2. 数据库与 SQL 规范

### 2.1 Schema 来源

- Django model 是运行时 schema 的唯一实现来源；所有结构变更必须生成并提交 migration。
- 同时在 `docs/database/` 维护可读 SQL 文件：每张新增或变更的业务表一个文件，例如 `docs/database/customers.sql`、`docs/database/training_records.sql`。
- SQL 文件用于审阅、交接和数据库结构查阅，不应手动绕过 migration 直接改生产表。

### 2.2 SQL 文件要求

- 使用 PostgreSQL 方言，包含 `CREATE TABLE`、主键、唯一约束、检查约束和必要索引；业务表不得声明物理外键。
- 表和字段使用 `snake_case` 英文命名；SQL 注释使用 `COMMENT ON TABLE` 与 `COMMENT ON COLUMN` 说明业务含义。
- 每个表必须包含可追溯字段；通常为 `created_at`、`updated_at`，需要软删除时增加 `deleted_at`。
- 涉及正式记录修订时，不覆盖历史数据；使用审计表或审计日志保存前后快照与修改原因。

### 2.3 数据变更流程

1. 修改 Django Model。
2. 生成并审阅 migration。
3. 更新或新增对应 `docs/database/*.sql`。
4. 在本地 Compose PostgreSQL 上执行迁移。
5. 验证业务关联校验、索引与数据隔离逻辑。

## 3. 测试与提交

- 后端至少执行 `python manage.py check`；涉及模型或 API 时应补充对应单元测试。
- 不提交 `.env`、虚拟环境、真实客户数据或 AI Key。
- 每个提交聚焦单一目的；提交说明清楚描述用户可见影响与数据迁移影响。
