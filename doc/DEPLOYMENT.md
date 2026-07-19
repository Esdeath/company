# 部署设计

## 当前状态与目标

本地直传切片仅用于开发与验收，未认证写入接口不得部署到公网。生产部署仍以一台阿里云 ECS 和 Docker Compose 为目标：Nginx 是唯一公开容器；Nuxt 公开端、Vue/Vite 管理端、FastAPI 和 PostgreSQL 留在内部网络。生产写入入口需要另行接入管理员认证、授权和 CSRF 防护。

## 服务组成

```text
Internet
  └── Nginx :80/:443
        ├── Nuxt 公开端
        ├── Vue/Vite 管理端
        └── FastAPI
              ├── PostgreSQL
              └── content/companies/ 文件卷
```

| 服务 | 公网端口 | 健康检查 | 持久化或权限 |
|---|---|---|---|
| `nginx` | 80、443 | `/healthz` | 证书只读、日志 |
| `web` | 无 | `/healthz` | 无 |
| `admin` | 无 | `/healthz` | 无 |
| `api` | 无 | `/api/health/live`、`/api/health/ready` | 内容卷读写 |
| `postgres` | 无 | `pg_isready` | 数据卷 |

## Docker Compose

- `compose.yaml` 定义服务、`edge` 与 `backend` 网络、健康检查和命名卷。
- 生产镜像使用 Git commit SHA 等不可变标签，不以 `latest` 作为发布依据。
- 除 Nginx 外不配置宿主机 `ports`；容器绝不挂载 Docker socket。
- 未认证直传接口只能由本地开发 Compose 配置启用，生产 Compose 不提供它。

## 网络与安全组

Compose 定义两个网络：

- `edge`：Nginx 与 web、admin、api 通信，但只有 Nginx 绑定宿主机端口。
- `backend`：api 与 postgres，设置为 `internal: true`；PostgreSQL 不加入 `edge`。

安全组只开放：

| 端口 | 来源 | 用途 |
|---:|---|---|
| 80 | 公网 | HTTPS 跳转与 ACME |
| 443 | 公网 | HTTPS |
| 22 | 固定管理 IP、VPN 或堡垒机 | SSH |

不得开放 3000、8000、5432 或数据库管理端口。ECS 使用非 root 部署用户、SSH 密钥、最小权限、防火墙、安全更新、NTP 和云监控。

## 内容卷与备份

生产使用独立、持久化的内容卷，和仓库内 `doc/` 示例严格分离：

```text
/srv/company/
├── app/
├── data/
│   ├── companies/
│   └── postgres/
├── backups/
├── logs/nginx/
└── secrets/.env
```

只有 FastAPI 能以读写方式挂载完整内容卷。备份将 PostgreSQL 索引和 `data/companies/` 放入同一备份集；恢复时使用同一备份集恢复两侧，再核对索引路径和文件存在性。

## Nginx 路由与缓存

Nginx 将根域 301 到 `https://www.ayaseeri.com`，传递 `Host`、`X-Forwarded-For`、`X-Forwarded-Proto` 和请求 ID，并限制上传大小与超时。

- 已建立索引的资料内容响应设置明确的 `Content-Type`；内容变更后由应用更新缓存验证信息。
- 带内容哈希的前端静态资源可使用一年缓存和 `immutable`。
- `/admin/`、`/api/` 和登录响应使用 `Cache-Control: no-store`，不得进入共享公开缓存。
- 配置 CSP、`X-Content-Type-Options: nosniff` 和合理的 Referrer Policy；启用 HSTS 前先确认相关域名稳定支持 HTTPS。

## 阿里云 ECS

首版以阿里云 ECS 为目标，建议从 2 vCPU、4 GiB 内存和 40–80 GiB ESSD 起步，再依据数据库和磁盘指标扩容。操作系统选受支持的 Ubuntu LTS 或 Alibaba Cloud Linux，安装 Docker Engine 与 Compose Plugin。

启用云监控，至少覆盖 CPU、内存、磁盘、网络、进程存活和证书到期。生产备份至少复制一份到 ECS 之外的阿里云 OSS，并通过独立凭据与生命周期策略保护。

## 健康检查、日志与告警

- `/api/health/live` 与 `/api/health/ready` 是唯一不版本化的基础设施例外；它们不要求管理员认证，只返回最小状态且不泄露内部信息。Nginx `/healthz` 只证明入口存活；FastAPI 在服务端计算 readiness 时检查数据库和内容根目录权限，公开响应只给出能否接收请求的最小结果。
- Docker 使用 `json-file` 或等价驱动的大小/文件数轮转；Nginx access/error 日志在宿主机轮转。
- 应用结构化日志包含 `request_id` 和结果摘要，不记录文件正文、密码、Cookie、Session、CSRF、内部令牌或私钥。
- 对容器重启、readiness 失败、5xx、备份失败、磁盘 80%、证书剩余 30 天和日志异常量告警。
