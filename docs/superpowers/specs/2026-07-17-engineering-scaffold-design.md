# 第一里程碑：工程骨架设计

## 目标

建立企业快照库的生产工程骨架，让 Nuxt 公开端、Vue/Vite 管理端、FastAPI、PostgreSQL 和 Nginx 能在本机混合开发模式及 Docker Compose 完整模式下运行。

第一里程碑只建立工程边界、健康检查、工具链、容器、路由和测试门槛，不实现快照业务、管理员登录、业务表、HTML 导入或原型界面迁移。

完成后，开发者应能：

- 使用 `pnpm workspace` 管理两个前端应用；
- 使用 `uv` 管理 FastAPI 应用；
- 本机运行 Web、Admin 和 API，并通过 Docker 启动 PostgreSQL；
- 使用 Compose 启动五个服务，通过一个 Nginx 入口访问；
- 运行统一检查和 smoke test；
- 从根目录 README 理解项目结构和每条命令的底层行为。

## 已确认的决策

1. 第一里程碑选择“工程骨架”，不提前实现业务。
2. Node 工作区使用 `pnpm`，Python 使用 `uv`。
3. 使用受支持的 LTS/稳定版本，不使用浮动 `latest`。
4. 采用混合开发：本机热更新，Docker Compose 做完整环境验收。
5. `doc/` 继续作为当前产品设计依据；工程代码不得修改其 HTML-only 主线。
6. 本次继续在当前仓库开发，不创建第二个应用仓库。

## 版本基线

| 组件 | 固定版本或系列 | 说明 |
|---|---:|---|
| Node.js | `24.18.0` | Active/Maintenance LTS 系列，写入 `.nvmrc` 和 Docker 基础镜像 |
| pnpm | `10.34.5` | 保守使用 pnpm 10，写入根 `packageManager` |
| TypeScript | `5.9.3` | 暂不采用新发布的 TypeScript 7 |
| Nuxt | `4.4.8` | Nuxt 4 稳定版 |
| Vue | `3.5.40` | Vue 3 稳定版 |
| Vite | `8.1.5` | Vite 8 稳定版，只供管理端直接配置；Nuxt 管理自己的构建依赖 |
| Python | `3.13` | 成熟 bugfix 分支，写入 `.python-version` |
| uv | `0.11.29` | 工具版本在 CI/安装说明中锁定 |
| FastAPI | `0.139.2` | 由 `apps/api/uv.lock` 精确锁定 |
| Uvicorn | `0.51.0` | 由 `apps/api/uv.lock` 精确锁定 |
| SQLAlchemy | `2.0.51` | 只用于连接和健康检查，不创建业务模型 |
| psycopg | `3.3.4` | PostgreSQL 驱动 |
| Pydantic | `2.13.4` | 环境配置与响应模型 |
| pydantic-settings | `2.14.2` | 从环境变量构建并校验 API 配置 |
| PostgreSQL | `18.4` | Compose 数据库镜像 |
| Nginx | `1.30.4` | Stable 系列；优先使用对应 unprivileged 镜像 |

依赖清单声明兼容范围，`pnpm-lock.yaml` 和 `apps/api/uv.lock` 保存实际精确解析结果。Dockerfile 不使用 `latest`；基础镜像使用精确版本标签，实施时记录可用的多架构镜像摘要。

官方版本依据：

- Node.js：<https://nodejs.org/en/about/previous-releases/>
- Python：<https://devguide.python.org/versions/>
- Nuxt：<https://nuxt.com/blog/v4-4>
- Vite：<https://vite.dev/blog/announcing-vite8-1>
- PostgreSQL：<https://www.postgresql.org/support/versioning/>
- Nginx：<https://nginx.org/en/download.html>

## 目标目录

```text
company/
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── server/routes/healthz.get.ts
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── nuxt.config.ts
│   │   └── package.json
│   ├── admin/
│   │   ├── src/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── nginx.conf
│   │   ├── vite.config.ts
│   │   └── package.json
│   └── api/
│       ├── src/company_api/
│       ├── tests/
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── uv.lock
├── infra/nginx/
│   └── default.conf
├── scripts/
│   └── compose-smoke.sh
├── doc/
├── tests/
├── .dockerignore
├── .env.example
├── .gitignore
├── .nvmrc
├── .python-version
├── Makefile
├── README.md
├── compose.yaml
├── package.json
├── pnpm-lock.yaml
└── pnpm-workspace.yaml
```

`doc/` 和已有仓库级测试保留。新的应用测试放在各自应用目录；跨服务 smoke test 放在 `scripts/`，结构契约可以继续放在根 `tests/`。

## 服务边界

### Web

- 使用 Nuxt 4、Vue 3 和 TypeScript strict。
- 第一阶段只渲染一个明确标注“工程骨架”的公开首页。
- 提供内部 `GET /healthz`，不调用 API 或数据库。
- 容器运行 Nuxt 生产 server，监听 `0.0.0.0:3000`。
- 不读取 `doc/snapshots/`，不实现快照页面。

### Admin

- 使用 Vue 3、Vite 8 和 TypeScript strict。
- Vite `base` 固定为 `/admin/`。
- 第一阶段只渲染一个明确标注“管理端工程骨架”的页面。
- 生产构建由内部 unprivileged Nginx 提供，包含 `GET /healthz`。
- 不实现登录、路由守卫、Pinia 状态或业务 API。

### API

- 使用 FastAPI，包路径为 `apps/api/src/company_api`。
- 只实现：
  - `GET /api/health/live`
  - `GET /api/health/ready`
- `live` 不访问数据库。
- `ready` 通过 SQLAlchemy/psycopg 执行最小 `SELECT 1`。
- 本里程碑不创建 Alembic、不建业务表、不暴露业务 API。

### PostgreSQL

- 使用 PostgreSQL 18.4。
- 只创建由环境变量指定的数据库和角色。
- 持久化到命名 volume。
- Compose 健康检查使用 `pg_isready`。
- 本机混合开发只绑定 `127.0.0.1:5432`；不绑定所有网卡。

### Edge

- 使用 Nginx 1.30 stable 的 unprivileged 镜像。
- 是完整 Compose 模式唯一对宿主机提供 HTTP 的应用入口。
- 监听容器 `8080`，宿主机绑定 `127.0.0.1:8080`。
- 不挂载 Docker socket，不在镜像中保存密钥。

## 访问模式

### 本机混合开发

```text
Web        http://localhost:3000
Admin      http://localhost:5173/admin/
API        http://localhost:8000/api/health/live
Postgres   127.0.0.1:5432
```

工作方式：

1. `make dev-infra` 只启动 PostgreSQL。
2. Web/Admin 由 pnpm 在本机提供热更新。
3. API 由 uv/Uvicorn 在本机提供 reload。
4. 本机模式不要求 Nginx；它用于完整 Compose 验收。

### 完整 Compose 验收

```text
Browser → 127.0.0.1:8080 edge
                    ├── /admin/* → admin:8080
                    ├── /api/*   → api:8000
                    └── /*       → web:3000

api → postgres:5432
edge → web/admin/api internal network
```

Web、Admin、API 只声明 `expose`，不直接发布宿主机端口。PostgreSQL 的 loopback 端口只服务混合开发；生产覆盖配置必须取消该端口。

## Nginx 路由

路由必须满足：

```text
/admin        → 308 /admin/
/admin/*      → admin 服务，并去掉转发给内部静态服务的 /admin 前缀
/api/*        → api 服务，保留完整 /api 前缀
/*            → Nuxt web
```

Admin 构建产物使用 `/admin/` 绝对基础路径。Edge 的 `/api/` `proxy_pass` 不携带替换 URI，避免意外去掉 FastAPI 的 `/api` 前缀。

第一里程碑不配置 TLS、生产域名、缓存、压缩或安全响应头全集；这些属于部署里程碑。基础代理头至少包含 `Host`、`X-Real-IP`、`X-Forwarded-For` 和 `X-Forwarded-Proto`。

## 健康检查

### API live

```http
GET /api/health/live
200 {"status":"live"}
```

该端点只证明 FastAPI 进程和事件循环能够响应，不创建数据库连接。

### API ready

数据库连接成功：

```http
GET /api/health/ready
200 {"status":"ready"}
```

连接异常或查询失败：

```http
GET /api/health/ready
503 {"status":"not_ready"}
```

错误响应不包含数据库地址、用户名、驱动异常、堆栈或检查明细。异常写入应用日志，但健康响应保持最小化。

### Web/Admin/容器

- Web `GET /healthz` 返回 200 和最小文本或 JSON。
- Admin 内部 Nginx `GET /healthz` 返回 200，不依赖 SPA fallback。
- PostgreSQL 使用 `pg_isready`。
- Edge `GET /healthz` 返回自身 200；完整 smoke test 另外验证所有上游。
- Compose 使用 `depends_on.condition: service_healthy` 控制启动顺序，但应用自身仍必须处理依赖短暂不可用。

## 环境变量

提交 `.env.example`，忽略 `.env`。

本地字段至少包含：

```dotenv
POSTGRES_DB=company
POSTGRES_USER=company
POSTGRES_PASSWORD=local-development-only-change-me
DATABASE_URL=postgresql+psycopg://company:local-development-only-change-me@127.0.0.1:5432/company
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

Compose 中 API 的 `DATABASE_URL` 使用服务名 `postgres`，通过 Compose 环境覆盖本机值。

约束：

- `.env.example` 的密码必须明显标注只供本地开发。
- 不提供可误用于生产的默认密钥。
- 缺少必填字段或 URL 无法解析时，API 启动立即失败。
- CORS 只允许显式列表；完整 Compose 同源访问不依赖 CORS。
- 健康响应和日志不输出完整 `DATABASE_URL` 或密码。

## 工具与命令

根 `package.json` 为 private workspace，提供 Web/Admin 聚合脚本。Python 命令通过 `uv --project apps/api` 运行。

Makefile 提供：

```text
make setup          安装 pnpm 与 Python 依赖
make dev-infra      只启动 PostgreSQL
make dev            显示并启动 Web/Admin/API 本机开发命令
make check          lint + typecheck + test + build
make compose-up     构建并启动完整 Compose
make compose-smoke  验证五服务状态和三条入口路由
make compose-down   停止服务但不删除数据卷
```

根 README 同时列出对应底层命令，解释每个 Make target 做了什么。`make compose-down` 不使用 `-v`；删除数据卷必须是单独、显式且带警告的命令，本里程碑不提供快捷 target。

## Docker 构建与安全

- Web/Admin/API 使用多阶段构建。
- Web 和 API 最终镜像使用非 root 用户。
- Admin 与 Edge 使用 unprivileged Nginx。
- 最终镜像不包含源代码缓存、测试依赖、`.env`、Git 元数据或本机虚拟环境。
- pnpm 安装使用 frozen lockfile；uv 使用 frozen lockfile。
- 构建上下文通过 `.dockerignore` 排除 `.git`、`.env`、`node_modules`、`.nuxt`、`dist`、`.venv`、数据库文件和临时产物。
- Compose 不挂载 Docker socket。
- Web/Admin/API/PostgreSQL 使用命名网络；数据库不加入仅 Edge 使用的入口网络。

## 测试策略

### Web/Admin

- ESLint。
- TypeScript strict 类型检查。
- Vitest 验证骨架页面内容。
- Web 与 Admin 生产构建。
- Admin 构建测试确认 base 为 `/admin/`，直接访问 `/admin/` 和静态资源均成功。

### API

- Ruff lint 与 format check。
- mypy 类型检查。
- pytest：
  - `live` 返回 200，并证明没有调用数据库依赖；
  - `ready` 在数据库 probe 成功时返回 200；
  - probe 异常时返回 503；
  - 503 响应不包含原异常或数据库信息；
  - 配置缺失或非法时失败。

### Compose

- `docker compose config`。
- 构建五个服务镜像。
- 等待所有 healthcheck 成功。
- 通过 Edge 检查 `/`、`/admin/`、`/api/health/live`、`/api/health/ready`。
- 停止 PostgreSQL 后，API ready 必须变为 503；恢复 PostgreSQL 后必须重新变为 200。
- 确认 Web/Admin/API 没有宿主机发布端口。
- `compose-smoke.sh` 使用条件轮询和总超时，不使用固定长 sleep。

### 仓库回归

- 现有 `tests/docs.test.mjs` 必须继续通过。
- 现有 `tests/prototype.test.mjs` 必须继续通过，包括真实 Chrome 安全与状态测试。
- `git diff --check` 必须通过。

## 错误处理

- 本机命令找不到 Node、pnpm、uv 或 Docker 时，README 给出明确检查命令，不自动修改全局系统。
- 应用启动配置错误立即退出，错误信息只指出字段名，不输出密钥值。
- PostgreSQL 尚未 ready 时 API 可以启动，但 `/ready` 返回 503；Compose 通过健康依赖减少启动竞态。
- Nginx 上游不可用时 smoke test 必须失败，不把默认 502 当成可接受状态。
- smoke 脚本失败时输出失败 URL、HTTP 状态和相关 Compose 状态，并以非零退出。
- 清理命令必须在失败路径中停止容器，但不得删除 volume。

## README 学习目标

根 README 面向正在学习全栈开发的使用者，包含：

1. 当前里程碑与明确的“不包含”清单。
2. 五服务关系图。
3. 环境版本检查命令。
4. 第一次安装步骤。
5. 本机混合开发步骤。
6. 完整 Docker 验收步骤。
7. Make target 与底层命令对照。
8. 常见故障：端口占用、数据库未 ready、lockfile 不一致、Docker daemon 未启动。
9. 指向 `doc/README.md` 和下一里程碑说明的链接。

## 完成定义

第一里程碑只有同时满足以下条件才完成：

1. 新环境执行 `make setup` 成功。
2. `make dev-infra` 只启动 PostgreSQL，且数据卷持久化。
3. Web、Admin、API 可以分别以热更新模式启动。
4. `make check` 完成前后端 lint、类型、测试和生产构建。
5. `make compose-up` 构建并启动五个健康服务。
6. 通过 `http://localhost:8080/`、`/admin/` 和 `/api/health/*` 访问正确服务。
7. `make compose-smoke` 验证路由、健康、数据库失效与恢复。
8. `make compose-down` 后 PostgreSQL volume 仍存在。
9. Web/Admin/API 没有暴露宿主机端口；PostgreSQL 只绑定 loopback。
10. 现有 doc/prototype 回归全部通过。
11. 根 README 能让新开发者不依赖本次对话完成上述步骤。
12. Git 中不包含 `.env`、数据库数据、虚拟环境、依赖目录或构建产物。

## 明确不在本里程碑内

- 快照 HTML 导入、扫描、安全校验和文件存储。
- PostgreSQL 业务表与 Alembic 迁移。
- 管理员账号、Session、CSRF 和登录页面。
- 公开快照列表、搜索、详情和 SEO 页面。
- 原型 UI 迁移。
- 可信 load-checker/Chromium 生产服务。
- TLS、`www.ayaseeri.com`、阿里云安全组、备份与生产发布。
- CI/CD、镜像仓库和自动部署。

下一里程碑是“HTML 内容契约与后端校验核心”，单独设计和实施。
