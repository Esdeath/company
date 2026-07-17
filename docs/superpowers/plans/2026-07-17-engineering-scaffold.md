# 企业快照库工程骨架实施计划

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task in the current session. Each implementation task must be followed by a specification review and a code-quality review before moving on.

**Goal:** 建立一个可学习、可验证、可用 Docker Compose 运行的企业快照库工程骨架，包含 Nuxt 公开端、Vue/Vite 管理端、FastAPI、PostgreSQL 与 Nginx，但不提前实现任何快照业务。

**Architecture:** 根目录使用 pnpm workspace 管理两个 TypeScript 应用，FastAPI 在独立 uv 项目中管理。混合开发模式在宿主机运行前端和 API，只用 Docker 运行 PostgreSQL；完整验收模式由 Compose 启动五个服务，并只通过 loopback 上的 Nginx edge 暴露应用入口。

**Tech Stack:** Node.js 24.18.0、pnpm 10.29.0、TypeScript 5.9.3、Nuxt 4.4.8、Vue 3.5.40、Vite 8.1.5、Python 3.13、uv 0.11.29、FastAPI 0.139.2、SQLAlchemy 2.0.51、psycopg 3.3.4、PostgreSQL 18.4、Nginx 1.30.4、Vitest、pytest、Ruff、mypy、Docker Compose。

---

## 执行前约束

- 设计依据是 `docs/superpowers/specs/2026-07-17-engineering-scaffold-design.md`。
- `doc/` 是当前产品设计主线，本计划不得修改 `doc/` 中任何文件。
- 不处理仓库根目录现有的未跟踪文件：
  - `价值线_哔哩哔哩_企业快照版.html`
  - `价值线_哔哩哔哩_企业快照版.md`
  - `skills/`
- 第一里程碑明确不做：快照导入、MD 解析、业务表、Alembic、登录、权限、CSRF、原型迁移、TLS、阿里云部署、备份、CI/CD。
- 所有新功能按 RED → GREEN → REFACTOR 执行。不要先写实现再补测试。
- 每个任务只提交该任务声明的文件，提交前先运行 `git status --short`，不得使用 `git add .`。
- 若某个精确 Docker 标签无法拉取，先记录命令和错误，再选择同一产品、同一版本的官方等价标签；不得静默改为 `latest`。
- 宿主机缺少目标版 uv 时，不自动修改用户全局环境。可以用官方固定版本容器完成锁文件和检查，并在 README 写清本机安装命令。

## 目标接口与不变量

完成后必须满足：

```text
混合开发：
  http://localhost:3000/                 Nuxt
  http://localhost:5173/admin/           Vue/Vite
  http://localhost:8000/api/health/live  FastAPI
  127.0.0.1:5432                         PostgreSQL

完整 Compose：
  http://127.0.0.1:8080/                 Nuxt（经 edge）
  http://127.0.0.1:8080/admin             308 → /admin/
  http://127.0.0.1:8080/admin/            Admin（经 edge）
  http://127.0.0.1:8080/api/health/live   API（经 edge）
  http://127.0.0.1:8080/healthz           edge 自检
```

```json
GET /api/health/live  -> 200 {"status":"live"}
GET /api/health/ready -> 200 {"status":"ready"}
数据库不可用           -> 503 {"status":"not_ready"}
```

完整 Compose 中只有 edge 发布应用端口；PostgreSQL 只绑定 loopback，Web、Admin、API 不发布宿主机端口。

---

## Task 1：建立根工作区与版本契约

**Files:**

- Create: `tests/scaffold.test.mjs`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `.nvmrc`
- Create: `.python-version`
- Create: `.env.example`
- Create: `.dockerignore`
- Modify: `.gitignore`
- Create: `Makefile`

### Step 1：先写工程结构契约测试

在 `tests/scaffold.test.mjs` 使用 Node 内置 `node:test`，避免根测试依赖尚未安装的第三方包。测试内容至少包括：

```js
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('locks the agreed toolchain versions', async () => {
  assert.equal((await read('.nvmrc')).trim(), '24.18.0')
  assert.equal((await read('.python-version')).trim(), '3.13')

  const rootPackage = JSON.parse(await read('package.json'))
  assert.equal(rootPackage.private, true)
  assert.equal(rootPackage.packageManager, 'pnpm@10.29.0')
  assert.equal(rootPackage.engines.node, '>=24.18.0 <25')
})

test('declares only the two JavaScript applications as workspace packages', async () => {
  const workspace = await read('pnpm-workspace.yaml')
  assert.match(workspace, /apps\/web/)
  assert.match(workspace, /apps\/admin/)
  assert.doesNotMatch(workspace, /apps\/api/)
})

test('publishes a safe local environment template', async () => {
  const env = await read('.env.example')
  for (const key of [
    'POSTGRES_DB',
    'POSTGRES_USER',
    'POSTGRES_PASSWORD',
    'DATABASE_URL',
    'CORS_ORIGINS',
  ]) assert.match(env, new RegExp(`^${key}=`, 'm'))
  assert.doesNotMatch(env, /ayaseeri|buffett/i)
})
```

再增加两个测试：

1. `.gitignore` 必须忽略 `.env`、`.env.*`，但用 `!.env.example` 放行模板；保留原有 `.superpowers/`、构建目录和 Python 缓存规则。
2. `.dockerignore` 必须排除 `.git`、`.env*`、`.superpowers`、`node_modules`、`.nuxt`、`.output`、`dist`、`.venv`、`__pycache__`，并用 `!.env.example` 放行模板。

### Step 2：确认测试先失败

Run:

```bash
node --test tests/scaffold.test.mjs
```

Expected: FAIL，至少提示 `package.json` 或 `.nvmrc` 不存在。

### Step 3：写最小根配置

创建根 `package.json`：

```json
{
  "name": "company-research-library",
  "private": true,
  "packageManager": "pnpm@10.29.0",
  "engines": {
    "node": ">=24.18.0 <25"
  },
  "scripts": {
    "dev": "pnpm --parallel --filter @company/web --filter @company/admin dev",
    "check": "pnpm --recursive check"
  }
}
```

创建 `pnpm-workspace.yaml`：

```yaml
packages:
  - apps/web
  - apps/admin
```

创建：

```text
.nvmrc          24.18.0
.python-version 3.13
```

创建 `.env.example`：

```dotenv
POSTGRES_DB=company
POSTGRES_USER=company
POSTGRES_PASSWORD=company_local_only
DATABASE_URL=postgresql+psycopg://company:company_local_only@postgres:5432/company
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

创建 `.dockerignore`，并只向现有 `.gitignore` 追加缺失的工具缓存，例如 `.ruff_cache/`、`.mypy_cache/`、`coverage/`，不要删除现有规则。

创建初版 `Makefile`，目标先作为稳定接口存在：

```make
.PHONY: setup dev-infra dev check compose-up compose-smoke compose-down

setup:
	corepack pnpm install --frozen-lockfile
	cd apps/api && uv sync --frozen

dev-infra:
	docker compose up -d postgres

dev:
	corepack pnpm run dev

check:
	node --test tests/*.test.mjs
	corepack pnpm run check
	cd apps/api && uv run ruff check .
	cd apps/api && uv run mypy src
	cd apps/api && uv run pytest

compose-up:
	docker compose up --build -d

compose-smoke:
	./scripts/compose-smoke.sh

compose-down:
	docker compose down
```

说明：此时部分目标引用后续任务才会创建的文件，所以 Task 1 只运行结构契约测试，不运行 `make check`。

### Step 4：运行结构契约和旧测试

Run:

```bash
node --test tests/scaffold.test.mjs
node --test tests/docs.test.mjs tests/prototype.test.mjs
```

Expected: 新结构测试 PASS；现有 46 个仓库级测试仍 PASS。

### Step 5：精确提交

```bash
git status --short
git add tests/scaffold.test.mjs package.json pnpm-workspace.yaml .nvmrc .python-version .env.example .dockerignore .gitignore Makefile
git commit -m "build: establish workspace contracts"
```

---

## Task 2：用测试驱动实现 FastAPI 健康服务

**Files:**

- Create: `apps/api/pyproject.toml`
- Create: `apps/api/uv.lock`
- Create: `apps/api/src/company_api/__init__.py`
- Create: `apps/api/src/company_api/config.py`
- Create: `apps/api/src/company_api/db.py`
- Create: `apps/api/src/company_api/main.py`
- Create: `apps/api/tests/test_health.py`
- Create: `apps/api/tests/test_config.py`
- Create: `apps/api/Dockerfile`

### Step 1：声明 API 工具与依赖契约

`apps/api/pyproject.toml` 使用 `requires-python = ">=3.13,<3.14"`，主依赖固定兼容系列：

```toml
[project]
name = "company-api"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "fastapi==0.139.2",
  "pydantic==2.13.4",
  "pydantic-settings==2.14.2",
  "psycopg[binary]==3.3.4",
  "sqlalchemy==2.0.51",
  "uvicorn[standard]==0.51.0",
]

[build-system]
requires = ["uv_build>=0.11.29,<0.12"]
build-backend = "uv_build"

[tool.uv]
package = true

[dependency-groups]
dev = [
  "httpx>=0.28,<0.29",
  "mypy==2.3.0",
  "pytest==9.1.1",
  "ruff==0.15.22",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.13"
strict = true
packages = ["company_api"]
mypy_path = "src"
```

生成锁文件时优先运行：

```bash
cd apps/api
uv lock --python 3.13
```

若宿主机仍无 uv，使用固定版本官方镜像在项目目录生成：

```bash
docker run --rm -v "$PWD:/work" -w /work ghcr.io/astral-sh/uv:0.11.29 \
  uv lock --python 3.13
```

### Step 2：先写健康接口测试

`apps/api/tests/test_health.py` 定义一个可注入的探针协议替身：

```python
from fastapi.testclient import TestClient

from company_api.config import Settings
from company_api.main import create_app


class SuccessfulProbe:
    async def check(self) -> None:
        return None


class FailingProbe:
    async def check(self) -> None:
        raise RuntimeError(
            "postgresql+psycopg://company:secret@postgres:5432/company"
        )


def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://company:local@postgres:5432/company",
        cors_origins="http://localhost:3000,http://localhost:5173",
    )
```

必须覆盖：

- `live` 返回严格的 200/JSON，并验证即使传入 `FailingProbe` 也不会调用数据库。
- `ready` 在 `SuccessfulProbe` 下返回严格的 200/JSON。
- `ready` 在 `FailingProbe` 下返回严格的 503/JSON。
- 503 响应体不包含 `postgres`、数据库用户名、密码、异常类型或原始错误文本。
- CORS 对 `http://localhost:3000` 返回允许头，对未配置域名不返回允许头。

`apps/api/tests/test_config.py` 必须覆盖：

- `DATABASE_URL` 缺失时 `Settings()` 抛出校验错误。
- 空白 `CORS_ORIGINS` 被解析为 `[]`。
- 逗号分隔来源去空格并得到两个 URL。

### Step 3：确认 API 测试先失败

Run:

```bash
cd apps/api
uv run pytest -q
```

Expected: FAIL，提示 `company_api.config` 或 `company_api.main` 不存在。

### Step 4：实现最小配置、数据库探针和应用工厂

`config.py` 的公开接口固定为：

```python
class Settings(BaseSettings):
    database_url: str
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]: ...
```

使用 `SettingsConfigDict(extra="ignore")`，由进程环境统一提供配置；不要让应用根据当前工作目录猜测 `.env` 的位置。混合开发通过 `uv run --env-file ../../.env ...` 显式读取根 `.env`，Compose 则通过 `environment` 注入。`database_url` 没有默认值，保证缺配置时 fail fast。

`db.py` 的公开接口固定为：

```python
from typing import Protocol

class ReadinessProbe(Protocol):
    async def check(self) -> None: ...

class SqlAlchemyReadinessProbe:
    def __init__(self, engine: AsyncEngine) -> None: ...
    async def check(self) -> None: ...  # async with connect; SELECT 1
```

注意：async SQLAlchemy + psycopg 3 使用 `postgresql+psycopg://` 即可。不要建立模型或 metadata。

`main.py` 的公开接口固定为：

```python
def create_app(
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI: ...
```

约束：

- `settings is None` 时才从环境创建 `Settings()`。
- 测试传入 probe 时，不创建真实 engine。
- 默认路径在 lifespan 中创建 engine，退出时 `await engine.dispose()`。
- `/api/health/live` 不读取 probe。
- `/api/health/ready` 捕获探针异常，使用 `logger.exception` 记录，但只返回固定 503 载荷。
- 响应使用显式 Pydantic 模型或等价的严格字面值结构。
- CORS 只使用 `settings.cors_origin_list`，不允许 `*`，且 `allow_credentials=True`。

### Step 5：运行 API 质量门槛

Run:

```bash
cd apps/api
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected: 全部 PASS。

### Step 6：添加非 root API 镜像

`apps/api/Dockerfile` 使用多阶段构建，固定：

```dockerfile
FROM ghcr.io/astral-sh/uv:0.11.29 AS uv
FROM python:3.13-slim-bookworm AS runtime
```

实现要求：

- 从 uv 镜像复制 `/uv` 和 `/uvx`。
- 设置 `UV_COMPILE_BYTECODE=1`、`UV_LINK_MODE=copy`。
- 先复制 `pyproject.toml` 和 `uv.lock`，执行 `uv sync --frozen --no-dev --no-install-project`。
- 再复制 `src/`，执行 `uv sync --frozen --no-dev`。
- 创建非 root 用户 `app`，最终 `USER app`。
- `EXPOSE 8000`。
- 启动命令：

```dockerfile
CMD ["uv", "run", "--no-sync", "uvicorn", "--factory", "company_api.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
```

Run:

```bash
docker build -t company-api:test apps/api
docker run --rm company-api:test id -u
```

Expected: 构建成功；UID 不是 `0`。容器缺 `DATABASE_URL` 时应快速失败，证明配置没有隐式生产默认值。

### Step 7：精确提交

```bash
git status --short
git add apps/api
git commit -m "feat: add FastAPI health service"
```

---

## Task 3：用测试驱动建立 Nuxt 公开端骨架

**Files:**

- Create: `apps/web/package.json`
- Create: `apps/web/nuxt.config.ts`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/eslint.config.mjs`
- Create: `apps/web/app/app.vue`
- Create: `apps/web/app/assets/css/main.css`
- Create: `apps/web/server/routes/healthz.get.ts`
- Create: `apps/web/tests/app.test.ts`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/Dockerfile`
- Create: `pnpm-lock.yaml`

### Step 1：声明 Web 依赖和检查命令

`apps/web/package.json` 固定包名 `@company/web`，至少包含：

```json
{
  "name": "@company/web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "nuxt dev --host 0.0.0.0 --port 3000",
    "build": "nuxt build",
    "lint": "eslint .",
    "typecheck": "nuxt typecheck",
    "test": "vitest run",
    "check": "pnpm lint && pnpm typecheck && pnpm test && pnpm build"
  }
}
```

主依赖使用 `nuxt==4.4.8`、`vue==3.5.40`。开发依赖使用 TypeScript 5.9.3、Vitest 4.1.10、ESLint 10.7.0，并加入与 Nuxt 4 兼容的 `@nuxt/eslint`、`@vue/test-utils`、`happy-dom`。首次解析后提交根 `pnpm-lock.yaml`。

### Step 2：先写公开端组件测试

`apps/web/tests/app.test.ts` 使用 `@vue/test-utils` 挂载 `app.vue`，断言：

- 页面存在唯一 `h1`，内容为“企业研究资料库”。
- 显示“公开端工程骨架”而非任何虚构业务数据。
- 存在指向 `/admin/` 的管理端入口。
- 不出现贵州茅台、哔哩哔哩或估值结论，防止骨架阶段偷渡业务内容。

### Step 3：确认测试先失败

Run:

```bash
corepack pnpm install
corepack pnpm --filter @company/web test
```

Expected: FAIL，提示 `app/app.vue` 不存在。

### Step 4：实现最小 Nuxt 页面与 health route

`nuxt.config.ts`：

```ts
export default defineNuxtConfig({
  compatibilityDate: '2026-07-17',
  css: ['~/assets/css/main.css'],
  devtools: { enabled: false },
  modules: ['@nuxt/eslint'],
  typescript: { strict: true, typeCheck: true },
})
```

`server/routes/healthz.get.ts`：

```ts
export default defineEventHandler(() => ({ status: 'ok' }))
```

`app.vue` 只做一个移动优先的学习型占位页：品牌、标题、工程状态、公开端/管理端/API 三项边界说明和管理端链接。视觉规则：

- 原生系统与中文字体栈，不引入远程字体。
- 内容宽度、间距、颜色使用 CSS 变量。
- 320px 宽度无横向滚动。
- 语义化 `header`、`main`、`footer`；明显焦点样式。
- 不复制 `doc/prototype.html`，也不显示业务卡片。

### Step 5：运行 Web 门槛

Run:

```bash
corepack pnpm --filter @company/web lint
corepack pnpm --filter @company/web typecheck
corepack pnpm --filter @company/web test
corepack pnpm --filter @company/web build
```

Expected: 全部 PASS，`.output/server/index.mjs` 存在。

### Step 6：添加非 root Nuxt 生产镜像

`apps/web/Dockerfile` 使用 `node:24.18.0-alpine`，分 `deps`、`build`、`runtime` 三阶段：

- 通过 Corepack 使用根 `packageManager` 指定的 pnpm。
- deps 阶段复制根 `package.json`、workspace 文件、lockfile 和 Web 的 package manifest；不要依赖尚未创建或与 Web 无关的 Admin 源码。
- 只安装 Web 的锁定依赖：`pnpm install --frozen-lockfile --filter @company/web...`。
- build 阶段复制 Web 源码并运行 `pnpm --filter @company/web build`。
- runtime 只复制 `.output`，使用镜像内置非 root `node` 用户。
- 设置 `HOST=0.0.0.0`、`PORT=3000`，运行 `node server/index.mjs`。

Run:

```bash
docker build -f apps/web/Dockerfile -t company-web:test .
docker run --rm company-web:test id -u
```

Expected: 构建成功，UID 不是 `0`。

### Step 7：精确提交

```bash
git status --short
git add apps/web pnpm-lock.yaml
git commit -m "feat: add Nuxt public shell"
```

---

## Task 4：用测试驱动建立 Vue/Vite 管理端骨架

**Files:**

- Create: `apps/admin/package.json`
- Create: `apps/admin/index.html`
- Create: `apps/admin/tsconfig.json`
- Create: `apps/admin/tsconfig.app.json`
- Create: `apps/admin/vite.config.ts`
- Create: `apps/admin/eslint.config.mjs`
- Create: `apps/admin/src/env.d.ts`
- Create: `apps/admin/src/main.ts`
- Create: `apps/admin/src/App.vue`
- Create: `apps/admin/src/style.css`
- Create: `apps/admin/tests/App.test.ts`
- Create: `apps/admin/nginx.conf`
- Create: `apps/admin/Dockerfile`
- Modify: `pnpm-lock.yaml`

### Step 1：声明 Admin 依赖和 `/admin/` 基础路径

`apps/admin/package.json` 固定包名 `@company/admin`。脚本与 Web 对齐：`dev`、`build`、`lint`、`typecheck`、`test`、`check`。

主依赖：Vue 3.5.40。开发依赖固定 TypeScript 5.9.3、Vite 8.1.5、`@vitejs/plugin-vue` 6.0.8、`vue-tsc` 3.3.7、Vitest 4.1.10、ESLint 10.7.0、Vue ESLint 插件、`@vue/test-utils` 和 `happy-dom`。

`vite.config.ts` 的关键契约：

```ts
export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  server: { host: '0.0.0.0', port: 5173 },
  test: { environment: 'happy-dom' },
})
```

### Step 2：先写管理端组件和构建路径测试

`tests/App.test.ts` 断言：

- 唯一 `h1` 为“资料管理后台”。
- 显示“管理端工程骨架”。
- 明确写出“登录与资料上传将在后续里程碑实现”。
- 有返回公开端 `/` 的链接。
- 不出现用户名输入、密码输入、上传按钮，防止占位控件被误解为已实现。

在根 `tests/scaffold.test.mjs` 增加构建配置静态契约：读取 `apps/admin/vite.config.ts`，确认 `base: '/admin/'` 存在。

### Step 3：确认测试先失败

Run:

```bash
corepack pnpm install
corepack pnpm --filter @company/admin test
node --test tests/scaffold.test.mjs
```

Expected: Admin 测试 FAIL，提示 `src/App.vue` 不存在；结构测试在实现 base 前 FAIL。

### Step 4：实现最小管理端页面

页面使用与 Web 一致的设计 token，但保持管理工具气质：

- 移动优先；320px 无横向滚动。
- 顶部有“企业研究资料库 / 管理端”文字标识。
- 主区只显示里程碑说明、后续能力清单和公开端返回链接。
- 语义化结构、键盘焦点状态，不使用假表单或假数据。

TypeScript 配置启用 `strict`、`noUnusedLocals`、`noUnusedParameters`、`noFallthroughCasesInSwitch`。

### Step 5：运行 Admin 门槛并验证产物路径

Run:

```bash
corepack pnpm --filter @company/admin lint
corepack pnpm --filter @company/admin typecheck
corepack pnpm --filter @company/admin test
corepack pnpm --filter @company/admin build
grep -Eo '/admin/assets/[^" ]+' apps/admin/dist/index.html
```

Expected: 全部 PASS；grep 至少输出一个 `/admin/assets/...` 路径。

### Step 6：添加内部静态 Nginx 与非 root 镜像

`apps/admin/nginx.conf` 监听 `8080`，包含：

```nginx
location = /healthz {
    access_log off;
    default_type application/json;
    return 200 '{"status":"ok"}';
}

location / {
    try_files $uri $uri/ /index.html;
}
```

`apps/admin/Dockerfile`：

- build 阶段使用 `node:24.18.0-alpine` 和根 lockfile，只复制 Admin 的 package manifest 并执行 filter install，不能要求复制 Web 源码。
- 运行 `pnpm --filter @company/admin build`。
- runtime 使用 `nginxinc/nginx-unprivileged:1.30.4-alpine`。
- 复制自定义配置和 `dist/` 到 `/usr/share/nginx/html`。
- 不切回 root，`EXPOSE 8080`。

Run:

```bash
docker build -f apps/admin/Dockerfile -t company-admin:test .
docker run --rm company-admin:test id -u
```

Expected: 构建成功；UID 不是 `0`。

### Step 7：精确提交

```bash
git status --short
git add apps/admin pnpm-lock.yaml tests/scaffold.test.mjs
git commit -m "feat: add Vue admin shell"
```

---

## Task 5：建立 Edge、Compose 与故障恢复 smoke test

**Files:**

- Create: `infra/nginx/default.conf`
- Create: `compose.yaml`
- Create: `scripts/compose-smoke.sh`
- Modify: `tests/scaffold.test.mjs`

### Step 1：先写 Compose 和 Nginx 静态契约测试

在 `tests/scaffold.test.mjs` 增加断言：

- `compose.yaml` 正好声明 `edge`、`web`、`admin`、`api`、`postgres` 五个服务。
- 镜像标签包含 `postgres:18.4-alpine` 与 `nginxinc/nginx-unprivileged:1.30.4-alpine`，不包含 `:latest`。
- edge 绑定 `127.0.0.1:8080:8080`。
- postgres 绑定 `127.0.0.1:5432:5432`。
- Web、Admin、API 没有 `ports:`，只允许 `expose:`。
- `default.conf` 中 `/admin` 使用 308；`/api/` 的 `proxy_pass` 不附加 URI；四个基础代理头存在。
- `scripts/compose-smoke.sh` 中不存在 `sleep 10`、`sleep 30` 等长固定等待，必须存在带超时的 polling helper。

测试不要用脆弱的整文件快照；使用小范围正则和 `docker compose config --format json` 的独立 shell 验证补足语义检查。

### Step 2：确认测试先失败

Run:

```bash
node --test tests/scaffold.test.mjs
```

Expected: FAIL，提示 `compose.yaml` 或 Nginx 配置不存在。

### Step 3：实现 Edge Nginx 路由

`infra/nginx/default.conf` 监听非特权端口 8080，关键顺序：

```nginx
location = /healthz { return 200 '{"status":"ok"}'; }
location = /admin { return 308 /admin/; }

location /admin/ {
    proxy_pass http://admin:8080/;
    # common proxy headers
}

location /api/ {
    proxy_pass http://api:8000;
    # common proxy headers
}

location / {
    proxy_pass http://web:3000;
    # common proxy headers
}
```

`/admin/` 的 `proxy_pass` 带尾斜杠以去掉前缀；`/api/` 不带尾斜杠以保留完整路径。配置基础代理头：`Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`。

### Step 4：实现五服务 Compose

`compose.yaml` 约束：

- `name: company-research-library`。
- `postgres` 使用 `.env`/默认插值，默认值仅为明显的本地开发值。
- `postgres` 使用命名 volume `postgres_data`，健康检查 `pg_isready -U ... -d ...`。
- API 的 `DATABASE_URL` 主机固定为服务名 `postgres`，不可从宿主机值误用 `localhost`。
- API 依赖 `postgres: condition: service_healthy`。
- web/admin/api 各自定义健康检查，并仅 `expose` 内部端口。
- edge 依赖三个上游 healthy，唯一应用端口为 `127.0.0.1:8080:8080`。
- postgres 为混合开发保留 `127.0.0.1:5432:5432`。
- 所有服务设置 `restart: unless-stopped`；开发 smoke 环境可通过 `docker compose stop` 验证故障。

先运行语义解析：

```bash
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --format json > /tmp/company-compose.json
```

Expected: 命令退出 0，渲染配置中无空环境变量。

### Step 5：先写会失败的 smoke script

`scripts/compose-smoke.sh` 使用 `set -Eeuo pipefail`，定义：

```bash
wait_for_http() {
  local url=$1 expected=$2 timeout=${3:-60}
  local deadline=$((SECONDS + timeout))
  while (( SECONDS < deadline )); do
    code=$(curl --silent --output /tmp/company-smoke-body --write-out '%{http_code}' "$url" || true)
    [[ "$code" == "$expected" ]] && return 0
    sleep 1
  done
  return 1
}
```

脚本必须逐项验证：

1. `docker compose ps` 五个服务均 running/healthy。
2. edge `/healthz` 200。
3. `/` 200，正文包含“企业研究资料库”。
4. `/admin` 严格返回 308，`Location` 为 `/admin/`。
5. `/admin/` 200，正文包含“资料管理后台”。
6. `/api/health/live` 200 且 JSON 严格等于 `{"status":"live"}`。
7. `/api/health/ready` 200 且 JSON 严格等于 `{"status":"ready"}`。
8. `docker compose port web 3000`、admin 8080、api 8000 都无宿主机映射。
9. `docker compose stop postgres` 后，轮询 ready 直到 503，响应严格为 `{"status":"not_ready"}` 且不含连接信息。
10. `docker compose start postgres` 后，轮询 ready 恢复 200。

故障注入后即使某步失败，也必须通过 trap 尽力重新启动 postgres；脚本不得自动 `down -v`。

### Step 6：运行完整 Compose 验收

Run:

```bash
docker compose --env-file .env.example build
docker compose --env-file .env.example up -d
./scripts/compose-smoke.sh
docker compose --env-file .env.example down
```

Expected: build、up、smoke、down 全部退出 0；命名 volume 保留。

若 registry 拉取精确标签超时，先单独验证并记录：

```bash
docker buildx imagetools inspect node:24.18.0-alpine
docker buildx imagetools inspect python:3.13-slim-bookworm
docker buildx imagetools inspect postgres:18.4-alpine
docker buildx imagetools inspect nginxinc/nginx-unprivileged:1.30.4-alpine
docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.11.29
```

网络超时不是更改版本策略的理由；重试或记录外部阻塞。

### Step 7：精确提交

```bash
git status --short
git add infra/nginx/default.conf compose.yaml scripts/compose-smoke.sh tests/scaffold.test.mjs
git commit -m "feat: add local full-stack runtime"
```

---

## Task 6：完善学习文档并做最终全链路复核

**Files:**

- Create: `README.md`
- Modify: `Makefile`
- Modify: `tests/scaffold.test.mjs`

### Step 1：先写 README 和 Make 接口契约测试

在 `tests/scaffold.test.mjs` 增加测试，读取 `README.md` 和 `Makefile`，要求：

- README 明确出现 `make setup`、`make dev-infra`、`make dev`、`make check`、`make compose-up`、`make compose-smoke`、`make compose-down`。
- README 同时给出每个 Make 目标对应的直接 pnpm、uv 或 Docker Compose 命令，不能把 Makefile 变成黑箱。
- README 解释混合开发与完整 Compose 两种模式。
- README 包含五个服务的职责和目录导航。
- README 明确声明本里程碑“不包含什么”。
- README 包含宿主机 Node/pnpm/uv/Python/Docker 版本检查命令。
- README 说明 `.env.example` 只含本地开发凭据，真实环境不得复用。
- Makefile 七个公共目标都存在，且 `check` 不依赖已运行的 Compose。

### Step 2：确认文档测试先失败

Run:

```bash
node --test tests/scaffold.test.mjs
```

Expected: FAIL，提示根 README 不存在或缺少命令说明。

### Step 3：写学习导向 README

README 按以下顺序组织：

1. 项目当前处于“工程骨架”里程碑。
2. 架构图（简洁文本或 Mermaid）与五个服务职责。
3. 目录结构。
4. 版本要求与逐条检查命令。
5. 第一次安装：复制 `.env.example`、安装 JS/Python 依赖。
6. 混合开发：四个终端分别做什么、访问哪些地址。
7. 完整 Compose：up、smoke、down。
8. 质量检查：每项工具检查什么。
9. Make 目标与底层命令对照表。
10. 常见问题：端口占用、缺 uv、数据库未 ready、registry 超时、Apple Silicon 镜像。
11. 当前不包含的业务能力与下一里程碑入口。

文档不能宣称登录、快照上传或 HTML 发布已经可用。

### Step 4：收紧 Makefile

最终目标行为：

- `setup`：验证版本提示，安装 pnpm workspace 和 uv 锁定依赖。
- `dev-infra`：只启动 postgres。
- `dev`：通过 `$(MAKE) -j3 dev-web dev-admin dev-api` 并行启动三个本机开发服务；`dev-api` 使用 `cd apps/api && uv run --env-file ../../.env uvicorn --factory company_api.main:create_app --reload --host 0.0.0.0 --port 8000`。三个内部目标也写入 README，便于用户在三个终端分别观察日志；Ctrl-C 必须能终止子进程。
- `check`：仓库 Node 测试、两个前端 check、API Ruff/mypy/pytest；不启动 Docker。
- `compose-up`：`docker compose --env-file .env up --build -d`，若 `.env` 不存在给出清晰提示。
- `compose-smoke`：调用脚本。
- `compose-down`：不带 `-v`，保留数据库。

优先保持 Makefile 可读。不要为了“一条命令启动一切”引入未锁定的进程管理器。

### Step 5：执行无 Docker 的完整质量门槛

Run:

```bash
make check
```

Expected:

- `tests/docs.test.mjs` 18/18 PASS。
- `tests/prototype.test.mjs` 28/28 PASS，并完成原有真实浏览器检查。
- `tests/scaffold.test.mjs` 全部 PASS。
- Web/Admin lint、typecheck、unit test、build 全部 PASS。
- API Ruff、mypy、pytest 全部 PASS。

若仓库 Node 测试的 glob 顺序导致真实浏览器测试未被执行，必须显式列出三个文件而不是弱化检查。

### Step 6：执行最终 Compose 验收

Run:

```bash
cp .env.example .env
make compose-up
make compose-smoke
docker compose ps
make compose-down
docker compose ps --all
```

Expected:

- smoke 全部 PASS，包括 PostgreSQL 停止后的 503 和恢复后的 200。
- up 期间只有 `127.0.0.1:8080` 和 `127.0.0.1:5432` 对宿主机可见。
- down 后无运行容器，`postgres_data` volume 保留。
- `.env` 仍为 ignored，不进入 Git。

随后删除只为本机验收复制的 `.env`，不要删除 volume：

```bash
rm .env
```

### Step 7：检查范围和安全不变量

Run:

```bash
git status --short
git diff --check
git diff --name-only HEAD
git ls-files .env
git grep -n 'company_local_only' -- ':!.env.example' ':!compose.yaml' ':!README.md' ':!docs/**'
```

Expected:

- `git diff --check` 无输出。
- `git ls-files .env` 无输出。
- 没有真实凭据。
- `doc/` 无修改。
- 根目录既有未跟踪的 Bilibili 文件与 `skills/` 状态保持不变。

### Step 8：提交 README 与最终命令整理

```bash
git add README.md Makefile tests/scaffold.test.mjs
git commit -m "docs: explain local development workflow"
```

### Step 9：提交后重新验证并请求代码审查

必须在最终提交后重新运行，而不是引用提交前结果：

```bash
make check
cp .env.example .env
make compose-up
make compose-smoke
make compose-down
rm .env
git status --short
```

然后使用 `superpowers:requesting-code-review` 做最终审查。审查范围从计划开始前的提交 `e1b8c24` 到当前 HEAD，重点检查：

- 是否实现了任何越界业务。
- API live 是否真的不碰数据库。
- ready 错误是否泄漏连接信息。
- `/admin/` 和 `/api/` 的 Nginx URI 语义是否正确。
- Compose 是否意外发布 Web/Admin/API 端口。
- Docker runtime 是否非 root。
- README 是否与真实命令一致。

只在审查问题修复、`make check` 与 Compose smoke 都重新通过后，才可以声明第一里程碑完成。

---

## 完成定义

以下条件全部满足才算完成：

- [ ] 根工作区、版本文件和锁文件已提交。
- [ ] Web、Admin、API 各自有最小页面/接口、测试、类型检查、lint 和生产构建。
- [ ] API live/ready 语义和故障隐私测试通过。
- [ ] 五服务 Compose 可启动，edge 路由正确。
- [ ] PostgreSQL 故障与恢复 smoke test 通过。
- [ ] 运行时容器非 root，基础镜像没有 `latest`。
- [ ] 完整 Compose 只发布 edge 和 loopback PostgreSQL 端口。
- [ ] 根 README 可以让学习者不用猜测地运行两种开发模式。
- [ ] `doc/` 和既有未跟踪文件未被改动。
- [ ] 现有文档/原型测试与所有新增测试通过。
- [ ] 最终代码审查无未处理的阻断问题。
