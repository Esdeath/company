# AGENTS.md

This file provides guidance to Codex and other AI coding agents when working with code in this repository.

## 项目概述

企业研究资料库:管理员在管理端创建公司并上传 HTML/Markdown 研究资料,公开站点按公司浏览与阅读。Markdown 上传时渲染为展示 HTML,HTML 保持原文;两者用同一个空 `sandbox` iframe 阅读器展示。数据库只保存公司与资料索引,文件正文存放在 `CONTENT_ROOT` 文件系统目录。

## 常用命令

```bash
make setup          # 安装锁定依赖(pnpm frozen + uv sync --frozen)
make dev-infra      # 只启动 Compose 中的 PostgreSQL(混合开发)
make dev            # 并行启动 web/admin/api 三个开发服务器
make db-upgrade     # alembic upgrade head
make check          # 全量质量检查(不需要 Docker)
make compose-up     # 完整五服务 Compose 构建并启动
make compose-smoke  # 端到端冒烟测试(需 Compose 已启动)
make compose-down   # 停止 Compose(保留 volume)
make deploy-aliyun  # 部署阿里云 ECS(日常更新一条命令)
```

混合开发前先把 `.env` 中 `DATABASE_URL` 的主机从 `postgres` 改为 `127.0.0.1`。开发地址:Web `http://127.0.0.1:3000`,Admin `http://127.0.0.1:5173/admin/`,API `http://127.0.0.1:8000`;完整 Compose 入口 `http://127.0.0.1:8080`。

### 分项检查与单个测试

`make check` 依次执行以下命令,可单独运行定位问题:

```bash
# 根目录工程契约测试(Node 内置 test runner)
node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs

# 前端(check = lint + typecheck + test + build)
corepack pnpm --filter @company/web check
corepack pnpm --filter @company/admin check
corepack pnpm --filter @company/web exec vitest run tests/某文件.test.ts   # 单个前端测试文件

# API(在 apps/api 目录下)
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest                                    # 全部
uv run pytest tests/test_routes.py               # 单文件
uv run pytest tests/test_routes.py::test_某用例   # 单用例
```

### 工具链约定

- Node 24.18.0(`.nvmrc`)、pnpm 10.34.5(经 corepack)、uv 0.11.29、Python 3.13。
- 所有依赖都走 frozen lockfile;lockfile 不一致时不要用非 frozen 安装绕过,应与声明文件一起重新生成并提交。
- Python 一律通过 `uv run` 执行;pnpm 一律通过 `corepack pnpm` 执行。

## 架构

五个服务,完整 Compose 只向宿主机发布 `127.0.0.1:8080`(edge)和 `127.0.0.1:5432`(postgres):

```
浏览器 → edge(Nginx, infra/nginx/default.conf)
           ├── /        → web   (Nuxt 4,      apps/web)
           ├── /admin/  → admin (Vue 3 + Vite, apps/admin)
           └── /api/    → api   (FastAPI,     apps/api) → postgres
```

### API 分层(apps/api/src/company_api)

- `main.py`:`create_app` 工厂(uvicorn 用 `--factory` 启动),组装依赖并注册路由。
- `routes.py` → `library_service.py` → `repository.py`(PostgreSQL 索引)+ `content_store.py`(文件系统正文):资料主线。上传按扩展名分流,`rendering.py` 把 Markdown 渲染成展示 HTML(模板在 `templates/`)。单个文件失败只清理该文件的临时数据,不影响同批次其他文件。
- `auth_routes.py` → `auth.py` → `auth_repository.py`:单管理员认证。Argon2 密码哈希,会话存 PostgreSQL,`HttpOnly` Cookie;所有写操作同时要求会话 Cookie 和 `X-CSRF-Token` 头。
- 数据库迁移用 Alembic(`apps/api/migrations`),API 容器启动时先跑 migration 再起 Uvicorn。

### 关键约定

- OpenAPI 是前后端接口契约来源。
- Skill 输出(HTML/Markdown)视为可信管理员输入,系统按扩展名处理,不检查正文内容。
- `tests/scaffold.test.mjs` 等根目录测试锁定工程契约(文件存在性、配置一致性),改动脚手架或文档结构后务必跑一遍。
- 生产边界:宿主机 Nginx 是唯一公网入口(HTTPS),容器端口只绑定回环地址;生产必须 `SESSION_COOKIE_SECURE=true`。部署细节见 `doc/DEPLOYMENT.md`。

## 文档与目录说明

- `doc/` 是当前开发依据(中文):`DEVELOPMENT.md` 总纲、`BACKEND.md`、`PRODUCT_UI.md`、`DEPLOYMENT.md`、`AUTHENTICATION.md`、`SEO.md`,以及 `doc/specs/` 中已确认的设计。
- `docs/superpowers/` 是历史决策记录;与 `doc/` 冲突时以 `doc/` 和已通过的测试为准。
- `doc/prototype.html` 仅是交互参考,不代表已实现功能。
- `stocks/` 按行业存放生成的研究资料(HTML/MD),是内容产物,不是应用代码。
- `skills/hk-value-snapshot/` 是站外运行的资料生成 Skill。
