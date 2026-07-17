# 企业研究资料库

## 当前里程碑：工程骨架

仓库目前提供可运行、可检查的五服务工程骨架。你可以查看占位页面、后台占位页和 API 健康接口，也可以练习本机开发与 Compose 验收。业务功能尚未进入本里程碑，具体边界见文末“当前不包含”。

## 五个服务

```text
浏览器 http://127.0.0.1:8080
              |
              v
        edge（Nginx 路由）
          /     |      \
         /    /admin/   \ /api/
        v       v        v
      web     admin     api ---- postgres
```

| 服务 | 职责 | 目录或定义 |
| --- | --- | --- |
| `edge` | 接收宿主机的 `8080` 请求，把 `/`、`/admin/`、`/api/` 分发给三个应用 | `infra/nginx/default.conf` |
| `web` | 提供公开站点的 Nuxt 占位页和 `/healthz` | `apps/web` |
| `admin` | 提供挂载在 `/admin/` 下的 Vue/Vite 占位页 | `apps/admin` |
| `api` | 提供 FastAPI 存活与就绪检查 | `apps/api` |
| `postgres` | 为 API 提供本地 PostgreSQL 18.4 数据库 | `compose.yaml` |

完整 Compose 只向宿主机发布 `127.0.0.1:8080` 和 `127.0.0.1:5432`。Web、Admin 和 API 端口只在 Compose 网络内开放。

## 目录导航

```text
.
├── apps/
│   ├── web/             # Nuxt 公开站点
│   ├── admin/           # Vue/Vite 管理端
│   └── api/             # FastAPI 服务、Python 测试与 uv.lock
├── infra/nginx/         # edge 路由配置
├── scripts/             # Compose smoke 验收脚本
├── tests/               # 文档、原型和工程契约测试
├── doc/                 # 产品与开发背景文档
├── compose.yaml         # 五服务编排
├── Makefile             # 常用入口；底层命令见后文对照表
└── pnpm-workspace.yaml  # Web 与 Admin 工作区
```

## 版本要求

仓库锁定 Node、pnpm、Python 和 Python 依赖。Docker 主机版本由你的 Docker Desktop 或 Docker Engine 安装决定，需支持 Compose v2。

| 工具 | 目标版本 | 锁定位置 |
| --- | --- | --- |
| Node.js | `24.18.0` | `.nvmrc` |
| pnpm | `10.34.5` | 根 `package.json` 的 `packageManager` |
| uv | `0.11.29` | 本里程碑使用的依赖安装工具版本 |
| Python | `3.13` | `.python-version` 和 `apps/api/pyproject.toml` |
| PostgreSQL 镜像 | `postgres:18.4-alpine` | `compose.yaml` |
| Nginx 镜像 | `nginxinc/nginx-unprivileged:1.30.4-alpine` | `compose.yaml` |

在根目录逐条检查宿主机：

```bash
node --version
corepack pnpm --version
uv --version
python3 --version
docker --version
docker compose version
```

如果 Node 版本不同，先用你安装的 Node 版本管理器读取 `.nvmrc`。例如 nvm 用户运行 `nvm install && nvm use`。`make setup` 会打印预期版本与当前版本；版本不符时请先切换工具链。

## 第一次安装

1. 复制本地环境文件：

   ```bash
   cp .env.example .env
   ```

   `.env.example` 只含本地开发弱凭据，方便启动骨架。真实环境不得复用其中的用户名、密码或连接串。Git 会忽略 `.env`。

2. 安装锁定依赖：

   ```bash
   make setup
   ```

   `make setup` 调用：

   ```bash
   corepack pnpm install --frozen-lockfile
   cd apps/api && uv sync --frozen
   ```

## 混合开发

混合开发只把 PostgreSQL 放进 Compose，三个应用在宿主机运行。这样可以直接看开发服务器日志并使用热更新。

先把 `.env` 中 `DATABASE_URL` 的主机从 `postgres` 改成 `127.0.0.1`：

```dotenv
DATABASE_URL=postgresql+psycopg://company:company_local_only@127.0.0.1:5432/company
```

Compose 中的 API 会根据 `POSTGRES_*` 变量生成容器内连接串，因此这项本机改动不会改变完整 Compose 的服务连接。

终端 1 启动数据库：

```bash
make dev-infra
# docker compose --env-file .env up -d postgres
```

你可以在终端 2 用一条命令启动三个应用：

```bash
make dev
# make -j3 dev-web dev-admin dev-api
```

按 `Ctrl-C` 后，递归 Make 会把中断传给三个开发服务器。若你想分开查看日志，改用三个终端运行内部目标：

```bash
# 终端 2
make dev-web
# corepack pnpm --filter @company/web dev

# 终端 3
make dev-admin
# corepack pnpm --filter @company/admin dev

# 终端 4
make dev-api
# cd apps/api && uv run --env-file ../../.env uvicorn --factory company_api.main:create_app --reload --host 0.0.0.0 --port 8000
```

混合开发地址：

| 进程 | 地址 |
| --- | --- |
| Web | `http://127.0.0.1:3000` |
| Admin | `http://127.0.0.1:5173/admin/` |
| API 存活检查 | `http://127.0.0.1:8000/api/health/live` |
| API 就绪检查 | `http://127.0.0.1:8000/api/health/ready` |

数据库可继续运行，或用 `make compose-down` 停止。该命令保留 `postgres_data` volume。

## 完整 Compose

完整 Compose 构建并启动 edge、Web、Admin、API 和 PostgreSQL。`make compose-up` 在缺少 `.env` 时会提示复制命令。

```bash
make compose-up
# docker compose --env-file .env up --build -d

make compose-smoke
# ./scripts/compose-smoke.sh

docker compose --env-file .env ps

make compose-down
# docker compose --env-file .env down
```

启动后访问 `http://127.0.0.1:8080`。smoke 会检查 edge、静态资源、深层 Admin 路由、API 健康响应、非 root 运行身份，以及 PostgreSQL 停止后的 `503` 与恢复后的 `200`。`make compose-down` 不带 `-v`，数据库 volume 会保留。

## 质量检查

```bash
make check
```

`make check` 不启动 Docker，也不要求 Compose 已运行。它依次执行：

```bash
node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
corepack pnpm --filter @company/web check
corepack pnpm --filter @company/admin check
cd apps/api && uv run ruff check .
cd apps/api && uv run mypy src
cd apps/api && uv run pytest
```

三组 Node 测试检查既有文档、浏览器原型和工程契约。两个前端 `check` 各自运行 lint、类型检查、单元测试和生产构建。API 检查运行 Ruff、严格 mypy 和 pytest。

## Make 目标与底层命令

Makefile 支持 `UV=/path/to/uv` 和 `PNPM='corepack pnpm'` 覆盖，表中列出默认命令。

| Make 目标 | 底层命令 |
| --- | --- |
| `make setup` | 版本检查；`corepack pnpm install --frozen-lockfile`；`cd apps/api && uv sync --frozen` |
| `make dev-infra` | `docker compose --env-file .env up -d postgres` |
| `make dev` | `make -j3 dev-web dev-admin dev-api` |
| `make dev-web` | `corepack pnpm --filter @company/web dev` |
| `make dev-admin` | `corepack pnpm --filter @company/admin dev` |
| `make dev-api` | `cd apps/api && uv run --env-file ../../.env uvicorn --factory company_api.main:create_app --reload --host 0.0.0.0 --port 8000` |
| `make check` | 三组 Node 测试、两个前端 `check`、API 的 Ruff/mypy/pytest，具体命令见上一节 |
| `make compose-up` | `docker compose --env-file .env up --build -d` |
| `make compose-smoke` | `./scripts/compose-smoke.sh` |
| `make compose-down` | `docker compose --env-file .env down` |

## 常见问题

### 端口被占用

用 `lsof -nP -iTCP:3000 -iTCP:5173 -iTCP:8000 -iTCP:8080 -iTCP:5432 -sTCP:LISTEN` 找出占用进程。先停止旧开发服务器或旧 Compose 项目，再重试。不要在 Compose 文件里临时发布 Web、Admin 或 API 端口。

### 找不到 uv

按 [uv 安装文档](https://docs.astral.sh/uv/getting-started/installation/) 安装 `0.11.29`，确认 `uv --version` 后再运行 `make setup`。如果 uv 位于自定义路径，可运行 `make setup UV=/path/to/uv`。

### 数据库未 ready

先运行 `docker compose --env-file .env ps postgres`，再看 `docker compose --env-file .env logs postgres`。混合开发还要确认 `.env` 的数据库主机为 `127.0.0.1`。PostgreSQL 停止时，API 存活接口仍返回 `200`，就绪接口返回 `503`。

### registry 拉取超时

运行 `docker pull postgres:18.4-alpine` 判断 registry 是否可达。超时通常来自 DNS、代理或镜像站配置。修复 Docker daemon 的网络设置后重试 `make compose-up`；不要把镜像标签改成 `latest`。

### Apple Silicon 镜像错误

先用 `uname -m` 确认宿主机架构，再用 `docker buildx imagetools inspect <镜像:标签>` 查看镜像清单是否包含 `linux/arm64`。如果 registry 返回 `no matching manifest for linux/arm64/v8`，选择同版本的多架构镜像。不要用 `platform: linux/amd64` 长期掩盖架构问题。

## 当前不包含

本里程碑不包含登录与权限、公司资料 CRUD、快照上传、HTML 发布、搜索、任务队列和生产部署。页面和 API 只证明工程边界、路由、健康检查与质量门槛可运行。下一里程碑应先从 `doc/README.md`、`doc/BACKEND.md` 和 `doc/PRODUCT_UI.md` 选定一个业务切片，再补测试与实现。
