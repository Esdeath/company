# Docker 与阿里云部署设计

## 部署目标

首版运行在一台阿里云 ECS：Nginx 对外提供 HTTPS，Nuxt、管理端、FastAPI 和 PostgreSQL 只在 Docker 网络中通信。

目标域名为 `www.ayaseeri.com`。正式切换前必须备份当前站点，并确认是替换现站还是先通过独立子域名验证。

## 服务组成

```text
internet
  ↓ 80 / 443
nginx
  ├── /          → web:3000
  ├── /admin/    → admin:80
  └── /api/      → api:8000
                         ↓
                    postgres:5432
                         ↕
                    content volume
```

| 服务 | 公网端口 | 健康检查 | 持久化 |
|---|---:|---|---|
| `nginx` | 80、443 | `/healthz` | 证书、日志 |
| `web` | 无 | Nuxt 健康页 | 无 |
| `admin` | 无 | 静态文件响应 | 无 |
| `api` | 无 | `/api/health/ready` | `content/` |
| `postgres` | 无 | `pg_isready` | PostgreSQL data |

## Compose 文件

- `compose.yaml`：本地开发和基础服务定义。
- `compose.prod.yaml`：生产镜像、资源限制、只读文件系统、日志和重启策略。
- `.env.example`：可提交的变量说明。
- `.env`：本地密钥，不提交。
- `/srv/company/secrets/.env`：生产密钥，只允许部署用户读取。

## 本地开发

### 首次启动

```bash
cp .env.example .env
docker compose up -d postgres
docker compose run --rm api alembic upgrade head
docker compose up --build
```

访问地址：

- 公开前台：`http://localhost/`
- 管理端：`http://localhost/admin/`
- API 文档：`http://localhost/api/docs`

### 常用命令

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f web
docker compose restart api
docker compose down
```

默认不使用 `down -v`，避免删除 PostgreSQL 和内容卷。

## 环境变量

### 必填

| 变量 | 说明 |
|---|---|
| `APP_ENV` | `development` 或 `production` |
| `PUBLIC_BASE_URL` | 公开站点地址 |
| `DATABASE_URL` | PostgreSQL 连接字符串 |
| `POSTGRES_DB` | 数据库名 |
| `POSTGRES_USER` | 数据库用户 |
| `POSTGRES_PASSWORD` | 数据库密码 |
| `SESSION_SECRET` | 会话密钥，至少 32 字节随机值 |
| `CSRF_SECRET` | CSRF 密钥，至少 32 字节随机值 |
| `CONTENT_ROOT` | 容器内内容根目录 |

### 生产建议值

```dotenv
APP_ENV=production
PUBLIC_BASE_URL=https://www.ayaseeri.com
CONTENT_ROOT=/data/content
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
TRUSTED_HOSTS=www.ayaseeri.com,ayaseeri.com
```

密钥使用 `openssl rand -base64 48` 生成，不在文档、Compose 或镜像中写默认生产密钥。

## 网络

定义两个网络：

- `edge`：Nginx、web、admin、api。
- `backend`：api、postgres，设为 internal。

PostgreSQL 不加入 `edge`。生产 Compose 不使用 `ports` 暴露 web、admin、api 和 postgres。

## 文件挂载

```text
/srv/company/
├── app/                       # Git checkout 或发布包
├── data/
│   ├── content/
│   │   ├── inbox/
│   │   ├── drafts/
│   │   └── published/
│   └── postgres/
├── backups/
│   ├── content/
│   └── postgres/
├── logs/nginx/
└── secrets/.env
```

- `api` 以读写方式挂载 `/srv/company/data/content:/data/content`。
- `web` 和 `admin` 不挂载内容目录。
- PostgreSQL 使用独立 volume 或绑定目录。
- 容器不直接挂载 Docker socket。

## 阿里云 ECS 基线

建议起步配置：

- 2 vCPU、4 GiB 内存。
- 40–80 GiB ESSD 云盘。
- Ubuntu LTS 或 Alibaba Cloud Linux 的受支持版本。
- Docker Engine 与 Compose Plugin。
- 开启云监控和磁盘告警。

系统层：

- 创建非 root 部署用户。
- 禁止 SSH 密码登录，使用密钥。
- 设置自动安全更新或固定维护窗口。
- 配置时区和 NTP。
- 防火墙与安全组保持相同最小开放范围。

## 安全组

| 端口 | 来源 | 用途 |
|---:|---|---|
| 80 | `0.0.0.0/0`、`::/0` | HTTP 跳转和 ACME |
| 443 | `0.0.0.0/0`、`::/0` | HTTPS |
| 22 | 管理员固定 IP | SSH |

不要开放 3000、8000、5432。若管理员 IP 经常变化，优先使用 VPN、堡垒机或临时安全组规则。

## Nginx 路由

核心行为：

```nginx
server {
    listen 80;
    server_name ayaseeri.com www.ayaseeri.com;
    return 301 https://www.ayaseeri.com$request_uri;
}

server {
    listen 443 ssl http2;
    server_name www.ayaseeri.com;

    client_max_body_size 2m;

    location /api/ {
        proxy_pass http://api:8000/api/;
    }

    location /admin/ {
        proxy_pass http://admin:80/;
    }

    location / {
        proxy_pass http://web:3000;
    }
}
```

完整配置还需要：

- 传递 `Host`、`X-Forwarded-For` 和 `X-Forwarded-Proto`。
- API 动态响应默认不缓存。
- 带内容哈希的静态资源缓存一年并标记 immutable。
- HTML 使用短缓存或不缓存。
- 添加 HSTS 前先确认 HTTPS 和所有子域名策略。
- 设置 CSP、`X-Content-Type-Options` 和合理的 Referrer Policy。

## HTTPS

域名证书需要覆盖：

- `www.ayaseeri.com`
- `ayaseeri.com`

可选择：

1. Certbot + Let's Encrypt 自动续期。
2. 阿里云证书服务，将证书以只读文件挂载到 Nginx。

部署前检查：

```bash
openssl s_client -connect www.ayaseeri.com:443 -servername www.ayaseeri.com </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

2026-07-16 的检查记录显示 `www.ayaseeri.com` 旧证书已过期。正式上线前必须更新，不能复用旧文件。`buffett.ayaseeri.com` 使用独立的 Cloudflare Pages 证书，不受本项目证书直接控制。

证书续期后执行：

```bash
nginx -t
docker compose -f compose.yaml -f compose.prod.yaml exec nginx nginx -s reload
```

## 首次部署

```text
1. 备份 www.ayaseeri.com 当前站点和 Nginx 配置
2. 准备 ECS 目录、部署用户和 secrets/.env
3. 拉取代码或上传发布包
4. 构建或拉取固定版本镜像
5. 启动 PostgreSQL
6. 执行 Alembic 迁移
7. 初始化管理员
8. 启动 api、web、admin
9. 验证内部健康检查
10. 配置并验证 Nginx 与新证书
11. 切换流量
12. 完成真实 A 股、港股快照验收
```

初始化管理员：

```bash
docker compose -f compose.yaml -f compose.prod.yaml run --rm api \
  company-api admin create --username admin
```

密码通过交互输入或一次性秘密文件传入，不出现在 shell 历史中。

## 日常发布

镜像必须使用不可变版本，例如 Git commit SHA，不用 `latest` 作为生产发布依据。

```bash
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml run --rm api alembic upgrade head
docker compose -f compose.yaml -f compose.prod.yaml up -d --remove-orphans
docker compose -f compose.yaml -f compose.prod.yaml ps
```

验证：

- `/api/health/ready` 返回成功。
- 首页和一条快照详情返回 `200`。
- `/admin/` 未登录时跳转登录页。
- TLS 证书域名和有效期正确。
- Nginx、API 和数据库没有新的错误日志。

## 回滚

1. 保留上一版镜像标签和 Compose 配置。
2. 应用代码回滚到上一版本。
3. 如果迁移可逆，按迁移说明降级；否则恢复发布前数据库备份。
4. `content/` 与数据库必须恢复到同一备份时间点。
5. 启动旧版本并执行健康检查。

不要只恢复数据库而保留较新的 Markdown，或反过来。

## 备份

每天执行：

```bash
pg_dump --format=custom --file=/backups/postgres/company-$(date +%F).dump company
tar -czf /backups/content/content-$(date +%F).tar.gz -C /data content
```

生产脚本中使用固定时区和安全的临时文件名。建议策略：

- 日备份保留 14 天。
- 周备份保留 8 周。
- 至少一份复制到 ECS 之外的 OSS。
- 每季度执行一次恢复演练。

## 日志与告警

- Docker 日志启用 `json-file` 轮转。
- Nginx access/error 日志写入宿主机目录并轮转。
- 应用日志使用 JSON，包含 `request_id`，不含密码、Cookie 和 Markdown 正文。
- 监控磁盘使用率、容器重启、数据库连接、5xx 和证书到期日。
- 磁盘使用率 80% 和证书剩余 30 天时告警。
