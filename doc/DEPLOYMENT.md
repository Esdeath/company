# 阿里云 ECS 部署与运维

## 已验证状态

本项目已在一台 CentOS Stream 9、x86_64 的阿里云 ECS 上完成部署。公开资料库和受保护的管理端都通过 `https://www.ayaseeri.com/` 提供服务。管理员使用 Argon2 密码登录，FastAPI 把会话保存在 PostgreSQL，并用 `HttpOnly` Cookie 与会话绑定的 CSRF 令牌保护全部写操作；管理端不再依赖 SSH 端口转发。

实际链路如下：

```text
Internet :80/:443
  └── 宿主机 Nginx（/usr/local/nginx）
        ├── /admin/ HTTPS 管理入口
        ├── 管理员与普通用户认证、评论写入按 IP 限速
        ├── /api/ 交给 FastAPI 做会话与 CSRF 校验
        └── 127.0.0.1:8080
              └── edge 容器
                    ├── web:3000
                    ├── admin:8080
                    └── api:8000 ── postgres:5432
```

在 Compose 内，edge Nginx 是唯一面向宿主机的容器，而且只绑定回环地址。宿主机 Nginx 是唯一公网入口。PostgreSQL 不加入 `edge`，只在 `backend` 网络与 API 通信；当前 Compose 额外把数据库绑定到 `127.0.0.1:5432` 供本机诊断，不得将它开放到公网。

## 仓库中的部署资产

| 路径 | 用途 |
| --- | --- |
| `infra/aliyun-ecs/nginx-bootstrap.conf` | 首次申请证书前的 HTTP 配置 |
| `infra/aliyun-ecs/nginx.conf` | HTTPS、管理端代理和登录限速配置 |
| `infra/aliyun-ecs/systemd/nginx.service` | 源码安装 Nginx 的开机服务 |
| `infra/aliyun-ecs/systemd/company-backup.*` | 每日本地备份服务与定时器 |
| `infra/aliyun-ecs/letsencrypt/reload-nginx.sh` | 证书续签后的 Nginx 重载钩子 |
| `scripts/build-ecs-image-bundle.sh` | 在 Mac 构建 linux/amd64 离线镜像包 |
| `scripts/load-ecs-image-bundle.sh` | 在 ECS 导入镜像并启动 Compose |
| `scripts/company-backup.sh` | PostgreSQL 与内容卷同批备份 |

这些文件不包含密码、AccessKey、证书私钥或 ECS 公网 IP。

## ECS 目录

```text
/srv/company/
├── app/                         # rsync 上传的仓库
├── backups/                     # 本地备份集与 latest 软链接
├── secrets/company.env          # 600、root:root
└── company-ecs-amd64-images.tar.gz
```

Docker 使用两个命名卷：

- `company-research-library_postgres_data`
- `company-research-library_content_data`

不要用 `docker compose down -v`，也不要手工删除这两个卷。

## 网络和主机准备

阿里云安全组只开放：

| 端口 | 来源 | 用途 |
| ---: | --- | --- |
| 80 | 公网 | ACME 与 HTTPS 跳转 |
| 443 | 公网 | 公开资料库 |
| 22 | 固定管理 IP，条件允许时使用 | SSH 运维 |

不得开放 3000、8000、8080、5432 或 18080。Docker Engine 和 Compose 必须启用开机启动：

```bash
dnf install -y dnf-plugins-core
dnf config-manager --add-repo \
  https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
dnf install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version
docker compose version
```

中国大陆网络无法稳定访问 Docker Hub 时，在 `/etc/docker/daemon.json` 配置自己阿里云账号提供的镜像加速地址。不要把账号专属地址或凭据提交到仓库。

本次已验证服务器原先已有源码安装的 Nginx，主目录为 `/usr/local/nginx`。仓库内宿主机配置和 systemd 单元均以这个路径为准；使用 RPM 安装的 Nginx 时，必须先按实际二进制、配置和 PID 路径调整，不可直接复制。

## 首次部署

### 1. 上传代码

在 ECS 创建目录：

```bash
mkdir -p /srv/company/app /srv/company/backups /srv/company/secrets
```

在 Mac 仓库根目录执行：

```bash
rsync -az --delete \
  --exclude='.git/' \
  --exclude='.worktrees/' \
  --exclude='.env' \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='.nuxt/' \
  --exclude='.output/' \
  --exclude='dist/' \
  --exclude='var/' \
  ./ root@<ECS-IP>:/srv/company/app/
```

### 2. 创建管理员密码与生产环境文件

先在 Mac 仓库根目录运行下面的命令，交互式输入一个不少于 12 个字符的独立管理员密码：

```bash
make admin-password-hash
```

复制脚本输出中单引号里面的完整 Argon2 哈希。然后在 ECS 执行；终端不会回显粘贴的哈希，随机数据库密码和管理员哈希只写进 root 可读文件，不提交 Git：

```bash
POSTGRES_PASSWORD="$(openssl rand -hex 32)"
USER_TOKEN_SIGNING_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
read -r -s -p "粘贴 Argon2 管理员哈希：" ADMIN_PASSWORD_HASH
echo
install -m 600 /dev/null /srv/company/secrets/company.env
{
  printf '%s\n' 'POSTGRES_DB=company' 'POSTGRES_USER=company'
  printf 'POSTGRES_PASSWORD=%s\n' "$POSTGRES_PASSWORD"
  printf 'DATABASE_URL=postgresql+psycopg://company:%s@postgres:5432/company\n' "$POSTGRES_PASSWORD"
  printf '%s\n' 'ADMIN_USERNAME=admin'
  printf "ADMIN_PASSWORD_HASH='%s'\n" "$ADMIN_PASSWORD_HASH"
  printf '%s\n' \
    'CORS_ORIGINS=http://localhost:3000,http://localhost:5173' \
    'CONTENT_ROOT=/data/content' \
    'SESSION_COOKIE_SECURE=true' \
    'SESSION_LIFETIME_SECONDS=43200' \
    'APP_ENVIRONMENT=production' \
    'USER_REGISTRATION_ENABLED=false' \
    'COMMENT_WRITES_ENABLED=true' \
    'USER_SESSION_LIFETIME_SECONDS=2592000' \
    'EMAIL_BACKEND=smtp' \
    'SMTP_HOST=' \
    'SMTP_PORT=587' \
    'SMTP_USERNAME=' \
    'SMTP_PASSWORD=' \
    'SMTP_STARTTLS=true' \
    'SMTP_SENDER=' \
    'PUBLIC_BASE_URL=https://www.ayaseeri.com' \
    'EMAIL_DISPATCH_INTERVAL_SECONDS=2' \
    'EMAIL_MAX_ATTEMPTS=8'
  printf 'USER_TOKEN_SIGNING_KEY=%s\n' "$USER_TOKEN_SIGNING_KEY"
} > /srv/company/secrets/company.env
chown root:root /srv/company/secrets/company.env
ln -sfn /srv/company/secrets/company.env /srv/company/app/.env
```

管理端与 API 通过同一个 HTTPS 域名通信，因此不需要把公网域名加入 CORS。`SESSION_COOKIE_SECURE=true` 不能在生产中关闭。`USER_TOKEN_SIGNING_KEY` 必须长期保存，轮换会使尚未使用的邮件链接失效。不要输出或截图完整环境文件。

### 3. 配置 SMTP 并分阶段开放注册

首次迁移和部署必须保持 `USER_REGISTRATION_ENABLED=false`。填写 SMTP 服务商提供的 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD`、`SMTP_STARTTLS` 和 `SMTP_SENDER`，并把 `PUBLIC_BASE_URL` 设为无路径的 HTTPS 站点地址。`SMTP_PASSWORD` 只存在 `/srv/company/secrets/company.env`；日常部署会原样保留 SMTP 凭据，不会写入仓库或终端输出。

发件域名的 SPF 与 DKIM 记录由所选 SMTP 服务商提供和验证。先发送注册验证与密码重置测试邮件，确认链接回到正确的 HTTPS 域名，并观察发件箱没有持续失败，再把 `USER_REGISTRATION_ENABLED=true`。不要在 SMTP 尚未工作时开放注册。`EMAIL_DISPATCH_INTERVAL_SECONDS` 控制领取间隔，`EMAIL_MAX_ATTEMPTS` 控制最大尝试次数；失败任务保存在 PostgreSQL，API 重启后继续重试。

### 4. 构建和传输离线镜像

ECS 为 x86_64，而开发 Mac 可能是 Apple Silicon。Mac 上使用 Docker Desktop 构建单架构镜像包：

```bash
./scripts/build-ecs-image-bundle.sh \
  /tmp/company-ecs-amd64-images.tar.gz
```

脚本会构建三个应用镜像以及 PostgreSQL、Nginx 的 linux/amd64 包装镜像，检查架构，生成 gzip 和 SHA-256 文件。上传两者：

```bash
rsync -avP \
  /tmp/company-ecs-amd64-images.tar.gz \
  /tmp/company-ecs-amd64-images.tar.gz.sha256 \
  root@<ECS-IP>:/srv/company/
```

ECS 上校验并启动：

```bash
cd /srv/company
sha256sum -c company-ecs-amd64-images.tar.gz.sha256
/srv/company/app/scripts/load-ecs-image-bundle.sh \
  /srv/company/company-ecs-amd64-images.tar.gz
```

导入脚本会在已有应用镜像时先增加带时间的 `rollback-*` 标签，再用 `--no-build --pull never` 启动，避免 ECS 再次访问 Docker Hub。首次部署没有上一版镜像，因此不会生成可用的回滚标签。

### 5. 配置域名、Nginx 与 HTTPS

域名 `ayaseeri.com` 和 `www.ayaseeri.com` 的 A 记录必须指向 ECS。首次申请证书前：

```bash
cp -a /usr/local/nginx/conf \
  /usr/local/nginx/conf.backup-$(date +%Y%m%d-%H%M%S)
mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
chmod -R 755 /var/www/letsencrypt
cp /srv/company/app/infra/aliyun-ecs/nginx-bootstrap.conf \
  /usr/local/nginx/conf/nginx.conf
nginx -t && nginx -s reload
```

CentOS Stream 9 可从 EPEL 安装 Certbot，然后使用 webroot 模式，不让 Certbot 修改自定义 Nginx：

```bash
dnf install -y epel-release certbot
certbot certonly \
  --webroot \
  --webroot-path /var/www/letsencrypt \
  --cert-name ayaseeri.com \
  -d ayaseeri.com \
  -d www.ayaseeri.com
```

证书成功后切换最终配置：

```bash
cp /srv/company/app/infra/aliyun-ecs/nginx.conf \
  /usr/local/nginx/conf/nginx.conf
nginx -t && nginx -s reload
```

安装续签钩子并启用定时器：

```bash
install -m 750 \
  /srv/company/app/infra/aliyun-ecs/letsencrypt/reload-nginx.sh \
  /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
systemctl enable --now certbot-renew.timer
certbot renew --dry-run
```

源码安装的 Nginx 需要额外注册 systemd。已有手动进程时先优雅退出：

```bash
install -m 644 \
  /srv/company/app/infra/aliyun-ecs/systemd/nginx.service \
  /etc/systemd/system/nginx.service
systemctl daemon-reload
systemctl enable nginx
nginx -s quit
sleep 2
systemctl start nginx
```

### 6. 启用本地备份

```bash
install -m 750 \
  /srv/company/app/scripts/company-backup.sh \
  /usr/local/sbin/company-backup
install -m 644 \
  /srv/company/app/infra/aliyun-ecs/systemd/company-backup.service \
  /srv/company/app/infra/aliyun-ecs/systemd/company-backup.timer \
  /etc/systemd/system/
systemctl daemon-reload
/usr/local/sbin/company-backup
systemctl enable --now company-backup.timer
```

备份脚本短暂暂停 API 写入，将 PostgreSQL archive dump 和 `content_data` 内容卷放入同一个时间戳目录，校验两份文件，保留 30 天并更新 `latest` 软链接。PostgreSQL 备份包含普通用户、评论、举报、通知、邮件发件箱和限流记录；内容卷包含上传资料。恢复演练必须同时恢复两者。目前只完成 ECS 本地备份；它不能防止整台 ECS 或云盘丢失，资料规模扩大后应再复制到 OSS。

## 管理端访问

打开 `https://www.ayaseeri.com/admin/`，输入 `ADMIN_USERNAME` 和生成哈希时使用的原始密码。登录成功后浏览器收到 Secure、HttpOnly、SameSite=Strict 会话 Cookie；关闭 SSH 不影响管理端。仍然不要在安全组中开放 8080、8000 或 5432。

## 发布更新

已经完成首次部署后，推荐在 Mac 仓库根目录只运行：

```bash
make deploy-aliyun
```

默认 SSH 目标是 `root@www.ayaseeri.com`。如果只能通过 IP 登录：

```bash
DEPLOY_TARGET=root@<ECS-IP> make deploy-aliyun
```

脚本会依次运行本地 `make check`、复用一个 SSH 连接、构建 linux/amd64 离线镜像、创建 ECS 发布前备份、rsync 代码、上传并校验镜像、补齐安全环境变量、运行 Alembic migration、启动 Compose、更新 Nginx，最后验证公开首页、管理端、匿名会话和未授权写入的 401。首次社区版本发布会在远端生成并保存 32 字节 URL-safe `USER_TOKEN_SIGNING_KEY`；后续发布保留该密钥和已有 SMTP 凭据，并把注册恢复为关闭状态，必须在测试邮件成功后再次手工开启。使用 root 密码登录时通常只需输入一次。

社区功能上线顺序是：保持注册关闭并做备份，运行增量 Alembic migration，部署 API、Web 和 Admin，更新 Nginx，配置 SMTP 与发件域名，发送测试邮件，最后开放注册。上线初期监控待审核评论、429 命中、发件箱失败与积压。

第一次从旧版升级到管理员认证时，脚本会提示创建生产管理员密码。后续发布会保留原密码；需要主动更换时运行：

```bash
./scripts/deploy-aliyun-ecs.sh --rotate-admin-password
```

常用辅助参数：

```bash
# 只查看将执行的步骤
./scripts/deploy-aliyun-ecs.sh --dry-run

# 已经单独跑过检查时跳过 make check
./scripts/deploy-aliyun-ecs.sh --skip-checks
```

如果公网验收失败，脚本会恢复上一份宿主机 Nginx 配置并停止。应用导入脚本仍会保留 `rollback-<时间>` 镜像标签，供后续按“应用回滚”处理。首次安装 Docker、申请证书和建立 `/srv/company` 目录仍按前面的“首次部署”执行一次。

### 手工验收命令

验收命令：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  -f /srv/company/app/compose.yaml ps
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/health/ready
curl --fail https://www.ayaseeri.com/ > /dev/null
curl -s -o /dev/null -w '%{http_code}\n' \
  https://www.ayaseeri.com/admin/
curl --fail https://www.ayaseeri.com/api/v1/auth/session
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST -H 'Content-Type: application/json' \
  --data '{"name":"unauthorized"}' \
  https://www.ayaseeri.com/api/v1/companies
```

`/admin/` 必须输出 `200`，未登录 session JSON 必须包含 `"authenticated":false`，最后一个未认证写入请求必须输出 `401`。再用浏览器实际登录、创建或上传一份测试资料并退出，确认退出后刷新会回到登录页。`/api/health/live` 与 `/api/health/ready` 是唯一不版本化的基础设施例外，业务 API 使用 `/api/v1`。

## 应用回滚

社区功能异常时先设置 `USER_REGISTRATION_ENABLED=false` 和 `COMMENT_WRITES_ENABLED=false`，重建 API 容器。后一个开关只拒绝发布、编辑、删除和举报，已发布评论仍可读取，因此可以先回到只读评论而不丢数据。普通应用回滚不要执行破坏性 Alembic 迁移；旧应用会忽略新增表，PostgreSQL 中的社区数据仍随备份保留。

已有旧版应用镜像时，导入脚本会输出本次生成的 `rollback-<时间>` 标签。新版本异常且没有不兼容数据库迁移时，重新标记三个应用镜像：

```bash
ROLLBACK_TAG=<导入脚本输出的标签>
docker tag company-research-library-api:$ROLLBACK_TAG company-research-library-api:latest
docker tag company-research-library-web:$ROLLBACK_TAG company-research-library-web:latest
docker tag company-research-library-admin:$ROLLBACK_TAG company-research-library-admin:latest
docker compose \
  --env-file /srv/company/secrets/company.env \
  -f /srv/company/app/compose.yaml \
  up -d --no-build --pull never
```

数据库结构发生不兼容变化时，不要只回滚应用镜像，应使用发布前备份恢复数据库和内容卷。

## 备份恢复

恢复是破坏性操作，先复制当前卷或创建新的临时备份。选择同一个时间戳目录，先校验：

```bash
BACKUP=/srv/company/backups/<时间戳>
cd "$BACKUP"
sha256sum -c SHA256SUMS
```

停止 API，恢复数据库和内容卷，再启动并检查：

```bash
cd /srv/company/app
docker compose --env-file /srv/company/secrets/company.env stop api
docker compose --env-file /srv/company/secrets/company.env exec -T postgres sh -lc \
  'pg_restore --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < "$BACKUP/postgres.dump"
docker run --rm --pull never --user 0:0 \
  -v company-research-library_content_data:/data \
  nginxinc/nginx-unprivileged:1.30.4-alpine \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'
gzip -dc "$BACKUP/content.tar.gz" | docker run --rm --pull never --user 0:0 -i \
  -v company-research-library_content_data:/data \
  nginxinc/nginx-unprivileged:1.30.4-alpine \
  tar -xzf - -C /data
docker compose --env-file /srv/company/secrets/company.env start api
curl --fail http://127.0.0.1:8080/api/health/ready
```

## 日常检查

```bash
systemctl --failed
systemctl list-timers --all | grep -E 'company-backup|certbot'
journalctl -u company-backup.service --no-pager -n 100
df -h /
docker compose \
  --env-file /srv/company/secrets/company.env \
  -f /srv/company/app/compose.yaml ps
```

启用云监控，至少关注 CPU、内存、磁盘、容器重启、5xx、备份失败和证书到期。SSH 当前按使用者选择保留 root 登录；即便继续使用 root，也建议改为密钥认证并把安全组 22 端口来源限制到固定管理 IP。
