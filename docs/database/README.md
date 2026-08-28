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

1. `CREATE TABLE`、主键、外键、唯一约束、检查约束和必要索引。
2. `COMMENT ON TABLE` 与关键 `COMMENT ON COLUMN` 的中文业务解释。
3. `created_at`、`updated_at`；需要软删除时增加 `deleted_at`。
4. 客户数据归属字段，例如 `therapist_id`，用于权限隔离。
5. 对正式记录修订的审计关联，不得覆盖历史值。

## 变更检查表

- [ ] Django Model 已更新。
- [ ] Migration 已生成并审阅。
- [ ] 对应 SQL 文件已新增或更新。
- [ ] 已在本地 Compose PostgreSQL 执行迁移。
- [ ] 已验证索引、外键与康复师数据隔离。
