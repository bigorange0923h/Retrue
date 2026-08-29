# Retrue

面向运动康复师的客户管理、康复记录与 AI 辅助工作台。

## 项目结构

- `retrue-web`：Vue 3 + TypeScript + Vite + Pinia + Element Plus 前端
- `retrue-server`：Django + Django REST Framework + Pydantic 后端

## 本地开发

1. 在项目根目录复制 `.env.example` 为 `.env`，并设置 `RETRUE_POSTGRES_PASSWORD`。
2. 启动独立数据库：`docker compose up -d postgres`。
3. 在 `retrue-server` 中复制 `.env.example` 为 `.env`，并使用相同的数据库密码。
4. 执行迁移：`retrue-server\\.venv\\Scripts\\python manage.py migrate`。
5. 初始化演示数据：`retrue-server\\.venv\\Scripts\\python manage.py init_demo_data`。
   - 演示康复师：`retrue` / `retrue123`；管理员：`admin` / `admin123`。
6. 启动后端：`retrue-server\\.venv\\Scripts\\python manage.py runserver`
7. 启动前端：在 `retrue-web` 中运行 `npm run dev`

后端健康检查：`http://127.0.0.1:8000/api/health/`。

运行 `docker compose up --build` 可同时启动 PostgreSQL、后端和前端。数据库映射到 `127.0.0.1:5433`，以避免与 KnowledgeArk 的 PostgreSQL（5432）冲突。

### AI 服务商配置

聊天模型统一由 `retrue-server/ai_config.yaml` 管理（详见 `docs/deployment.md`）：

- 默认顺序：DeepSeek → Qwen → mock；真实密钥只放在服务端 `.env`。
- DeepSeek 单次失败会在当前请求内自动切换 Qwen；连续失败 3 次后熔断 5 分钟，期间直接使用备用模型。
- `AI_PROVIDER`、`AI_FALLBACK_PROVIDERS` 保留为旧部署的兼容配置；新部署不建议使用。

配置了未实现的 `AI_PROVIDER` 时系统会抛错而非静默回退，便于及时发现配置问题。

## V1 范围

优先实现「今日客户 → 训练记录 → AI 草稿确认 → 客户时间线 → 下次备课」核心闭环；AI 仅生成待确认草稿，不直接修改正式记录。
