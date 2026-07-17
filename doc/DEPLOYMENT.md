# 部署设计

## 当前状态与目标

当前仓库只有 `doc/prototype.html` 和样本内容，没有 Compose、镜像、Nginx 配置、迁移或运维脚本。下文是生产目标设计；其中命令只有在对应运行文件落地并经过预生产验证后才能执行，不能当作当前原型已经部署的证明。

目标是在一台阿里云 ECS 上以 Docker Compose 运行首版：Nginx 是唯一公开容器，统一承接 HTTP/HTTPS；Nuxt 公开端、Vue/Vite 管理端、FastAPI、可信 load-checker 和 PostgreSQL 全部留在内部网络。生产发布物是持久化 HTML 文件，索引元数据保存在 PostgreSQL。

## 服务组成

```text
internet
  ↓ 80 / 443
Nginx
  ├── /                       → web:3000
  ├── /admin/                 → admin:80
  ├── /api/                   → api:8000
  └── /snapshots/.../*.html   → 只读 published HTML

internal only
  api ──→ postgres:5432
   │
   ├──→ HTML 内容卷（读写）
   └──→ trusted load-checker（内部认证）
```

| 服务 | 公网端口 | 健康检查 | 持久化或权限 |
|---|---:|---|---|
| `nginx` | 80、443 | `/healthz` | 证书只读、已发布 HTML 只读、日志 |
| `web` | 无 | `/healthz` | 无 |
| `admin` | 无 | 静态入口 | 无 |
| `api` | 无 | `/api/health/ready` | HTML 内容卷读写 |
| `load-checker` | 无 | 内部任务探针 | 不直接写内容 |
| `postgres` | 无 | `pg_isready` | 数据卷 |

可信 load-checker 可以是独立 worker 容器，也可以是 FastAPI 启动的受控进程；两种实现都必须使用内部认证，只接受 API 创建的绑定记录 ID、版本、哈希与 nonce 的任务，并用 headless Chromium 执行权威加载检查。它没有公网路由，管理员客户端不能写入 `passed` 结果。

## Docker Compose

目标运行文件为 `compose.yaml`、`compose.prod.yaml`、各服务 Dockerfile、Nginx 配置和 `.env.example`。这些文件尚不存在时，本节所有命令都是待实现的运行手册。

- `compose.yaml` 定义服务、`edge` 与 `backend` 网络、健康检查和命名卷。
- `compose.prod.yaml` 固定镜像标签、资源限制、只读根文件系统、日志轮转、重启策略和生产挂载。
- 生产镜像使用 Git commit SHA 等不可变标签，不以 `latest` 作为发布依据。
- 除 Nginx 外不配置宿主机 `ports`；容器绝不挂载 Docker socket。

目标配置验证命令：

```bash
docker compose -f compose.yaml -f compose.prod.yaml config --quiet
docker compose -f compose.yaml -f compose.prod.yaml ps
```

## 本地开发

运行文件落地后的首次启动流程：

```bash
cp .env.example .env
docker compose up -d postgres
docker compose run --rm api alembic upgrade head
docker compose up --build
docker compose ps
```

常用诊断命令：

```bash
docker compose logs --since=30m api
docker compose logs --since=30m load-checker
docker compose restart api
docker compose down
```

默认不执行 `docker compose down -v`，避免删除数据库和 HTML 内容卷。

## 环境变量与密钥

目标环境至少提供：

| 变量 | 用途 |
|---|---|
| `APP_ENV` | `development` 或 `production` |
| `PUBLIC_BASE_URL` | `https://www.ayaseeri.com` |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD` | 数据库初始化 |
| `SESSION_SECRET`、`CSRF_SECRET` | 管理会话与 CSRF |
| `CONTENT_ROOT` | 容器内 HTML 根目录，例如 `/data/html` |
| `LOAD_CHECKER_TOKEN` | API 与可信检查器的内部认证 |
| `TRUSTED_HOSTS` | `www.ayaseeri.com,ayaseeri.com` |

生产密钥放在 `/srv/company/secrets/.env` 或等价的只读秘密存储中，只允许部署用户读取；不得提交到 Git、写入镜像、Compose 默认值或日志。Session、CSRF 和检查器密钥分别生成并支持轮换。TLS 证书与私钥只读挂载给 Nginx，不挂载给其他容器。

## 网络与安全组

Compose 定义两个网络：

- `edge`：Nginx 与 web、admin、api 通信，但只有 Nginx 绑定宿主机端口。
- `backend`：api、load-checker、postgres，设置为 `internal: true`；PostgreSQL 不加入 `edge`。

可信 load-checker 只可访问受控预览地址和必要的内部探针，不允许任意出站访问。安全组只开放：

| 端口 | 来源 | 用途 |
|---:|---|---|
| 80 | 公网 | HTTPS 跳转与 ACME |
| 443 | 公网 | HTTPS |
| 22 | 固定管理 IP、VPN 或堡垒机 | SSH |

不得开放 3000、8000、5432 或检查器端口。ECS 使用非 root 部署用户、SSH 密钥、最小权限、防火墙、安全更新、NTP 和云监控。

## HTML 内容卷

生产使用独立、持久化的 HTML 内容卷，和仓库内 `doc/snapshots/` 示例严格分离：

```text
/srv/company/
├── app/                    # Git checkout 或发布包
├── data/
│   ├── html/
│   │   ├── drafts/
│   │   ├── published/
│   │   └── withdrawn/
│   └── postgres/
├── backups/
├── logs/nginx/
├── releases/
└── secrets/.env
```

只有 FastAPI 能以读写方式挂载完整 HTML 内容卷。Nginx 只读挂载 `published/`；web 与 admin 不挂载内容目录；load-checker 只通过受控预览 URL 读取当前候选文件。文件发布或撤回必须与 PostgreSQL 索引、SHA-256、版本和审计执行补偿式业务事务。

## Nginx 路由与缓存

Nginx 将根域 301 到 `https://www.ayaseeri.com`，传递 `Host`、`X-Forwarded-For`、`X-Forwarded-Proto` 和请求 ID，并限制上传大小与超时。

- 独立、已发布的 HTML 响应设置明确的 `Content-Type: text/html; charset=utf-8`、ETag 和经过发布验证的短期 `Cache-Control`；撤回时必须能及时失效。
- 带内容哈希的前端静态资源可使用一年缓存和 `immutable`。
- `/admin/`、`/api/`、登录、草稿、预览和检查响应使用 `Cache-Control: no-store`，不得进入共享公开缓存。
- 受控预览附带 `X-Robots-Tag: noindex, nofollow`，且不能通过 Nginx 公网路由绕过认证。
- 配置 CSP、`X-Content-Type-Options: nosniff` 和合理的 Referrer Policy；启用 HSTS 前先确认所有相关域名均稳定支持 HTTPS。

检查与平滑重载：

```bash
docker compose -f compose.yaml -f compose.prod.yaml exec nginx nginx -t
docker compose -f compose.yaml -f compose.prod.yaml exec nginx nginx -s reload
```

## 阿里云 ECS

首版以单 ECS 为目标，建议从 2 vCPU、4 GiB 内存和 40–80 GiB ESSD 起步，再依据 Chromium 检查并发、数据库和磁盘指标扩容。操作系统选受支持的 Ubuntu LTS 或 Alibaba Cloud Linux，安装 Docker Engine 与 Compose Plugin。

启用云监控，至少覆盖 CPU、内存、磁盘、网络、进程存活和证书到期。生产备份至少复制一份到 ECS 之外的阿里云 OSS，并通过独立凭据与生命周期策略保护。

## www.ayaseeri.com 与 HTTPS

证书覆盖 `www.ayaseeri.com` 与 `ayaseeri.com`。可以使用 Certbot/Let's Encrypt 自动续期，或阿里云证书服务；私钥始终只读挂载。切换前先备份现站和现有 Nginx 配置，明确是替换现站还是先用隔离域名验收。

证书检查：

```bash
openssl s_client -connect www.ayaseeri.com:443 -servername www.ayaseeri.com </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
curl -fsSIL https://www.ayaseeri.com/healthz
```

续期任务必须在到期前自动运行，成功后执行 `nginx -t` 与平滑重载；失败立即告警。

## 首次部署

运行文件落地并在预生产验证后，目标步骤是：

1. 备份当前站点、Nginx 配置、数据库与 HTML 内容。
2. 创建 `/srv/company` 目录、部署用户、只读密钥和证书挂载。
3. 拉取固定版本镜像并执行 `docker compose ... config --quiet`。
4. 启动 PostgreSQL，执行 `alembic upgrade head`，初始化管理员。
5. 启动 api、load-checker、web、admin，等待内部健康检查。
6. 启动 Nginx，验证 HTTPS、缓存、安全头和非公开端口。
7. 导入一条测试 HTML，完成静态校验、可信加载检查、审核、发布与撤回演练。
8. 切换流量并记录发布版本、迁移版本和备份集 ID。

目标命令：

```bash
export RELEASE_SHA=<git-commit-sha>
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d postgres
docker compose -f compose.yaml -f compose.prod.yaml run --rm api alembic upgrade head
docker compose -f compose.yaml -f compose.prod.yaml up -d --remove-orphans
docker compose -f compose.yaml -f compose.prod.yaml ps
curl -fsS https://www.ayaseeri.com/healthz
```

## 日常发布与回滚

每次发布记录不可变镜像标签、Git SHA、数据库迁移版本和内容备份集 ID。发布后 smoke test 至少覆盖：

```bash
curl -fsS https://www.ayaseeri.com/healthz
curl -fsSI https://www.ayaseeri.com/snapshots/CN/600519/2025-12-31.html
curl -fsSI https://www.ayaseeri.com/admin/
docker compose -f compose.yaml -f compose.prod.yaml ps
docker compose -f compose.yaml -f compose.prod.yaml logs --since=10m nginx api load-checker
```

回滚步骤：

1. 停止发布写入并记录故障版本。
2. 将 Compose 镜像标签和配置切回上一已验证版本。
3. 若迁移明确可逆则按迁移说明降级；否则选择发布前同一备份集。
4. 必须把 PostgreSQL 元数据与 HTML 内容卷恢复到该备份集的同一逻辑点，不能只恢复一侧。
5. 启动旧版本，执行健康检查、独立 HTML、管理登录、可信加载门禁和撤回可见性 smoke test。

## 备份与恢复

备份必须覆盖 PostgreSQL 元数据与 HTML 内容卷，并在同一逻辑点生成一个带唯一 ID 的备份集。维护模式必须阻断并排空所有会修改索引或 HTML 内容卷的操作，包括导入、扫描、校验结果写入、发布、撤回和删除；不能只冻结发布。等待这些事务全部结束并记录数据库版本与内容清单后，才在保持全量内容写入冻结期间完成两侧快照：

```bash
export BACKUP_ID="$(date -u +%Y%m%dT%H%M%SZ)"
docker compose -f compose.yaml -f compose.prod.yaml exec -T api \
  company-api maintenance enable --wait
docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
  sh -c 'pg_dump --format=custom --dbname="$POSTGRES_DB"' \
  > "/srv/company/backups/$BACKUP_ID.postgres.dump"
tar -C /srv/company/data -czf "/srv/company/backups/$BACKUP_ID.html.tar.gz" html
sha256sum "/srv/company/backups/$BACKUP_ID.postgres.dump" \
  "/srv/company/backups/$BACKUP_ID.html.tar.gz" > "/srv/company/backups/$BACKUP_ID.sha256"
docker compose -f compose.yaml -f compose.prod.yaml exec -T api \
  company-api maintenance disable
```

生产脚本必须用 trap 保证成功或失败都能安全退出维护模式，并保存 release SHA、Alembic 版本、内容清单与时间点；只有两份文件和校验和全部成功，备份集才标记完成。日备份保留 14 天、周备份保留 8 周，至少一份复制到 ECS 外的 OSS；每季度恢复演练。

恢复先在隔离环境验证校验和与清单，再停止公开入口、api 和 load-checker，删除并重新创建空数据库，同时清空 HTML 目录；随后只使用同一 `BACKUP_ID` 的两个文件恢复：

```bash
sha256sum -c "/srv/company/backups/$BACKUP_ID.sha256"
docker compose -f compose.yaml -f compose.prod.yaml stop nginx api load-checker
rm -rf /srv/company/data/html
docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
  sh -ceu 'dropdb --if-exists --force --username="$POSTGRES_USER" "$POSTGRES_DB"; \
    createdb --username="$POSTGRES_USER" --owner="$POSTGRES_USER" "$POSTGRES_DB"'
docker compose -f compose.yaml -f compose.prod.yaml exec -T postgres \
  sh -c 'pg_restore --exit-on-error --no-owner --dbname="$POSTGRES_DB"' \
  < "/srv/company/backups/$BACKUP_ID.postgres.dump"
tar -C /srv/company/data -xzf "/srv/company/backups/$BACKUP_ID.html.tar.gz"
docker compose -f compose.yaml -f compose.prod.yaml up -d api load-checker nginx
```

恢复后核对索引路径、文件 SHA-256、发布/撤回状态和审计记录，再运行 smoke test；验证失败不得切换流量。

## 健康检查、日志与告警

- Nginx `/healthz` 只证明入口存活；FastAPI readiness 还要检查数据库、HTML 根目录权限和内部检查任务队列。
- load-checker 健康检查验证 worker 可接任务、Chromium 可启动和内部认证可用，但不暴露公网详情。
- Docker 使用 `json-file` 或等价驱动的大小/文件数轮转；Nginx access/error 日志在宿主机轮转。
- 应用结构化日志包含 `request_id`、任务 ID 和结果摘要，不记录 HTML 正文、密码、Cookie、Session、CSRF、内部令牌或私钥。
- 对容器重启、readiness 失败、5xx、检查任务堆积、备份失败、磁盘 80%、证书剩余 30 天和日志异常量告警。
- 每次发布检查 `docker compose ps`、近十分钟错误日志、公开 HTML、管理端不缓存、API 不缓存和证书有效期。
