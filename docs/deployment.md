# Retrue 配置与部署入口

服务器完整部署、Nginx 示例、数据库前置条件、迁移顺序和回滚见 [DEPLOY.md](../DEPLOY.md)。生产 Compose 仅有 Django backend，不管理 PostgreSQL 或 Nginx；前端是 Vue/Vite 静态 SPA。

## 开发环境

保留 `config.settings` 默认行为，读取 `retrue-server/.env`；变量见 [后端示例](../retrue-server/.env.example)。开发数据库独立准备，已有环境可继续使用 `127.0.0.1:5433`。不要把生产根目录示例覆盖到开发配置。

在 `retrue-server` 目录执行：

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

仅本地演示库可以运行 `init_demo_data`，该命令包含固定密码，并会重设演示账号密码。生产通过明确的账号管理流程建立账号，目录型种子数据按 [数据库规范](database/README.md) 单独审阅。

## 生产环境

- 根目录 `.env` 由 Compose 注入，不进入镜像；变量见 [根目录示例](../.env.example)。
- `config.settings_production` 强制关闭 DEBUG、校验 SECRET_KEY 和数据库必填值、设置同源 CORS/CSRF 与代理 HTTPS。
- static 使用明确的 collectstatic 和宿主机发布快照，media 持久保存但不公开。
- 不在容器启动时迁移，完整发布命令顺序以 DEPLOY.md 为准。
- 旧三服务 Compose 已替换，旧容器和数据卷不会被配置变更删除。

## AI 配置与优先级

无密钥的模型定义在 `retrue-server/ai_config.yaml`，密钥使用 `api_key_env` 引用环境变量。禁止将真实 api_key 直接写入 YAML。

1. `AI_CONFIG_FILE` 指定的 YAML（`config.enabled=true`）优先。
2. 未启用 YAML 时使用 `AI_FALLBACK_PROVIDERS` JSON 配置。
3. 最后使用 `AI_PROVIDER` 等单 provider 变量。

当前 YAML 的 `enable_model_fallback=false`，聊天仅使用第一项 DeepSeek。只有显式开启后，才按配置顺序尝试 DeepSeek、Qwen、mock；不要把模型列表误认为已启用的故障转移。真实生产环境使用 mock 兜底前需明确业务允许范围。

| 变量 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 当前第一项聊天模型 |
| `QWEN_API_KEY` | 当前 embedding，以及启用故障转移后的 Qwen 聊天 |
| `AI_CONFIG_FILE` | YAML 路径，Docker 为 `/app/ai_config.yaml` |
| `AI_PROVIDER` / `AI_MODEL` / `AI_BASE_URL` / `AI_API_KEY` | 未启用 YAML 时的兼容单模型配置 |
| `AI_FALLBACK_PROVIDERS` | 未启用 YAML 时的兼容多模型配置 |
| `AI_TIMEOUT` / `AI_MAX_TOKENS` | 兼容 provider 默认超时和 token 限制；YAML 条目可独立配置 |
| `AI_EMBEDDING_API_KEY` | embedding 环境变量兼容入口；当前 YAML 使用 QWEN_API_KEY |

密钥不得提交到 Git、前端构建或日志。备份包含客户健康数据，也应限制访问并按部署文档管理。
