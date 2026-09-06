# Retrue

面向运动康复师的客户管理、康复记录与 AI 辅助工作台。

## 项目结构

- `retrue-web`：Vue 3 + TypeScript + Vite + Pinia + Element Plus 前端
- `retrue-server`：Django + Django REST Framework + Pydantic 后端

## 本地开发

1. 准备独立的开发 PostgreSQL + pgvector，继续使用现有开发数据库也可以；生产 Compose 不再管理数据库。
2. 在 `retrue-server` 中复制 `.env.example` 为 `.env`，填写开发数据库地址、端口和密码（示例保留旧开发端口 5433）。
3. 后端命令在 `retrue-server` 目录执行，Windows 使用 `.venv\\Scripts\\python.exe`。
4. 执行迁移：`.venv\\Scripts\\python.exe manage.py migrate`。
5. 仅开发初始化演示数据：`.venv\\Scripts\\python.exe manage.py init_demo_data`。
   - 演示康复师：`retrue` / `retrue123`；管理员：`admin` / `admin123`。
6. 启动后端：`.venv\\Scripts\\python.exe manage.py runserver`
7. 启动前端：在 `retrue-web` 中运行 `npm run dev`

后端健康检查：`http://127.0.0.1:8000/api/health/`。

服务器部署见 [DEPLOY.md](DEPLOY.md)：宿主机 PostgreSQL + Nginx，Docker 仅运行 Django ASGI 后端，前端 build 后由宿主机 Nginx 提供。根目录 `.env.example` 专用于生产，开发 `.env` 不受影响。已有前端 Dockerfile 保留为历史文件，正式部署不使用。

### AI 服务商配置

聊天模型统一由 `retrue-server/ai_config.yaml` 管理（详见 `docs/deployment.md`）：

- 当前 `enable_model_fallback=false`，聊天仅使用第一项 DeepSeek；启用故障转移后才按 DeepSeek → Qwen → mock 尝试。
- 真实密钥只放在服务端环境变量中，Qwen 同时用于知识库 embedding。
- `AI_PROVIDER`、`AI_FALLBACK_PROVIDERS` 保留为旧部署的兼容配置；新部署不建议使用。

配置了未实现的 `AI_PROVIDER` 时系统会抛错而非静默回退，便于及时发现配置问题。

## V1 范围

优先实现「今日客户 → 训练记录 → AI 草稿确认 → 客户时间线 → 下次备课」核心闭环；AI 仅生成待确认草稿，不直接修改正式记录。
