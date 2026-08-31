# Retrue 数据库文档约定

`docs/database/` 保存便于审阅的 PostgreSQL 表结构 SQL，不直接作为部署入口；实际数据库变更仍由 Django migration 执行。

## 文件命名

- 一张业务表一个文件，使用复数 `snake_case`：`customers.sql`、`training_records.sql`。
- 有关联表时使用清晰名称，例如 `training_record_exercises.sql`。

## 物理表名约定

- 所有业务模型的物理表名通过 `Meta.db_table` **显式指定**，统一为 `tb_` 前缀 + 复数 `snake_case` 业务名，
  例如：`tb_customers`、`tb_therapists`、`tb_course_sessions`、`tb_training_records`、`tb_rehab_plans`。
- `tb_` 前缀用于区分业务表与 Django 内置系统表（`auth_user`、`django_session`、`django_admin_log` 等）。
- 不使用 Django 默认的 `app_label_模型名` 拼接（避免 `customers_customer` 这类命名重复）。
- 内置系统表保留 Django 默认名，不加 `tb_` 前缀。
- 新增或变更表时，`db_table`、迁移中的表名与 SQL 文档中的 `CREATE TABLE` 必须保持一致。

## 每个 SQL 文件必须包含

1. `CREATE TABLE`、主键、唯一约束、检查约束和必要索引；业务表不得包含物理外键。
2. `COMMENT ON TABLE` 与关键 `COMMENT ON COLUMN` 的中文业务解释。
3. `created_at`、`updated_at`；需要软删除时增加 `deleted_at`。
4. 客户数据归属字段，例如 `therapist_id`，用于权限隔离。
5. 对正式记录修订的审计关联，不得覆盖历史值。

## 初始化/种子数据

- 需要初始化到数据库的目录型数据（如课程类型、课程计划模板），统一放在
  `docs/database/seed_*.sql`，例如 `seed_rehab_catalog.sql`。
- 种子 SQL 必须**幂等**：使用 `INSERT ... SELECT ... WHERE NOT EXISTS(...)`，
  重复执行不产生重复数据。
- 种子数据按**康复师用户名**归属：通过 `FROM tb_users WHERE username = '...'`
  取 `therapist_id`，避免硬编码用户 id，便于为不同康复师复用。
- 涉及物理表名、字段与约束请与同目录 `*.sql` 结构文件保持一致。
- 种子 SQL 是初始化数据的唯一来源；不额外维护等价的 Django management command，
  需要初始化时直接执行对应的 `seed_*.sql` 即可。

## 变更检查表

- [ ] Django Model 已更新。
- [ ] Migration 已生成并审阅。
- [ ] 对应 SQL 文件已新增或更新。
- [ ] 已在本地 Compose PostgreSQL 执行迁移。
- [ ] 已验证索引、业务关联校验与康复师数据隔离。
- [ ] 新增目录型种子数据时，`docs/database/seed_*.sql` 已补齐且幂等可执行。
