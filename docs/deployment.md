# Retrue 部署与环境变量

本文档说明 Retrue 的部署方式、环境变量与备份恢复。

## 1. 环境变量说明

### 根目录 `.env`（用于 Docker Compose）

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `RETRUE_POSTGRES_PASSWORD` | PostgreSQL 数据库密码，用于本地 Compose。 | `replace-with-a-local-development-password` |

### `retrue-server/.env`（Django 后端）

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django 密钥，生产必须使用强随机值。 | `unsafe-development-key` |
| `DJANGO_DEBUG` | 是否开启调试模式，生产应设为 `false`。 | `true` |
| `DJANGO_ALLOWED_HOSTS` | 允许访问的主机，逗号分隔。 | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | 允许跨域的前端源，逗号分隔。 | `http://localhost:5173` |
| `POSTGRES_DB` | 数据库名。 | `retrue` |
| `POSTGRES_USER` | 数据库用户。 | `retrue` |
| `POSTGRES_PASSWORD` | 数据库密码，需与根目录 `RETRUE_POSTGRES_PASSWORD` 一致。 | - |
| `POSTGRES_HOST` | 数据库主机。 | `127.0.0.1` |
| `POSTGRES_PORT` | 数据库端口（本地 Compose 映射为 5433）。 | `5433` |
| `SESSION_COOKIE_SECURE` | 是否仅 HTTPS 下发送 Session Cookie，生产设为 `true`。 | `false` |

### AI 服务商配置

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `AI_PROVIDER` | 旧版单模型配置，保留兼容；新部署请使用 `ai_config.yaml`。 | `mock` |
| `AI_API_KEY` | 服务商密钥，敏感信息，仅存服务端 `.env`。 | 空 |
| `AI_MODEL` | 模型名称，DeepSeek 默认 `deepseek-chat`。 | `deepseek-chat` |
| `AI_BASE_URL` | 自定义 API 地址（可选，兼容网关/代理）。DeepSeek 默认 `https://api.deepseek.com`。 | 空 |
| `AI_TIMEOUT` | 请求超时秒数。 | `60` |
| `AI_MAX_TOKENS` | 最大输出 token 数。 | `2000` |
| `AI_FALLBACK_PROVIDERS` | 旧版多模型 JSON 配置，保留兼容；新部署请使用 YAML。 | 空 |
| `AI_CONFIG_FILE` | 聊天模型 YAML 配置路径，默认 `retrue-server/ai_config.yaml`。 | `ai_config.yaml` |

> 配置了未实现的 `AI_PROVIDER` 时，系统会抛出清晰错误而非静默回退到 mock。
> DeepSeek 未配置 `AI_API_KEY` 时同样会给出明确提示。

### 聊天模型与故障转移（推荐用 YAML）

多模型配置放在 `retrue-server/ai_config.yaml`，比 `.env` 的 JSON 更清晰易维护：

```yaml
config:
  enabled: true

chat:
  circuit_breaker:
    failure_threshold: 3   # 连续失败 3 次后熔断
    cooldown_seconds: 300  # 5 分钟内跳过故障模型

  models:
    - name: deepseek-chat
      provider: openai_compatible
      model: deepseek-chat
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY   # 密钥引用 .env 中的变量

    - name: qwen-plus
      provider: openai_compatible
      model: qwen-plus
      base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
      api_key_env: QWEN_API_KEY

  - name: mock                      # 兜底
    provider: mock
```

各服务商独立密钥在 `.env` 中定义（不写入 yaml）：

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
```

启用步骤：
1. 在 `.env` 填入各服务商密钥（`DEEPSEEK_API_KEY`、`QWEN_API_KEY`）。
2. 按需要调整 `chat.models` 的顺序、模型名称和超时；默认配置已启用。
3. 重启后端。

配置优先级：
1. yaml（`AI_CONFIG_FILE`，enabled=true）。
2. `AI_FALLBACK_PROVIDERS`（JSON 数组，备选）。
3. 单 provider（`AI_PROVIDER`）。

故障转移规则：
- 模型按 `chat.models` 顺序依次尝试，首个成功即返回。
- 单个模型调用失败（网络/超时/解析错误）时，在当前请求内自动切换到下一个。
- 同一个模型连续失败达到 `failure_threshold` 后进入熔断；在 `cooldown_seconds` 内直接跳过，窗口结束后自动恢复探测。
- 所有 provider 均失败时抛出汇总错误。

密钥引用方式（每个 provider 条目）：
- `api_key_env`：指定环境变量名（推荐，各服务商独立密钥）。
- `api_key`：直接填值。
- `api_key` 形如 `${VAR}`：从环境变量引用。

> 注意：`.env` 文件包含敏感信息（数据库密码、Secret Key、AI_API_KEY），已被 `.gitignore` 排除，不得提交到仓库。

## 2. 本地开发启动

1. 复制根目录 `.env.example` 为 `.env`，设置 `RETRUE_POSTGRES_PASSWORD`。
2. 启动数据库：`docker compose up -d postgres`。
3. 在 `retrue-server` 复制 `.env.example` 为 `.env`，密码与根目录一致。
4. 执行迁移：`retrue-server\.venv\Scripts\python manage.py migrate`。
5. 初始化演示数据：`retrue-server\.venv\Scripts\python manage.py init_demo_data`。
6. 启动后端：`retrue-server\.venv\Scripts\python manage.py runserver`。
7. 启动前端：在 `retrue-web` 运行 `npm run dev`。

## 3. 一键 Docker 部署

运行 `docker compose up --build` 可同时启动 PostgreSQL、后端和前端：

- PostgreSQL：映射到 `127.0.0.1:5433`（避免与 KnowledgeArk 的 5432 冲突）。
- 后端：`http://127.0.0.1:8000`。
- 前端：`http://127.0.0.1:8080`。

生产环境建议：
- `DJANGO_DEBUG=false`，`SESSION_COOKIE_SECURE=true`。
- 使用 Nginx 反向代理并配置 HTTPS。
- 使用强 `DJANGO_SECRET_KEY` 与数据库密码。

## 4. 备份与恢复

### 备份

```bash
# 备份 PostgreSQL 数据库
docker exec retrue-postgres-1 pg_dump -U retrue -d retrue > retrue_backup_$(date +%Y%m%d).sql
```

### 恢复

```bash
# 将备份导入数据库
docker exec -i retrue-postgres-1 psql -U retrue -d retrue < retrue_backup_YYYYMMDD.sql
```

> 备份包含客户健康数据与手机号，属于敏感数据，存储和传输需加密并严格控制访问权限。

## 5. 数据安全提示

- 健康数据与手机号敏感，建议对数据库备份进行加密。
- AI Key 仅存放服务端 `.env`，前端不保存任何密钥。
- 客户列表接口默认脱敏手机号，仅受控编辑场景返回完整号码。
