# 从本地 Docker Compose 到阿里云 ECS：企业研究资料库部署实录

> 记录日期：2026-07-21  
> 项目栈：Nuxt、Vue/Vite、FastAPI、PostgreSQL、Docker Compose、Nginx  
> 服务器：阿里云 ECS，CentOS Stream 9，x86_64  
> 发布边界：公网只读，管理端通过 SSH 隧道访问

## 摘要

这次部署把一个运行在 Mac 上的五服务 Docker Compose 项目搬到阿里云 ECS。公开站点使用备案域名和 HTTPS，管理端没有登录系统，因此不能暴露到公网。宿主机 Nginx 只开放公开阅读接口，拦截 `/admin/` 和 API 写方法；管理员通过 SSH 本地端口转发进入 Compose 的回环端口。

部署过程遇到了几类典型问题：Docker 官方仓库连接被重置、Docker Hub 镜像拉取超时、Apple Silicon 与 ECS 的 CPU 架构不同、`docker save` 导出的镜像不完整、FastAPI 因 CORS 配置拒绝启动、Nginx 使用源码安装目录且没有 systemd 服务、旧 HTTPS 证书过期、DNF 进程被 `Ctrl+Z` 暂停并占用锁。

为避免泄露信息，文中的服务器地址统一写成 `<ECS-IP>`，数据库密码写成 `<随机密码>`，阿里云账号专属镜像加速地址写成 `<镜像加速地址>`。

## 一、项目和部署目标

项目包含五个 Compose 服务：

| 服务 | 技术 | 职责 |
| --- | --- | --- |
| `web` | Nuxt | 公开公司目录和资料阅读页 |
| `admin` | Vue + Vite | 创建公司、上传 HTML/Markdown、维护资料 |
| `api` | FastAPI | 公司、资料和内容接口 |
| `postgres` | PostgreSQL | 保存公司和文档索引 |
| `edge` | Nginx 容器 | 在 Compose 内分发 `/`、`/admin/`、`/api/` |

HTML 文件按原文保存并嵌入阅读器。Markdown 文件同时保存 `source.md`，后端使用统一模板生成 `rendered.html`。数据库只保存索引，文件正文存入 Docker 内容卷。

本轮部署设定了四个约束：

1. 公网只能阅读资料。
2. 管理端和写接口不能直接暴露。
3. PostgreSQL 与内容文件必须持久化。
4. ECS 无法访问 Docker Hub 时仍能更新版本。

## 二、最终架构

```text
Internet :80/:443
  └── 宿主机 Nginx（/usr/local/nginx）
        ├── HTTP 跳转 HTTPS
        ├── 公网 /admin/ 返回 404
        ├── 公网 /api/ 仅允许 GET、HEAD、OPTIONS
        └── 127.0.0.1:8080
              └── edge 容器
                    ├── web:3000
                    ├── admin:8080
                    └── api:8000
                           └── postgres:5432

管理员 Mac
  └── SSH -L 18080:127.0.0.1:8080
        └── http://127.0.0.1:18080/admin/
```

阿里云建议把安全组当作白名单，只开放业务需要的端口。公开 Web 服务需要 80 和 443，SSH 使用 22；数据库、内部 API 和管理端端口保持关闭。[阿里云 ECS 安全组指南](https://help.aliyun.com/en/ecs/user-guide/security-groups-for-different-use-cases)

安全组按以下目标配置入方向规则：

| 端口 | 来源 | 用途 |
| ---: | --- | --- |
| 80 | `0.0.0.0/0` | ACME 验证与 HTTPS 跳转 |
| 443 | `0.0.0.0/0` | 公开资料库 |
| 22 | 管理 IP，条件允许时限制为 `/32` | SSH 与本地端口转发 |

3000、8000、8080、5432、18080 不加入安全组。Linux ECS 也不需要开放 Windows RDP 的 3389。

## 三、服务器环境盘点

部署前先确认操作系统、架构、身份、磁盘和已有软件：

```bash
cat /etc/os-release
uname -m
whoami
docker --version 2>/dev/null || echo "Docker 未安装"
docker compose version 2>/dev/null || echo "Docker Compose 未安装"
nginx -v 2>&1 || echo "Nginx 未安装"
df -h /
```

这些命令分别回答六个问题：

| 命令 | 含义 |
| --- | --- |
| `cat /etc/os-release` | 读取 Linux 发行版和版本 |
| `uname -m` | 查看 CPU 架构，`x86_64` 对应 Docker 的 `amd64` |
| `whoami` | 确认当前用户，本次按使用者选择保留 `root` |
| `docker --version` | 检查 Docker Engine |
| `docker compose version` | 检查 Compose 插件 |
| `df -h /` | 查看根分区容量和使用率 |

现场结果如下：

- CentOS Stream 9，x86_64。
- Nginx 1.28.0 已安装。
- Docker 和 Compose 尚未安装。
- 根分区 40 GB，剩余空间约 36 GB。

## 四、安装 Docker：官方仓库连接被重置

### 4.1 症状

使用 Docker 官方 CentOS 仓库安装时，DNF 在下载 `containerd.io`、`docker-ce` 和 Buildx 插件时多次报错：

```text
Curl error (35): SSL connect error
OpenSSL SSL_connect: Connection reset by peer
No more mirrors to try
```

包管理器本身能工作，DNF 数据库没有损坏。失败集中在 `download.docker.com:443`，指向 ECS 到 Docker 官方站点的网络链路。

### 4.2 处理

Docker 官方文档要求在 CentOS 上先配置 RPM 仓库，再安装 Engine、CLI、containerd、Buildx 和 Compose 插件。[Docker Engine on CentOS](https://docs.docker.com/engine/install/centos/)

本次把仓库地址切换到阿里云 Docker CE 镜像：

```bash
dnf install -y dnf-plugins-core

dnf config-manager --add-repo \
  https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo

dnf install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

systemctl enable --now docker
```

阿里云开发者社区提供了 Docker CE 镜像地址和 CentOS 安装示例。[阿里云 Docker CE 镜像](https://developer.aliyun.com/mirror/docker-ce/)

命令含义：

- `dnf-plugins-core` 提供 `dnf config-manager`。
- `--add-repo` 将软件仓库写入 `/etc/yum.repos.d/`。
- `systemctl enable --now docker` 同时启动 Docker 并设置开机启动。

安装完成后验证：

```bash
docker --version
docker compose version
systemctl is-active docker
```

现场版本为 Docker 29.6.2、Docker Compose v5.3.1，服务状态为 `active`。

## 五、上传项目和隔离秘密

### 5.1 服务器目录

```bash
mkdir -p \
  /srv/company/app \
  /srv/company/backups \
  /srv/company/secrets
```

目录职责如下：

- `/srv/company/app` 保存代码和 Compose 文件。
- `/srv/company/secrets` 保存生产环境变量。
- `/srv/company/backups` 保存数据库与内容卷备份。

### 5.2 从 Mac 上传代码

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
  /Users/<USER>/Desktop/code/company/ \
  root@<ECS-IP>:/srv/company/app/
```

参数说明：

| 参数 | 作用 |
| --- | --- |
| `-a` | 保留目录结构、权限和时间等归档属性 |
| `-z` | 传输时压缩 |
| `--delete` | 删除远端存在、源目录已不存在的文件 |
| `--exclude` | 跳过秘密、依赖、构建产物和运行数据 |

`--delete` 会改变远端目录。使用前要确认目标路径是 `/srv/company/app/`，并排除 `.env` 与运行数据。

服务器用以下命令确认上传结果：

```bash
cd /srv/company/app
test -f compose.yaml && echo "项目上传成功"
```

### 5.3 创建生产环境文件

```bash
POSTGRES_PASSWORD="$(openssl rand -hex 32)"

install -m 600 /dev/null \
  /srv/company/secrets/company.env

tee /srv/company/secrets/company.env >/dev/null <<EOF
POSTGRES_DB=company
POSTGRES_USER=company
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgresql+psycopg://company:$POSTGRES_PASSWORD@postgres:5432/company
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
CONTENT_ROOT=/data/content
EOF

chown root:root /srv/company/secrets/company.env
ln -sfn /srv/company/secrets/company.env /srv/company/app/.env
```

`openssl rand -hex 32` 生成 32 字节随机值并用十六进制表示。`install -m 600` 创建只允许所有者读写的文件。软链接让 Compose 仍能从项目目录找到 `.env`，秘密文件本体留在独立目录。

检查权限时不输出密码：

```bash
stat -c '%a %U:%G %n' \
  /srv/company/secrets/company.env

grep -E \
  '^(POSTGRES_DB|POSTGRES_USER|CORS_ORIGINS|CONTENT_ROOT)=' \
  /srv/company/secrets/company.env
```

期望权限为 `600 root:root`。

## 六、Docker Hub 超时：镜像加速器也没有解决全部问题

### 6.1 配置阿里云镜像加速

阿里云 ACR 会为账号生成专属镜像加速地址，Docker 可以在 `/etc/docker/daemon.json` 中配置 `registry-mirrors`。[阿里云 ECS Docker 指南](https://help.aliyun.com/en/ecs/user-guide/install-and-use-docker)

```bash
mkdir -p /etc/docker

tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "registry-mirrors": [
    "<镜像加速地址>"
  ]
}
EOF

systemctl daemon-reload
systemctl restart docker

docker info | sed -n '/Registry Mirrors/,+3p'
```

`docker info` 能看到加速地址，说明 Docker 已读取配置。账号专属加速地址不应写入公开仓库。

### 6.2 新问题

执行下面的命令仍然失败：

```bash
docker pull postgres:18.4-alpine
```

返回结果是镜像 `not found`。另一个镜像请求直接访问 `registry-1.docker.io:443` 时出现超时。加速器改善访问路径，但不能保证缓存或代理每个指定标签。

项目包含五个镜像，其中三个需要本地构建，另外两个来自 Docker Hub。继续在 ECS 上反复拉取会让部署结果受网络波动支配。部署改用离线镜像包。

## 七、Apple Silicon 与 ECS 架构不同

### 7.1 架构检查

开发 Mac 使用 ARM64，ECS 使用 AMD64。把 Mac 默认构建的镜像复制到 ECS，容器可能报 `exec format error`。

Docker Buildx 支持用 `--platform` 指定目标平台；单平台结果可以通过 `--load` 写入本地镜像库。[Docker 多平台构建](https://docs.docker.com/build/building/multi-platform/)、[Buildx `--load` 说明](https://docs.docker.com/reference/cli/docker/buildx/build/)

三个应用镜像使用以下模式构建：

```bash
docker buildx build \
  --platform linux/amd64 \
  --load \
  -t company-research-library-api:ecs-amd64 \
  apps/api

docker buildx build \
  --platform linux/amd64 \
  --load \
  -t company-research-library-web:ecs-amd64 \
  -f apps/web/Dockerfile \
  .

docker buildx build \
  --platform linux/amd64 \
  --load \
  -t company-research-library-admin:ecs-amd64 \
  -f apps/admin/Dockerfile \
  .
```

### 7.2 `docker save` 的 20 字节陷阱

第一次执行 `docker save | gzip` 时，Docker 报告某个 manifest 的内容摘要不存在。管道仍留下一个约 20 字节的 `.tar.gz` 文件。文件存在不代表镜像包可用。

本次为 PostgreSQL 和 Nginx 再构建一层只含 `FROM` 的单架构包装镜像：

```dockerfile
FROM postgres:18.4-alpine
```

```dockerfile
FROM nginxinc/nginx-unprivileged:1.30.4-alpine
```

对应标签为：

```text
postgres:ecs-amd64
nginxinc/nginx-unprivileged:ecs-amd64
```

随后逐个检查镜像架构：

```bash
docker image inspect <IMAGE> \
  --format '{{.Architecture}}/{{.Os}}'
```

五个结果都必须是：

```text
amd64/linux
```

### 7.3 导出、校验和传输

Docker 官方文档支持把多个镜像写入 tar 流，再用 gzip 压缩。[docker image save](https://docs.docker.com/reference/cli/docker/image/save/)

```bash
docker save \
  company-research-library-api:ecs-amd64 \
  company-research-library-web:ecs-amd64 \
  company-research-library-admin:ecs-amd64 \
  postgres:ecs-amd64 \
  nginxinc/nginx-unprivileged:ecs-amd64 \
  | gzip -1 \
  > /tmp/company-ecs-amd64-images.tar.gz

gzip -t /tmp/company-ecs-amd64-images.tar.gz
shasum -a 256 /tmp/company-ecs-amd64-images.tar.gz
```

最终镜像包约 319 MB。`gzip -t` 检查压缩结构，SHA-256 用于确认网络传输前后字节一致。

上传时保留进度和断点信息：

```bash
rsync -avP \
  /tmp/company-ecs-amd64-images.tar.gz \
  root@<ECS-IP>:/srv/company/
```

ECS 重新计算哈希，结果与 Mac 一致后导入：

```bash
sha256sum \
  /srv/company/company-ecs-amd64-images.tar.gz

gzip -dc \
  /srv/company/company-ecs-amd64-images.tar.gz \
  | docker load
```

`gzip -dc` 解压到标准输出，`docker load` 从标准输入读取镜像归档。整个过程不生成额外的未压缩 tar 文件。

Compose 期望固定标签，因此导入后重新标记：

```bash
docker tag \
  company-research-library-api:ecs-amd64 \
  company-research-library-api:latest

docker tag \
  company-research-library-web:ecs-amd64 \
  company-research-library-web:latest

docker tag \
  company-research-library-admin:ecs-amd64 \
  company-research-library-admin:latest

docker tag postgres:ecs-amd64 postgres:18.4-alpine

docker tag \
  nginxinc/nginx-unprivileged:ecs-amd64 \
  nginxinc/nginx-unprivileged:1.30.4-alpine
```

仓库现在用 [`scripts/build-ecs-image-bundle.sh`](../scripts/build-ecs-image-bundle.sh) 和 [`scripts/load-ecs-image-bundle.sh`](../scripts/load-ecs-image-bundle.sh) 固化了这套流程。

## 八、Compose 启动失败：CORS 配置触发应用自检

### 8.1 启动命令

ECS 已经有完整本地镜像，启动时禁止构建和拉取：

```bash
cd /srv/company/app

docker compose \
  --env-file /srv/company/secrets/company.env \
  up -d \
  --no-build \
  --pull never
```

`--no-build` 禁止 Compose 在服务器构建镜像。`--pull never` 禁止访问镜像仓库。

### 8.2 症状

PostgreSQL、Web、Admin 均变为 healthy，API 一直 unhealthy，edge 因依赖 API 健康状态而没有正常启动。

查看状态和日志：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  ps -a

docker compose \
  --env-file /srv/company/secrets/company.env \
  logs --no-color --tail=200 api
```

日志中的核心错误为：

```text
ValidationError: cors_origins
CORS origins must use approved local development URLs
```

### 8.3 原因与处理

项目当前没有管理员登录系统。后端配置故意只接受批准的本地开发来源，防止开发阶段把未认证写接口当成公网能力。环境文件最初写入了 `https://www.ayaseeri.com`，应用因此主动拒绝启动。

改回批准的本地来源：

```bash
sed -i \
  's#^CORS_ORIGINS=.*#CORS_ORIGINS=http://localhost:3000,http://localhost:5173#' \
  /srv/company/secrets/company.env
```

然后重新创建 API：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  up -d \
  --no-build \
  --pull never
```

管理端通过 SSH 隧道访问同一个 edge 地址，浏览器请求与 API 同源，因此不依赖公网 CORS。

健康检查全部通过：

```bash
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/health/live
curl --fail http://127.0.0.1:8080/api/health/ready
```

对应输出为 `ok`、`live` 和 `ready`。

## 九、Nginx 不在 `/etc/nginx`

### 9.1 错误假设

最初按 RPM 安装布局尝试备份：

```bash
cp -a /etc/nginx \
  /etc/nginx.backup-$(date +%Y%m%d-%H%M%S)
```

命令返回：

```text
cp: cannot stat '/etc/nginx': No such file or directory
```

`nginx -t` 已经给出线索：

```text
the configuration file /usr/local/nginx/conf/nginx.conf syntax is ok
```

服务器使用源码安装的 Nginx，主目录是 `/usr/local/nginx`。

### 9.2 查清配置、进程和证书

```bash
find /usr/local/nginx/conf \
  -maxdepth 3 \
  -type f \
  -print

grep -RInE \
  'include|server_name|listen|ssl_certificate|proxy_pass' \
  /usr/local/nginx/conf

systemctl status nginx --no-pager -l 2>&1

ps -ef | grep '[n]ginx'

find /usr/local/nginx \
  -maxdepth 5 \
  -type f \
  \( -name '*.pem' -o -name '*.crt' -o -name '*.cer' -o -name '*.key' \) \
  -print
```

这些命令确认了三件事：

- 配置文件只有 `/usr/local/nginx/conf/nginx.conf`。
- Nginx 由手工命令启动，没有 `nginx.service`。
- 旧证书位于 `/usr/local/nginx/conf/cert/`。

`ps` 同时显示宿主机 Nginx 和容器内 Nginx。宿主机 master 由 root 启动；容器进程使用容器 UID，并带有 `daemon off` 参数。排查时不能看到多个 Nginx 进程就全部终止。

正确备份方式为：

```bash
cp -a /usr/local/nginx/conf \
  /usr/local/nginx/conf.backup-$(date +%Y%m%d-%H%M%S)
```

## 十、设计公网只读边界

宿主机 Nginx 只代理回环地址 `127.0.0.1:8080`。公网管理端直接返回 404：

```nginx
location = /admin {
    return 404;
}

location ^~ /admin/ {
    return 404;
}
```

API 只允许读取和预检：

```nginx
location ^~ /api/ {
    limit_except GET HEAD OPTIONS {
        deny all;
    }

    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

公开页面继续代理：

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

每次修改都先测试再重载：

```bash
nginx -t && nginx -s reload
```

`nginx -t` 检查语法、证书文件和引用路径。只有前半段成功，Shell 才会执行 `nginx -s reload`。

验证结果：

```bash
curl -I -H 'Host: www.ayaseeri.com' \
  http://127.0.0.1/

curl -s -o /dev/null -w 'admin: %{http_code}\n' \
  -H 'Host: www.ayaseeri.com' \
  http://127.0.0.1/admin/
```

首页返回 200，管理端返回 404。

最终配置保存在 [`infra/aliyun-ecs/nginx.conf`](../infra/aliyun-ecs/nginx.conf)。

## 十一、旧证书过期与 Certbot 续签

### 11.1 检查旧证书

```bash
openssl x509 \
  -in /usr/local/nginx/conf/cert/www.ayaseeri.com.pem \
  -noout \
  -subject \
  -issuer \
  -dates \
  -ext subjectAltName
```

旧证书同时包含 `ayaseeri.com` 和 `www.ayaseeri.com`，到期时间为 2026-06-30。部署日期为 2026-07-21，证书已经失效。

### 11.2 检查 DNS 和 HTTP 验证路径

阿里云 DNS 使用 A 记录把域名指向 IPv4 地址。[阿里云 DNS 网站解析指南](https://help.aliyun.com/en/dns/pubz-add-website-parsing)

```bash
getent ahostsv4 ayaseeri.com
getent ahostsv4 www.ayaseeri.com
```

两个域名都解析到同一台 ECS 后，创建 webroot 验证目录：

```bash
mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
chmod -R 755 /var/www/letsencrypt

echo 'acme-check-ok' \
  > /var/www/letsencrypt/.well-known/acme-challenge/check

curl --fail \
  http://ayaseeri.com/.well-known/acme-challenge/check

curl --fail \
  http://www.ayaseeri.com/.well-known/acme-challenge/check
```

Certbot 的 webroot 验证要求服务器能从公网通过 80 端口提供 HTTP 站点；官方也建议用 `certbot renew --dry-run` 测试自动续签。[Certbot Nginx 指南](https://certbot.eff.org/instructions?os=snap&ws=nginx)

### 11.3 DNF 被 `Ctrl+Z` 暂停

安装 Certbot 时误按 `Ctrl+Z`：

```text
[1]+ Stopped dnf install -y certbot
```

再次运行 DNF 后，新进程一直等待旧进程释放锁：

```text
Waiting for process with pid ... to finish
```

`Ctrl+Z` 会暂停前台进程并把它留在作业表中。它不会像 `Ctrl+C` 那样终止进程。恢复方法：

```bash
jobs -l
fg %1
```

`jobs -l` 列出当前 Shell 的作业和 PID，`fg %1` 把编号 1 的暂停作业恢复到前台。若创建了第二个重复作业，先用 `Ctrl+C` 停止等待命令，再处理暂停作业。

### 11.4 申请新证书

```bash
dnf install -y epel-release certbot

certbot certonly \
  --webroot \
  --webroot-path /var/www/letsencrypt \
  --cert-name ayaseeri.com \
  -d ayaseeri.com \
  -d www.ayaseeri.com
```

使用 `certonly --webroot` 的原因是服务器运行自定义路径的源码 Nginx。Certbot 只申请证书，不改写 `/usr/local/nginx/conf/nginx.conf`。

新文件位于：

```text
/etc/letsencrypt/live/ayaseeri.com/fullchain.pem
/etc/letsencrypt/live/ayaseeri.com/privkey.pem
```

修改 Nginx 的证书路径并重载：

```bash
nginx -t && nginx -s reload
```

检查 Nginx 实际提供的证书：

```bash
openssl s_client \
  -connect 127.0.0.1:443 \
  -servername www.ayaseeri.com \
  </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

新证书到期时间为 2026-10-19，根域名和 `www` 均返回 HTTPS 200。

### 11.5 自动续签与重载

Certbot 会更新软链接指向的证书文件，但 Nginx 需要重载后才会使用新证书。部署钩子内容为：

```sh
#!/bin/sh
set -eu

/usr/local/nginx/sbin/nginx -t
/usr/local/nginx/sbin/nginx -s reload
```

安装、测试并启用定时器：

```bash
install -m 750 reload-nginx.sh \
  /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

certbot renew --dry-run

systemctl enable --now certbot-renew.timer
systemctl list-timers --all | grep -i certbot
```

模拟续签返回 `all simulated renewals succeeded`。

## 十二、把手工 Nginx 纳入 systemd

源码安装的 Nginx 由手工命令启动，系统重启后不会恢复。本次创建了 `/etc/systemd/system/nginx.service`：

```ini
[Unit]
Description=NGINX HTTP and reverse proxy server
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=forking
PIDFile=/usr/local/nginx/logs/nginx.pid
ExecStartPre=/usr/local/nginx/sbin/nginx -t -q
ExecStart=/usr/local/nginx/sbin/nginx
ExecReload=/usr/local/nginx/sbin/nginx -s reload
ExecStop=/usr/local/nginx/sbin/nginx -s quit
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

切换过程：

```bash
systemctl daemon-reload
systemctl enable nginx
nginx -s quit
sleep 2
systemctl start nginx
```

`nginx -s quit` 让旧 master 完成已有请求后退出。`systemctl start nginx` 再由 systemd 启动新 master。

验证：

```bash
systemctl is-enabled nginx
systemctl is-active nginx
systemctl status nginx --no-pager -l

curl -I https://www.ayaseeri.com/
curl -I http://www.ayaseeri.com/
```

结果为 `enabled`、`active`、HTTPS 200、HTTP 301。

## 十三、通过 SSH 隧道访问管理端

Mac 另开终端：

```bash
ssh -N \
  -L 18080:127.0.0.1:8080 \
  root@<ECS-IP>
```

参数含义：

- `-N` 表示不执行远端 Shell 命令，只建立转发。
- `-L 本地端口:远端目标:远端端口` 把 Mac 的 18080 转发到 ECS 回环地址的 8080。

浏览器访问：

```text
http://127.0.0.1:18080/admin/
```

隧道内管理端正常显示。公网访问下面的地址返回 404：

```text
https://www.ayaseeri.com/admin/
```

这个方案保留了未认证管理端的本地边界，也免去了把 8080 加入安全组。

## 十四、完整业务验收

管理端创建“贵州茅台”，填写证券代码和市场，再上传两种资料：

```text
doc/snapshots/published/贵州茅台.html
doc/snapshots/sources/贵州茅台.md
```

公开首页出现公司和资料目录。HTML 直接嵌入；Markdown 使用统一模板生成 HTML 后嵌入。

数据库检查：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  exec -T postgres sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT name, ticker, market FROM companies ORDER BY created_at;"'
```

文档索引检查：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  exec -T postgres sh -lc \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT title, format, original_filename FROM documents ORDER BY uploaded_at;"'
```

内容文件检查：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  exec -T api sh -lc \
  'find /data/content -maxdepth 4 -type f | sort'
```

HTML 目录包含 `source.html`。Markdown 目录包含 `source.md` 和 `rendered.html`。

## 十五、备份数据库和内容卷

Docker 容器可以重建，命名卷中的数据库和资料不能跟随镜像恢复。Docker 文档也区分镜像和卷：保存镜像不会包含卷数据。[Docker 数据持久化](https://docs.docker.com/get-started/docker-concepts/running-containers/persisting-container-data/)

本项目必须把 PostgreSQL 索引和内容卷放入同一个备份集。备份脚本执行以下步骤：

1. 使用文件锁防止两个任务重叠。
2. 暂停 API，阻止备份期间写入。
3. 用 `pg_dump -Fc` 导出数据库。
4. 把内容卷压缩为 `content.tar.gz`。
5. 使用 `pg_restore --list`、`tar -tzf` 和 SHA-256 检查备份。
6. 恢复 API，更新 `latest` 软链接并清理 30 天前的目录。

PostgreSQL 官方文档说明 `pg_dump` 能生成一致导出，custom 格式 `-Fc` 适合交给 `pg_restore` 检查和恢复。[PostgreSQL 18 `pg_dump`](https://www.postgresql.org/docs/current/app-pgdump.html)

核心数据库命令：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  exec -T postgres sh -lc \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > postgres.dump
```

核心内容卷命令：

```bash
docker run --rm --pull never \
  --user 0:0 \
  -v company-research-library_content_data:/data:ro \
  nginxinc/nginx-unprivileged:1.30.4-alpine \
  tar -czf - -C /data . \
  > content.tar.gz
```

完整实现位于 [`scripts/company-backup.sh`](../scripts/company-backup.sh)。

每天凌晨 3:30 由 systemd timer 执行，并随机延迟最多 15 分钟：

```ini
[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15m
Persistent=true
Unit=company-backup.service
```

启用和检查：

```bash
systemctl daemon-reload
systemctl enable --now company-backup.timer
systemctl list-timers --all | grep company-backup
journalctl -u company-backup.service --no-pager -n 100
```

首次备份生成：

```text
postgres.dump
content.tar.gz
SHA256SUMS
created-at.txt
compose-status.txt
```

本轮按使用者决定只保留 ECS 本地备份。它可以处理误删和应用故障，无法处理整台 ECS 或云盘损坏。资料规模增加后应复制到 OSS 或另一台机器。

## 十六、问题与解决方案总表

| 问题 | 判断依据 | 解决方案 | 验证 |
| --- | --- | --- | --- |
| Docker 官方仓库 SSL 重置 | DNF 只在 `download.docker.com` 失败 | 改用阿里云 Docker CE 仓库 | Docker 与 Compose 显示版本，服务 active |
| Docker Hub 拉取超时 | `registry-1.docker.io:443` 超时 | Mac 构建并上传离线镜像包 | ECS `docker load` 成功 |
| ACR 加速器缺少标签 | `postgres:18.4-alpine not found` | 不依赖加速器完成部署 | Compose 使用本地镜像启动 |
| Mac ARM64 与 ECS AMD64 不同 | `uname -m` 和镜像 inspect 不一致 | Buildx 指定 `linux/amd64` | 五个镜像均为 `amd64/linux` |
| 镜像归档只有 20 字节 | `docker save` manifest 错误 | 构建单架构包装镜像，检查 gzip 与 SHA-256 | 319 MB 归档通过 `gzip -t` |
| API unhealthy | API 日志显示 CORS ValidationError | CORS 改回批准的本地来源 | live 与 ready 都通过 |
| `/etc/nginx` 不存在 | `nginx -t` 显示 `/usr/local/nginx/conf` | 按源码安装目录备份和配置 | `nginx -t` 成功 |
| Nginx 没有 systemd 服务 | `systemctl status nginx` 显示 unit not found | 新建 `nginx.service` | enabled、active |
| HTTPS 证书过期 | `openssl x509 -dates` 显示旧到期日 | Certbot webroot 申请双域名证书 | 两个 HTTPS 域名返回 200 |
| DNF 锁一直等待 | `jobs -l` 显示暂停的 DNF | `fg %1` 恢复原任务 | Certbot 3.1.0 安装成功 |
| 管理端没有登录保护 | 当前代码没有认证和 CSRF | 公网 404，SSH 隧道访问 | 隧道内可用，公网 404 |
| 容器重建后担心丢数据 | 数据位于两个命名卷 | `pg_dump` 与内容 tar 同批备份 | dump、tar 和 SHA-256 均通过 |

## 十七、这次部署留下的经验

### 17.1 先查现场，再写配置

`nginx -t` 已经打印真实配置路径。若先看这条输出，就不会尝试备份不存在的 `/etc/nginx`。服务器上的安装来源、目录和启动方式不能靠习惯推断。

### 17.2 镜像可用性包含网络和架构

镜像标签存在不代表 ECS 能获得可执行镜像。部署前要确认仓库可达、标签存在、目标架构匹配、归档完整。`docker image inspect`、`gzip -t` 和 SHA-256 分别覆盖这三个检查点。

### 17.3 应用自检能阻止危险配置

FastAPI 因公网 CORS 值拒绝启动，看起来像部署故障，实质上保护了未认证写接口。修复时保留了安全边界，没有删除验证器。

### 17.4 管理端认证可以分阶段实现

当前阶段用 SSH 隧道限制管理端范围，公开站点已经可用。以后实现登录、授权和 CSRF 后，再评估是否开放公网管理入口。

### 17.5 备份需要同时覆盖索引和文件

数据库知道文档位置，内容卷保存文档正文。只备份其中一边会产生无法读取的索引或没有索引的孤立文件。备份脚本暂停写入，并把两边放入同一个时间戳目录。

## 十八、当前运维清单

检查服务：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  -f /srv/company/app/compose.yaml ps

systemctl is-active docker
systemctl is-active nginx
systemctl --failed
```

检查网站：

```bash
curl --fail https://www.ayaseeri.com/ > /dev/null

curl -s -o /dev/null -w '%{http_code}\n' \
  https://www.ayaseeri.com/admin/
```

第二条必须返回 404。

检查定时任务和磁盘：

```bash
systemctl list-timers --all \
  | grep -E 'company-backup|certbot'

df -h /
docker system df
```

查看应用日志：

```bash
docker compose \
  --env-file /srv/company/secrets/company.env \
  -f /srv/company/app/compose.yaml \
  logs --no-color --tail=200 api edge
```

## 十九、仓库中固化的资产

本轮对话结束前，服务器上的手工配置被整理进仓库：

| 文件 | 内容 |
| --- | --- |
| [`doc/DEPLOYMENT.md`](./DEPLOYMENT.md) | 首次部署、更新、回滚、恢复和日常检查 |
| [`infra/aliyun-ecs/nginx-bootstrap.conf`](../infra/aliyun-ecs/nginx-bootstrap.conf) | Certbot 申请前的 HTTP 配置 |
| [`infra/aliyun-ecs/nginx.conf`](../infra/aliyun-ecs/nginx.conf) | HTTPS 与公网只读边界 |
| [`infra/aliyun-ecs/systemd/nginx.service`](../infra/aliyun-ecs/systemd/nginx.service) | 宿主机 Nginx systemd 单元 |
| [`infra/aliyun-ecs/systemd/company-backup.timer`](../infra/aliyun-ecs/systemd/company-backup.timer) | 每日备份定时器 |
| [`infra/aliyun-ecs/letsencrypt/reload-nginx.sh`](../infra/aliyun-ecs/letsencrypt/reload-nginx.sh) | 续签后重载钩子 |
| [`scripts/build-ecs-image-bundle.sh`](../scripts/build-ecs-image-bundle.sh) | Mac 构建 AMD64 离线镜像 |
| [`scripts/load-ecs-image-bundle.sh`](../scripts/load-ecs-image-bundle.sh) | ECS 导入、启动和健康等待 |
| [`scripts/company-backup.sh`](../scripts/company-backup.sh) | 数据库与内容卷备份 |

仓库测试会检查这些资产存在、Nginx 拦截管理端和写方法、脚本没有写入固定 ECS IP 或密码。两份 Nginx 配置也使用真实 Nginx 1.30.4 镜像执行过 `nginx -t`。

## 参考资料

1. [Docker Engine on CentOS](https://docs.docker.com/engine/install/centos/)
2. [Install the Docker Compose plugin](https://docs.docker.com/compose/install/linux/)
3. [阿里云 Docker CE 镜像](https://developer.aliyun.com/mirror/docker-ce/)
4. [阿里云 ECS 安装和使用 Docker](https://help.aliyun.com/en/ecs/user-guide/install-and-use-docker)
5. [阿里云 ACR 配置镜像加速器](https://help.aliyun.com/zh/acr/user-guide/accelerate-the-pulls-of-docker-official-images)
6. [Docker 多平台构建](https://docs.docker.com/build/building/multi-platform/)
7. [docker buildx build](https://docs.docker.com/reference/cli/docker/buildx/build/)
8. [docker image save](https://docs.docker.com/reference/cli/docker/image/save/)
9. [Docker 数据持久化](https://docs.docker.com/get-started/docker-concepts/running-containers/persisting-container-data/)
10. [阿里云 ECS 安全组指南](https://help.aliyun.com/en/ecs/user-guide/security-groups-for-different-use-cases)
11. [阿里云 DNS 网站解析指南](https://help.aliyun.com/en/dns/pubz-add-website-parsing)
12. [Certbot Nginx 指南](https://certbot.eff.org/instructions?os=snap&ws=nginx)
13. [PostgreSQL 18 pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)

## 结语

这次部署没有依赖一条从头跑到尾的理想命令。每个失败都留下了可检查的证据：DNF 的目标域名、Docker manifest、镜像架构、FastAPI 验证错误、Nginx 编译路径、证书日期、systemd 状态和备份校验值。处理顺序始终相同：读取错误，缩小范围，修改一个变量，再用健康检查确认结果。

公开站点已经具备稳定的只读入口，管理端仍停留在 SSH 隧道内。下一阶段若要开放公网管理，应先实现管理员认证、会话、授权和 CSRF 防护。现有部署边界可以继续承载资料录入和公开阅读。
