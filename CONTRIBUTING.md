# Retrue 贡献指南

## 开始前

1. 阅读 `AGENT.md` 和与本次改动相关的规范文档。
2. 配置根目录与 `retrue-server/` 的 `.env`，启动 `docker compose up -d postgres`。
3. 先同步主分支，再创建以 `codex/` 开头的描述性分支，例如 `codex/customer-profile-api`。

## 提交前检查

- [ ] 不包含 `.env`、虚拟环境、`node_modules`、构建产物或真实客户数据。
- [ ] 新接口已同步后端、前端类型和 `docs/api/` 文档。
- [ ] 新表已同步 Model、migration 与 `docs/database/` SQL 文件。
- [ ] 后端执行 `python manage.py check`；前端执行 `npm run build`。
- [ ] AI 输出保持“草稿待确认”边界；正式记录修改包含审计信息。

## 提交信息

使用简洁中文说明，推荐格式：`类型(模块): 变更说明`。

示例：`feat(customers): 新增客户档案创建接口`。
