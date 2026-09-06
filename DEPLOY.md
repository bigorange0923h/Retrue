# Retrue 服务器部署

目标：宿主机 Nginx 提供 Vue 静态页面，并代理 `/api/`、`/admin/` 到仅绑定 `127.0.0.1:8000` 的 Django 容器；PostgreSQL 留在宿主机。本文命令由发布者在服务器执行，本次配置工作不操作服务器服务或数据库。

## 1. 已核对的项目事实

| 检查项 | 当前代码与部署选择 |
| --- | --- |
| 前端 | `retrue-web`，Vue 3、TypeScript、Vite 8.2.2、Pinia、Element Plus；纯静态 SPA，没有 SSR |
| Node | package.json 原先没有 engines；锁文件中的 Vite / Vue 插件要求 `^20.19.0 \|\| >=22.12.0`。本次构建环境为 Node 24.16.0，服务器建议统一 Node 24 |
| 前端构建 | `npm ci` 后 `npm run build`，实际脚本为 `vue-tsc -b && vite build`，输出 `retrue-web/dist/` |
| API 地址 | Axios `/api`，流式 fetch `/api/assistant/turns/stream/`；同源部署无需前端域名环境变量，开发 Vite proxy 不参与生产 |
| Django 入口 | `retrue-server/manage.py`，`config.asgi:application` 和 `config.wsgi:application` 均存在 |
| Python / Django | 当前虚拟环境 Python 3.14.5、Django 6.0.8；镜像采用官方 `python:3.14-slim-bookworm` |
| 依赖 | pip + `requirements.txt`，没有 Poetry/uv 锁文件；新增 `requirements-production.txt` 仅添加生产服务器依赖 |
| 原有启动 | README 和原 Dockerfile 使用 runserver；原依赖不含 Gunicorn/Uvicorn |
| 配置 | 开发仍是 `config.settings` + `retrue-server/.env`；Docker 显式用 `config.settings_production` + 根目录 `.env` 注入 |
| LangGraph | 已有节点事件 streaming；业务在后台线程同步执行，ASGI 使用异步迭代器输出 SSE，未发现 WebSocket/Channels 路由 |
| SSE 限制 | 每个进程最多 4 个流，10 秒心跳、180 秒服务端上限；默认 2 workers 的名义容量为 8，并非全局配额 |
| PostgreSQL | 已用 `POSTGRES_*` 变量、psycopg binary；新增生产配置强制 PostgreSQL 并禁止回退开发密码 |
| static / media | 原先仅 STATIC_URL，含 Django admin 静态资源，必须 collectstatic；未发现 FileField/ImageField 或上传存储配置。新增持久 media 目录，但不公开访问 |
| migrations | 多个业务 app 已有 migration，包含数据迁移与 pgvector VectorExtension；不能只按空库 DDL 处理 |
| 初始化 | `init_demo_data` 仅供开发，含固定密码且会重设演示密码，生产禁止执行；目录数据按需审阅 `docs/database/seed_*.sql`，不是启动必需步骤 |
| 原部署文件 | 原 `compose.yaml` 同时启动 PostgreSQL/server/web；两个子目录已有 Dockerfile，`docs/deployment.md` 原为开发部署说明 |
| 健康检查 | 复用 `/api/health/`，仅检查 HTTP 存活，不检查数据库、migration 或模型可用性 |

选择 Gunicorn + `uvicorn_worker.UvicornWorker`，与 [Django 官方 ASGI 部署说明](https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/uvicorn/)一致。不用旧的 `uvicorn.workers` 导入路径。Gunicorn timeout 240 秒、graceful timeout 210 秒，Compose 停止宽限 240 秒。同步模型任务可能在断线后继续运行，因此发布需安排维护窗口，不能把滚动重启视为任务无损取消。

`docker-compose.yml` 是唯一服务定义，仅有 backend。保留的 `compose.yaml` 转发到它，避免 Docker 默认选中旧配置；转发需要 Compose 2.20.0+。本文始终显式 `-f docker-compose.yml`，建议使用当前 Compose v2/v5 插件。固定项目名 `retrue-production` 与旧开发项目隔离；不会接管或删除旧 PostgreSQL 容器和数据卷。若旧容器占用 8000，须先识别并另行处理，不要使用 remove-orphans 或清理命令。

## 2. 服务器目录和前置条件

```text
/srv/retrue/
├── app/                       # Git checkout，根目录 .env 权限 600
├── releases/<release>/
│   ├── web/                   # dist 的发布快照
│   ├── collected/             # Docker collectstatic 输出，容器 UID 10001 可写
│   ├── static/                # Nginx 使用的独立只读快照
│   ├── deployment.env         # 该版本配置快照，权限 600，含密钥
│   └── source-commit.txt
├── current -> releases/<release>
└── shared/media/              # UID/GID 10001:10001，跨版本保存
```

服务器需有 Docker Engine 20.10+（host-gateway）、Compose 插件、Git、Node 24/npm，以及已安装的宿主机 Nginx、PostgreSQL。建议普通部署账户拥有 `/srv/retrue/app`、`releases`、`current` 的管理权限，容器始终以 UID/GID 10001 运行。不要对所有目录设置 777。

Nginx 只读取 `web` / `static`，不要把仓库、`.env`、media 或整个 `/srv/retrue` 配成网站根目录。为回滚保留旧镜像和旧 release，不覆盖同一个镜像 tag。

## 3. .env

首次准备目录并克隆（已有 checkout 时跳过创建和克隆）：

```bash
sudo install -d -m 0755 -o "$(id -u)" -g "$(id -g)" /srv/retrue
install -d -m 0755 /srv/retrue/releases /srv/retrue/shared
REPOSITORY_URL='填写本仓库的实际Git地址'
git clone "$REPOSITORY_URL" /srv/retrue/app
```

然后配置环境文件：

```bash
cd /srv/retrue/app
umask 077
cp .env.example .env                  # 仅首次，已有 .env 不要覆盖
chmod 600 .env
openssl rand -hex 32                  # 生成 64 字符 SECRET_KEY，填入 .env
vi .env
```

必须填写 `DJANGO_SECRET_KEY`、`POSTGRES_PASSWORD`、数据库名称/用户和实际域名。密码如含 `$`、`#` 或空格，使用 dotenv 单引号包裹整个值；不要用 `source .env`。密钥留空会阻止启动。不要执行或分享会完整打印环境变量的 `docker compose config` / `docker inspect` 输出，校验用 `config --quiet`。

生产 `.env` 使用根目录版本，容器不复制或读取开发 `retrue-server/.env`。即便填写 `DJANGO_DEBUG=true`，生产模块也强制关闭 DEBUG。同源 `CORS_ALLOWED_ORIGINS` 留空，`CSRF_TRUSTED_ORIGINS=https://实际域名`。Session 和 CSRF Cookie 默认仅 HTTPS，保留前端读取 CSRF Cookie 的现有方式。

当前 `ai_config.yaml` 已启用，`enable_model_fallback=false`：聊天只使用第一项 DeepSeek；Qwen 用于 embedding。填写 `DEEPSEEK_API_KEY`、`QWEN_API_KEY`，不要误以为 `AI_PROVIDER=mock` 能覆盖 YAML。模型名称/端点/故障转移调整仍放无密钥 YAML，配置优先级保持原业务实现。修改镜像内 YAML 后要重新构建。

HTTPS 由宿主机 Nginx 终止。Django 信任 Nginx **覆盖写入**的 `X-Forwarded-Proto`，仅适用于当前受控代理拓扑。短期 HTTP 隔离验收时可同时设 `SECURE_SSL_REDIRECT=false`、`SESSION_COOKIE_SECURE=false`、`CSRF_COOKIE_SECURE=false`、`SECURE_HSTS_SECONDS=0` 并改 CSRF 来源；上线恢复 HTTPS，不能直接在公网 HTTP 使用真实账号。HSTS 默认一小时，不包含子域、不预加载。

## 4. 宿主机 PostgreSQL 必须核对

`host.docker.internal:host-gateway` 只解决容器到宿主机的地址解析，**不会**替你修改 PostgreSQL 监听或访问规则。在容器里 `127.0.0.1` 指向容器自己。保持 `POSTGRES_HOST=host.docker.internal`、`POSTGRES_PORT=5432`（若宿主机使用其他端口则改为实际值）。

管理员需在正式部署前确认：

1. 数据库与应用角色已准备，应用角色拥有项目 schema 的迁移权限，日常应用不使用 PostgreSQL 超级用户。
2. 宿主机已安装与其 PostgreSQL 主版本匹配的 pgvector 扩展文件，并在目标数据库启用 `vector`。仅安装 Python 的 pgvector 包不够，安装方法参考 [pgvector 官方说明](https://github.com/pgvector/pgvector#installation)。
3. `listen_addresses` 包含 host-gateway 对应的 Docker 网桥地址（例如 `localhost,172.17.0.1`，必须以服务器实际地址为准），不能只监听 localhost，也不要监听公网地址或 `*`。
4. `pg_hba.conf` 仅允许实际 Compose 子网到该数据库/角色，使用 `scram-sha-256`，不要写 `0.0.0.0/0`。例：`host retrue retrue <实际Compose子网CIDR> scram-sha-256`。
5. 现有防火墙/SELinux 策略允许所需的本机流量，但 PostgreSQL 5432 不对公网开放。本文不会修改这些设置。

这些只读命令可由管理员核对现状，示例库名需替换：

```bash
docker network inspect bridge --format '{{json .IPAM.Config}}'
ss -lnt | grep -E ':(5432|8000)\b'
sudo -u postgres psql -d retrue -c 'SHOW listen_addresses;'
sudo -u postgres psql -d retrue -c "SELECT name, default_version, installed_version FROM pg_available_extensions WHERE name = 'vector';"
```

首次 `docker compose run` 会建立 `retrue-production_default`，可再查看来源子网：

```bash
docker network inspect retrue-production_default --format '{{json .IPAM.Config}}'
docker compose -f docker-compose.yml run --rm --no-deps backend python -c "import socket; print(socket.gethostbyname('host.docker.internal'))"
```

确认网络/账号/pgvector 前不要执行 migrate。若扩展未启用，由 DBA 在确认目标库后执行 `CREATE EXTENSION IF NOT EXISTS vector;`；不要为了迁移长期给应用账号超级用户权限。Docker 网络重建可能更换来源子网，应重新核对授权范围。

## 5. 正式发布完整命令顺序

以下在 Bash、仓库根目录执行；假设已完成上一节数据库配置、`.env`、HTTPS 证书准备。更新时先 checkout 已审阅的发布提交，保留上一版本镜像和配置。每一步成功才继续；本次不会替你执行这些服务器命令。

```bash
set -euo pipefail
umask 022
cd /srv/retrue/app
RELEASE="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD)"
RELEASE_DIR="/srv/retrue/releases/$RELEASE"

# 1. 创建独立发布目录和容器可写目录。
install -d -m 0755 /srv/retrue/releases "$RELEASE_DIR" "$RELEASE_DIR/web" "$RELEASE_DIR/static"
sudo install -d -m 0755 -o 10001 -g 10001 "$RELEASE_DIR/collected"
sudo install -d -m 0700 -o 10001 -g 10001 /srv/retrue/shared/media
sed -i "s|^RETRUE_IMAGE_TAG=.*|RETRUE_IMAGE_TAG=$RELEASE|" .env
sed -i "s|^RETRUE_STATIC_DIR=.*|RETRUE_STATIC_DIR=$RELEASE_DIR/collected|" .env
sed -i 's|^RETRUE_MEDIA_DIR=.*|RETRUE_MEDIA_DIR=/srv/retrue/shared/media|' .env
chmod 600 .env
docker compose -f docker-compose.yml config --quiet

# 2. 前端只在构建时需要 Node，不运行 frontend 容器。
node --version                         # Node 24
cd retrue-web
npm ci
npm run build
cp -a dist/. "$RELEASE_DIR/web/"
cd ..

# 3. 构建新后端镜像，无真实配置进入构建上下文。
docker compose -f docker-compose.yml build --pull backend
docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py check --deploy
docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py collectstatic --noinput
cp -R "$RELEASE_DIR/collected/." "$RELEASE_DIR/static/"
chmod -R a+rX "$RELEASE_DIR/web" "$RELEASE_DIR/static"
git rev-parse HEAD > "$RELEASE_DIR/source-commit.txt"
install -m 0600 .env "$RELEASE_DIR/deployment.env"

# 4. 只读检查数据库连通、扩展以及即将应用的 migration。
docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('SELECT 1'); print(c.fetchone()); c.execute(\"SELECT extversion FROM pg_extension WHERE extname='vector'\"); assert c.fetchone(), '缺少 vector 扩展'"
docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py migrate --plan

# 5. 此处进入维护窗口，由 DBA 完成并核对备份。
# 首次发布可跳过 stop；升级先停旧后端，避免业务请求与数据迁移并发。
docker compose -f docker-compose.yml stop backend
# 下例使用宿主机 postgres 管理员和本地 socket；DB_NAME 必须与 .env 一致。
DB_NAME='retrue'
install -d -m 0700 /srv/retrue/backups
(umask 077; sudo -u postgres pg_dump -Fc "$DB_NAME" > "/srv/retrue/backups/$RELEASE.dump")
sudo -u postgres pg_restore --list < "/srv/retrue/backups/$RELEASE.dump" > /dev/null
# 目录可读检查不等于恢复演练；备份恢复能力需在发布前确认。
# 确认备份、扩展和迁移计划后，明确执行一次；容器重启不会自动迁移。
docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py migrate --noinput
docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py migrate --check

# 6. 启动新镜像，等待健康检查（失败时停止发布，不切换前端）。
docker compose -f docker-compose.yml up -d --no-build --wait --wait-timeout 120 backend
curl --fail http://127.0.0.1:8000/api/health/

# 7. 原子切换前端和 admin 静态资源；current 必须是符号链接或尚不存在。
test ! -e /srv/retrue/current || test -L /srv/retrue/current
ln -s "$RELEASE_DIR" "/srv/retrue/current.$RELEASE"
mv -Tf "/srv/retrue/current.$RELEASE" /srv/retrue/current

# 8. 首次部署由管理员审阅安装 Nginx 示例后再核对公网入口。
docker compose -f docker-compose.yml ps
curl --fail https://retrue.example.com/api/health/
```

首次启用 Nginx 的人工步骤见下一节。命令中的示例域名必须替换，证书必须有效。若维护期间需向前端显示维护页，由管理员事先安排；这里没有自动改 Nginx。新增管理员时交互执行 `docker compose -f docker-compose.yml run --rm --no-deps backend python manage.py createsuperuser`，不要运行 init_demo_data。种子目录数据只在业务需要且审阅用户归属后由管理员导入，不属于容器入口。

## 6. Nginx 与 OpenCloudOS / SELinux

示例文件：[deploy/nginx.conf.example](deploy/nginx.conf.example)。管理员需替换域名、证书、路径，确认不与已有 server 块冲突，再自行安装。本文不直接修改 `/etc/nginx`。审阅安装后才执行 `sudo nginx -t`，通过后 `sudo systemctl reload nginx`。

关键行为：`proxy_pass http://127.0.0.1:8000` 保留 `/api/` 前缀；重写 Host 和代理头；关闭 SSE 缓冲/缓存/gzip，超时 240 秒，禁止代理自动重试；Vue history 路由回退 index.html；Django static 指向 collectstatic 的发布快照；media 返回 404。前端无需 Vite preview 或常驻 Node。

OpenCloudOS 可能启用 SELinux enforcing。Compose 对专用 `collected`/media 目录使用 `:z` 标签，发布时复制静态资源到另一目录供 Nginx 读取，避免同一目录标签冲突。不要把 `:z` 挂载源改成 `/srv`、`/etc` 或整个仓库。

若 Nginx 出现权限拒绝，管理员先检查 `getenforce`、`ls -Zd`、`namei -l /srv/retrue/current/web/index.html` 和审计日志。在确认是 SELinux 策略后，可为专用静态发布路径配置持久的 `httpd_sys_content_t`（示例规则 `/srv/retrue/releases/[^/]+/(web|static)(/.*)?`），并对当前发布的 web/static 执行 restorecon。后续每次发布也需对新目录恢复标签；不要对 collected/media 应用此静态标签。Nginx 访问上游若被拦截，由管理员评估开启 `httpd_can_network_connect` 或更窄的本机策略。这里不自动安装 SELinux 工具、关闭 SELinux 或修改安全策略。

## 7. 日常运维与检查

在 `/srv/retrue/app`：

```bash
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs --tail=200 -f backend
docker compose -f docker-compose.yml stop backend
docker compose -f docker-compose.yml start backend
docker compose -f docker-compose.yml restart backend
# 修改 .env 后 restart 不会重新加载环境，需重建容器：
docker compose -f docker-compose.yml up -d --no-build --force-recreate --wait backend
docker compose -f docker-compose.yml exec backend python healthcheck.py
docker compose -f docker-compose.yml exec backend python manage.py migrate --check
```

镜像以非 root 运行；应用日志 stdout，Gunicorn stdout/stderr，Docker 每文件 10MB、保留 5 个。日志也可能含业务上下文，应按现有项目敏感数据规范限制访问。healthcheck 标记 unhealthy **不会**触发 Docker 自动重启；restart 策略只在进程退出时生效。health 正常后仍须检查登录/CSRF、实际 DB 和授权的模型测试。

SSE 上线验收：登录测试账号，用已授权的无敏感输入发起一次对话；浏览器应先显示连接/进度，等待模型时约每 10 秒有字节，并在最终结果前持续收到事件。若经过 CDN/上层代理也须关闭其缓冲；curl health 不能证明 SSE 正常。不要在断线后自动重发业务请求。

## 8. 备份和回滚

宿主机备份由 DBA 管理，例如维护窗口内用 `pg_dump -Fc` 写到权限 600 的专用备份目录，验证可读性与恢复流程，并保存 media。不要把密码写在命令参数中；使用受控 `.pgpass`、Unix socket 认证或交互输入。不在本文自动执行恢复或反向 migration。

如果 migration 尚未改变 schema，或已确认新 schema 兼容旧代码，可回退镜像、环境和静态快照。若 migration 含不可逆数据转换/旧代码不兼容，先停写并制定恢复计划，**仅换旧镜像不构成数据库回滚**。已有多个 RunPython 数据迁移，不能盲目 migrate 到旧序号。

确认兼容后（把 OLD_RELEASE 替换为实际保留版本）：

```bash
set -euo pipefail
cd /srv/retrue/app
OLD_RELEASE=20260906-120000-abcdef0
OLD_DIR="/srv/retrue/releases/$OLD_RELEASE"
test -f "$OLD_DIR/deployment.env"
test -f "$OLD_DIR/web/index.html"
docker image inspect "retrue-backend:$OLD_RELEASE" --format '{{.Id}}'
docker compose -f docker-compose.yml stop backend
install -m 0600 "$OLD_DIR/deployment.env" .env
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml up -d --no-build --wait --wait-timeout 120 backend
ln -s "$OLD_DIR" /srv/retrue/current.rollback
mv -Tf /srv/retrue/current.rollback /srv/retrue/current
curl --fail http://127.0.0.1:8000/api/health/
```

保留与该版本匹配的部署文件/Git 提交记录；将来 Compose 结构改变时同时回到对应已审阅部署定义。密钥若已轮换，恢复旧环境快照前先同步当前有效密钥。旧 SPA 页面可能引用上一版哈希资源，切换后应刷新页面。依赖当前采用版本范围，重复 build 可能解析到不同版本，因此回滚必须复用已验证的镜像，不能重新构建旧 tag 充当原镜像。

## 9. 本次验证范围

2026-09-06 本地验证结果：

| 验证 | 结果与范围 |
| --- | --- |
| 前端生产构建 | Node 24.16.0，使用现有 node_modules 执行 npm run build 成功，产物 dist；有已有大 chunk 提醒，未单独验证全新 npm ci |
| Compose | 使用虚构配置验证两个入口解析成功，仅 backend、项目名 retrue-production、127.0.0.1:8000 映射；未启动容器 |
| Django 生产配置 | 不读取真实 .env，拦截任何数据库连接；必填变量缺失/通配域名拒绝、HTTP/ASGI health、HTTPS 代理/跳转、CSRF Secure Cookie 均通过 |
| collectstatic | 输出到忽略的隔离目录，已确认 admin/css/base.css 生成 |
| SSE | 现有后端 ProgressTests 6 项、前端 SSE 4 项全部通过；不代表真实 Nginx/模型链路验收 |
| check --deploy | 无错误；保留 security.W005、W021：HSTS 不扩大到全部子域、不启用 preload，需确认所有子域 HTTPS 后再决定 |
| 依赖解析 | 官方 PyPI 的 Linux x86_64 / CPython 3.14 二进制包 dry-run 全量解析成功；解析到 Gunicorn 25.3.0、Uvicorn 0.52.4、uvicorn-worker 0.4.0，不等于 Linux 实际安装测试 |
| Docker build | 已实际执行；在拉取 python:3.14-slim-bookworm 元数据时，auth.docker.io 认证连接超时。本机无 Python 镜像缓存，镜像构建及 Gunicorn 容器启动尚未验证成功 |

服务器 PostgreSQL、Nginx、TLS、SELinux、真实账号和模型均未在此工作区操作。网络恢复后须重跑 `docker compose -f docker-compose.yml build --pull backend`，再按发布步骤验收；不要把上述静态检查视为已成功发布。

## 10. 本次文件清单

| 类型 | 文件 | 目的 |
| --- | --- | --- |
| 新增 | docker-compose.yml | 仅管理生产 backend，回环端口、宿主机映射、卷和健康检查 |
| 新增 | retrue-server/.dockerignore | 排除 .env、虚拟环境、日志和本地数据 |
| 新增 | retrue-server/requirements-production.txt | 独立添加 Gunicorn/Uvicorn/worker，保留开发依赖管理 |
| 新增 | retrue-server/gunicorn.conf.py | ASGI worker、进程数、超时和 stdout/stderr |
| 新增 | retrue-server/config/settings_production.py | 环境变量校验、HTTPS、安全 Cookie、静态和 media 配置 |
| 新增 | retrue-server/healthcheck.py | 复用已有 health API，不增加业务接口 |
| 新增 | deploy/nginx.conf.example | 宿主机静态文件、API/SSE 和 admin 代理示例 |
| 新增 | DEPLOY.md | 项目分析、完整服务器操作顺序、回滚和验证记录 |
| 修改 | retrue-server/Dockerfile | 官方 slim、依赖缓存、非 root、生产 ASGI 启动 |
| 修改 | compose.yaml | 转到唯一生产定义，避免默认误启动旧三服务配置 |
| 修改 | .env.example | 无真实凭据的生产配置模板 |
| 修改 | retrue-server/.env.example | 开发密码示例不再依赖旧 Compose 变量，保留开发端口 |
| 修改 | retrue-server/config/settings.py | LOG_TO_FILE=false 时不创建目录/文件 handler，控制台输出 stdout |
| 修改 | .gitignore | 排除环境文件变体、运行数据和验证产物 |
| 修改 | README.md | 区分开发/生产入口，修正实际 AI 故障转移说明 |
| 修改 | docs/deployment.md | 替换过时三容器教程，保留配置说明并指向本文 |
| 修改 | docs/architecture.md | 同步实际生产拓扑与开发数据库说明 |

本地构建 dist 和 var 下的隔离验证产物已被忽略，不属于提交文件。没有删除项目文件或更改业务模型、接口和 migration；未修改真实 .env、数据库、服务器 Nginx 或防火墙。
