# `doc/` Mainline Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the conflicting Markdown-era documentation with one concise HTML-publication mainline, organize the checked-in prototype snapshots, and keep the executable prototype and tests working.

**Architecture:** Keep `doc/prototype.html` at its current URL. Make `doc/README.md` the only current-doc entry point, consolidate product/backend/deployment concerns into five focused documents, and separate website HTML artifacts from audit-only Markdown sources under `doc/snapshots/`. Protect the structure and content contract with Node built-in tests; do not add dependencies.

**Tech Stack:** Markdown, standalone HTML/CSS/JavaScript, Node.js `node:test`, headless Chrome/CDP tests already present in `tests/prototype.test.mjs`, Git.

**Design:** `docs/superpowers/specs/2026-07-17-doc-mainline-cleanup-design.md`

## Global Constraints

- HTML is the website's only publishable artifact.
- Markdown is an audit and regeneration source only; runtime code must never read it.
- Both HTML artifacts and Markdown sources must be tracked by Git.
- Keep `doc/prototype.html` at the same path.
- Do not modify or delete the duplicate Bilibili HTML/MD files in the repository root.
- Do not rewrite historical paths in `docs/superpowers/specs/` or `docs/superpowers/plans/`.
- Do not implement Nuxt, Vue admin, FastAPI, PostgreSQL, Nginx, or Docker runtime code in this change.
- Do not add npm packages or any other dependency.
- Use `apply_patch` for textual edits. Mechanical directory creation and file moves may use `mkdir` and `mv` after exact source/destination verification.
- Each task must leave its focused tests green and receive an independent review before the next task starts.

## Target File Map

```text
doc/
├── README.md                 # current status and reading entry point
├── DEVELOPMENT.md            # product and engineering mainline
├── PRODUCT_UI.md             # public and administrator interaction contract
├── BACKEND.md                # API, persistence, validation, workflow
├── DEPLOYMENT.md             # Docker/Nginx/Aliyun operating target
├── SEO.md                    # standalone HTML indexing strategy
├── prototype.html            # executable prototype; path remains stable
└── snapshots/
    ├── published/
    │   ├── 贵州茅台.html
    │   └── 哔哩哔哩.html
    └── sources/
        ├── 贵州茅台.md
        └── 哔哩哔哩.md

tests/
├── docs.test.mjs             # current documentation structure and link contract
└── prototype.test.mjs        # prototype, asset safety, runtime state transitions
```

---

### Task 1: Establish the current documentation entry point

**Files:**
- Create: `tests/docs.test.mjs`
- Create: `doc/README.md`
- Modify: `doc/DEVELOPMENT.md`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-07-17-doc-mainline-cleanup-design.md`; current prototype behavior in `doc/prototype.html`.
- Produces: `readCurrentDoc(name: string): string` test helper; `doc/README.md` as the only current-doc entry; `doc/DEVELOPMENT.md` as the engineering mainline used by later documents.

- [ ] **Step 1: Add failing tests for the entry point and mainline**

Create `tests/docs.test.mjs` with Node built-ins only:

```js
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const docDirectory = new URL('../doc/', import.meta.url);

function currentDocUrl(name) {
  return new URL(name, docDirectory);
}

function readCurrentDoc(name) {
  const url = currentDocUrl(name);
  assert.equal(existsSync(url), true, `missing current document: doc/${name}`);
  return readFileSync(url, 'utf8');
}

test('README is the current documentation entry point', () => {
  const markdown = readCurrentDoc('README.md');
  assert.match(markdown, /^# 企业快照库文档/m);
  assert.match(markdown, /HTML 是网站唯一发布物/);
  assert.match(markdown, /MD.+审计.+重新生成/s);
  assert.match(markdown, /prototype\.html/);
  assert.match(markdown, /DEVELOPMENT\.md/);
  assert.match(markdown, /PRODUCT_UI\.md/);
  assert.match(markdown, /BACKEND\.md/);
  assert.match(markdown, /DEPLOYMENT\.md/);
  assert.match(markdown, /SEO\.md/);
});

test('DEVELOPMENT describes one HTML publication mainline', () => {
  const markdown = readCurrentDoc('DEVELOPMENT.md');
  assert.match(markdown, /^# 企业快照库开发总纲/m);
  assert.match(markdown, /Skill[\s\S]+HTML[\s\S]+校验[\s\S]+审核[\s\S]+发布/);
  assert.match(markdown, /MD.+不参与网站运行/s);
  assert.match(markdown, /Vue.+Nuxt.+Vite.+TypeScript.+FastAPI.+PostgreSQL.+Nginx.+Docker/s);
  assert.doesNotMatch(markdown, /上传 Markdown|扫描 `?content\/inbox|Markdown 是.+唯一事实来源/);
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
node --test tests/docs.test.mjs
```

Expected: FAIL because `doc/README.md` does not exist and the old `DEVELOPMENT.md` still describes Markdown as the website source of truth.

- [ ] **Step 3: Create `doc/README.md`**

Write a concise entry document with this exact information architecture:

```markdown
# 企业快照库文档

## 当前状态

项目当前完成的是可执行 HTML 原型：公开端以公司目录加阅读工作区展示快照，管理端演示 HTML 导入、校验、审核、发布与撤回。Nuxt、Vue 管理端、FastAPI、PostgreSQL 和 Docker 仍是下一阶段的生产目标，不应写成已经实现。

## 唯一内容主线

HTML 是网站唯一发布物。Skill 同时生成的 MD 只用于审计、复查和重新生成，不参与网站上传、解析、预览或发布。

## 从哪里开始

1. 打开 [prototype.html](./prototype.html) 查看当前交互。
2. 阅读 [DEVELOPMENT.md](./DEVELOPMENT.md) 了解产品范围、技术边界和实施顺序。
3. 按任务阅读 [PRODUCT_UI.md](./PRODUCT_UI.md)、[BACKEND.md](./BACKEND.md)、[DEPLOYMENT.md](./DEPLOYMENT.md) 或 [SEO.md](./SEO.md)。

## 样本资产

- `snapshots/published/`：原型直接读取的完整 HTML。
- `snapshots/sources/`：与 HTML 对应的审计源 MD；网站运行时不读取。

## 文档优先级

`doc/` 是当前开发依据。`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 记录历史决策与实施过程；出现差异时，以本目录当前文档和已通过的测试为准。

## 下一步

按 [DEVELOPMENT.md](./DEVELOPMENT.md) 的实施顺序，从仓库骨架、HTML 内容契约和 FastAPI 索引开始建设生产代码。
```

- [ ] **Step 4: Rewrite `doc/DEVELOPMENT.md` around the HTML mainline**

Replace the old Markdown-import design with a focused document containing these sections and decisions:

```markdown
# 企业快照库开发总纲

## 项目目标

保存并阅读 A 股、港股及无上市代码公司的企业研究快照。首版先跑通多公司 HTML 快照的导入、审核、发布和公开阅读。

## 当前实现与目标实现

- 已实现：`doc/prototype.html` 和两家公司样本，覆盖公开工作区、移动抽屉、管理审核、发布状态与加载失败。
- 目标实现：Nuxt 公开端、Vue/Vite 管理端、FastAPI、PostgreSQL、Nginx 和 Docker Compose。

## 唯一内容主线

Codex Skill 生成 HTML 与 MD。HTML 经过校验、人工审核后发布，是网站唯一发布物；MD 只用于审计和重新生成，不参与网站运行。

## 首版范围

包含多公司目录、HTML 阅读、搜索筛选、管理员认证、HTML 上传或扫描、安全校验、审核、发布、撤回、审计、SEO 基础和阿里云部署。不包含在线编辑器、网站内运行 Skill、行情实时刷新、社区功能或复杂组合管理。

## 技术栈

公开端使用 Nuxt、Vue 和 TypeScript；管理端使用 Vue、Vite 和 TypeScript；API 使用 FastAPI；索引和审计使用 PostgreSQL；入口使用 Nginx；本地和阿里云使用 Docker Compose。

## 系统边界

Skill 在网站外运行。只有 FastAPI 可以写生产内容目录和发布状态。Nuxt 与管理端通过 API 读取元数据；公开端与管理端预览同一个 HTML 文件并采用相同 sandbox 规则。数据库不保存 HTML 正文。

## 数据流

Skill → HTML 安全与元数据校验 → 草稿 → 人工审核 → 发布 → 公开阅读。任一文件缺失或加载失败都会形成审核错误并阻断发布。

## 文档地图

- `PRODUCT_UI.md`：公开端和管理端交互。
- `BACKEND.md`：API、索引、状态、校验和审计。
- `DEPLOYMENT.md`：Docker、Nginx、阿里云、备份和回滚。
- `SEO.md`：独立 HTML 地址的索引策略。

## 开发约定

OpenAPI 是前后端契约来源；内容状态变化必须事务化并记录审计；HTML 只能通过统一校验器进入发布状态；文档必须区分“当前已实现”和“目标设计”。

## 测试层级

使用单元测试覆盖元数据和安全校验，集成测试覆盖文件事务与发布状态，浏览器测试覆盖公开目录、管理操作、404、重试、iframe 清理与移动抽屉。

## 实施顺序

1. 建立 Nuxt、Vue/Vite、FastAPI 和 Compose 仓库骨架。
2. 实现 HTML 元数据、安全校验和内容路径契约。
3. 建立 PostgreSQL 迁移、管理员认证和审计。
4. 实现导入、审核、发布、撤回和公开读取 API。
5. 将已验证的原型交互迁移到公开端和管理端。
6. 完成 Nginx、阿里云、SEO、备份和发布检查。
```

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run:

```bash
node --test tests/docs.test.mjs
git diff --check
```

Expected: both documentation tests PASS; `git diff --check` exits 0.

- [ ] **Step 6: Commit Task 1**

```bash
git add tests/docs.test.mjs doc/README.md doc/DEVELOPMENT.md
git commit -m "docs: establish HTML publication mainline"
```

---

### Task 2: Consolidate product UI and backend contracts

**Files:**
- Modify: `tests/docs.test.mjs`
- Create: `doc/PRODUCT_UI.md`
- Create: `doc/BACKEND.md`
- Delete: `doc/PAGE_MAIN.md`
- Delete: `doc/PAGE_SEARCH.md`
- Delete: `doc/PAGE_SNAPSHOT.md`
- Delete: `doc/PAGE_ADMIN.md`
- Delete: `doc/API_DESIGN.md`
- Delete: `doc/DATABASE_DESIGN.md`
- Delete: `doc/MARKDOWN_SPEC.md`

**Interfaces:**
- Consumes: mainline and scope from `doc/DEVELOPMENT.md`; current UI/state behavior in `doc/prototype.html`; reusable authentication, audit, transaction, pagination, and accessibility rules from the deleted documents.
- Produces: `doc/PRODUCT_UI.md` as the only current UI contract; `doc/BACKEND.md` as the only current API/persistence contract.

- [ ] **Step 1: Add failing consolidation tests**

Append to `tests/docs.test.mjs`:

```js
const retiredCurrentDocs = [
  'PAGE_MAIN.md',
  'PAGE_SEARCH.md',
  'PAGE_SNAPSHOT.md',
  'PAGE_ADMIN.md',
  'API_DESIGN.md',
  'DATABASE_DESIGN.md',
  'MARKDOWN_SPEC.md'
];

test('product UI has one public and administrator interaction contract', () => {
  const markdown = readCurrentDoc('PRODUCT_UI.md');
  for (const phrase of ['公司目录', 'HTML 阅读', '移动端', '抽屉', '登录', '上传', '审核', '发布', '撤回', 'sandbox']) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.doesNotMatch(markdown, /MarkdownPreview|上传 Markdown|Markdown 正文/);
});

test('backend contract indexes HTML without storing its body', () => {
  const markdown = readCurrentDoc('BACKEND.md');
  for (const phrase of ['FastAPI', 'PostgreSQL', 'SHA-256', '草稿', '已发布', '已撤回', '审计', 'OpenAPI']) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.match(markdown, /不保存 HTML 正文/);
  assert.match(markdown, /MD 不进入后端/);
  assert.doesNotMatch(markdown, /上传 Markdown|scan-inbox|解析 Markdown/);
});

test('superseded current documents are removed', () => {
  for (const name of retiredCurrentDocs) {
    assert.equal(existsSync(currentDocUrl(name)), false, `retired document remains: doc/${name}`);
  }
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
node --test tests/docs.test.mjs
```

Expected: FAIL because `PRODUCT_UI.md` and `BACKEND.md` do not exist and retired documents remain.

- [ ] **Step 3: Create `doc/PRODUCT_UI.md`**

Write one interaction contract with these exact top-level sections:

```markdown
# 产品与界面设计

## 当前原型边界
## 公开工作区
## 公司目录、搜索与排序
## HTML 阅读区
## 独立快照地址
## 移动端公司抽屉
## 管理端登录与框架
## HTML 上传或目录扫描
## 审核、预览与发布
## 状态与错误处理
## 安全边界
## 可访问性
## 生产迁移原则
```

The body must preserve these concrete rules:

- desktop uses a company directory on the left and the selected HTML on the right;
- mobile uses a focus-trapped dismissible company drawer and restores focus on close;
- public filtering supports company name, ticker, market, name order, and date order;
- only published records are public; withdrawing the selected record chooses the next published item or renders an empty state;
- public, standalone, and administrator preview resolve the same HTML path through one renderer;
- iframe has an empty `sandbox` with no allowances;
- administrator imports/scans `.html`, never `.md`;
- validation errors prevent iframe preview and publication when the file is unsafe or unavailable;
- HEAD and iframe load are both required over HTTP; `file://` prototype fallback relies on iframe load;
- invalid HTML, empty results, network failure, 404, retry, toast, dialog, and focus behavior are explicit;
- clearly label prototype behavior as implemented and production routes as target design.

- [ ] **Step 4: Create `doc/BACKEND.md`**

Write one backend contract with these exact top-level sections:

```markdown
# 后端设计

## 职责与边界
## 内容模型
## HTML 校验
## 状态机
## 文件存储
## PostgreSQL 索引
## 认证与会话
## 公开 API
## 管理 API
## 发布与撤回事务
## 审计日志
## 错误、幂等与并发
## OpenAPI 与测试
```

Define this target record shape explicitly:

```json
{
  "id": "uuid",
  "company_name": "贵州茅台",
  "ticker": "600519",
  "market": "CN",
  "data_as_of": "2025-12-31",
  "title": "价值线企业快照版 — 贵州茅台 (600519.SH)",
  "html_path": "published/CN/600519/2025-12-31.html",
  "content_sha256": "64 lowercase hex characters",
  "status": "draft | published | withdrawn",
  "published_at": null
}
```

The document must state:

- FastAPI alone mutates production content and publication state;
- PostgreSQL stores metadata, paths, SHA-256, status, sessions, and audit records, but does not save HTML body text;
- MD does not enter backend upload, parsing, preview, API, or persistence flows;
- validation covers complete document structure, title/company/ticker metadata, remote-resource prohibition, script/iframe/form/navigation restrictions, allowed size, MIME type, and file accessibility;
- public API returns metadata plus a stable HTML URL, never an arbitrary filesystem path;
- administrator API supports `.html` import, scan, detail, validation retry, publish, withdraw, and deletion of eligible drafts;
- publish/withdraw updates index and filesystem state transactionally and writes an audit entry;
- use `/api/v1`, ISO 8601 times, `snake_case`, cursor pagination, structured errors, idempotency keys, optimistic version checks, and generated TypeScript clients from OpenAPI.

- [ ] **Step 5: Delete the superseded documents**

Delete exactly:

```text
doc/PAGE_MAIN.md
doc/PAGE_SEARCH.md
doc/PAGE_SNAPSHOT.md
doc/PAGE_ADMIN.md
doc/API_DESIGN.md
doc/DATABASE_DESIGN.md
doc/MARKDOWN_SPEC.md
```

Do not create an archive directory. Before deletion, compare the new documents against the old authentication, audit, transaction, error-state, accessibility, and responsive sections; carry over only rules compatible with the approved HTML mainline.

- [ ] **Step 6: Run focused and regression tests**

Run:

```bash
node --test tests/docs.test.mjs
node --test tests/prototype.test.mjs
git diff --check
```

Expected: documentation tests PASS; prototype tests remain 26/26 PASS; `git diff --check` exits 0.

- [ ] **Step 7: Commit Task 2**

```bash
git add tests/docs.test.mjs doc/PRODUCT_UI.md doc/BACKEND.md doc/PAGE_MAIN.md doc/PAGE_SEARCH.md doc/PAGE_SNAPSHOT.md doc/PAGE_ADMIN.md doc/API_DESIGN.md doc/DATABASE_DESIGN.md doc/MARKDOWN_SPEC.md
git commit -m "docs: consolidate product and backend contracts"
```

---

### Task 3: Rewrite deployment and SEO for HTML publication

**Files:**
- Modify: `tests/docs.test.mjs`
- Create: `doc/DEPLOYMENT.md`
- Delete: `doc/DOCKER.md`
- Modify: `doc/SEO.md`

**Interfaces:**
- Consumes: target architecture in `doc/DEVELOPMENT.md`; content and API boundaries in `doc/BACKEND.md`; reusable Aliyun, Nginx, HTTPS, backup, and rollback rules from `doc/DOCKER.md`.
- Produces: one operational document and one indexing document that do not claim the iframe shell contains indexable snapshot text.

- [ ] **Step 1: Add failing deployment and SEO contract tests**

Append to `tests/docs.test.mjs`:

```js
test('deployment targets Aliyun with persistent HTML content', () => {
  const markdown = readCurrentDoc('DEPLOYMENT.md');
  for (const phrase of ['Docker Compose', 'Nginx', '阿里云', 'www.ayaseeri.com', 'HTTPS', 'HTML 内容卷', '备份', '回滚']) {
    assert.match(markdown, new RegExp(phrase));
  }
  assert.doesNotMatch(markdown, /Markdown 正文|恢复.*Markdown|content\/inbox/);
  assert.equal(existsSync(currentDocUrl('DOCKER.md')), false, 'retired doc/DOCKER.md remains');
});

test('SEO indexes standalone published HTML instead of iframe contents', () => {
  const markdown = readCurrentDoc('SEO.md');
  assert.match(markdown, /iframe 外壳.+不能.+索引正文/s);
  assert.match(markdown, /独立 HTML 发布地址/);
  assert.match(markdown, /canonical/);
  assert.match(markdown, /noindex/);
  assert.doesNotMatch(markdown, /完整 Markdown 正文|Markdown 标记/);
});
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
node --test tests/docs.test.mjs
```

Expected: FAIL because `DEPLOYMENT.md` is absent, `DOCKER.md` remains, and `SEO.md` describes SSR Markdown output.

- [ ] **Step 3: Create `doc/DEPLOYMENT.md` and remove `doc/DOCKER.md`**

Create the new file with these exact top-level sections:

```markdown
# 部署设计

## 当前状态与目标
## 服务组成
## Docker Compose
## 本地开发
## 环境变量与密钥
## 网络与安全组
## HTML 内容卷
## Nginx 路由与缓存
## 阿里云 ECS
## www.ayaseeri.com 与 HTTPS
## 首次部署
## 日常发布与回滚
## 备份与恢复
## 健康检查、日志与告警
```

Preserve the useful single-ECS target and these rules:

- Nginx is the only public container; Nuxt, admin, FastAPI, and PostgreSQL stay on internal networks;
- production content uses a persistent HTML volume separate from `doc/snapshots/` samples;
- back up PostgreSQL metadata and the HTML content volume at the same logical point;
- HTML responses use deliberate cache headers, while administrator and API responses are not publicly cached;
- certificates are mounted read-only, secrets are not committed, and Docker socket is never mounted;
- deploy, smoke-test, rollback, backup, restore, log rotation, and health-check commands are concrete but remain target design until runtime files exist;
- remove all `content/inbox`, Markdown restore, and Markdown-body logging language.

Delete `doc/DOCKER.md` after extracting the compatible material.

- [ ] **Step 4: Rewrite `doc/SEO.md`**

Use these exact top-level sections:

```markdown
# SEO 设计

## 当前原型限制
## 可索引页面
## 独立 HTML 发布地址
## 工作区与 canonical
## 元数据
## Open Graph 与结构化数据
## Sitemap 与 robots
## 管理端、草稿与撤回
## 性能与发布检查
```

State clearly:

- the current iframe shell can describe the product but cannot make embedded snapshot text reliably indexable;
- production gives every published snapshot a stable standalone HTML URL;
- latest and historical routes must have explicit canonical rules;
- withdrawn, draft, invalid, administrator, and API pages are `noindex` or blocked as appropriate;
- metadata comes from validated HTML/index metadata, not Markdown parsing;
- sitemap contains published standalone HTML only and removes withdrawn records;
- no cloaking or User-Agent-specific content.

- [ ] **Step 5: Run focused and regression tests**

Run:

```bash
node --test tests/docs.test.mjs
node --test tests/prototype.test.mjs
git diff --check
```

Expected: documentation tests PASS; prototype tests remain 26/26 PASS; `git diff --check` exits 0.

- [ ] **Step 6: Commit Task 3**

```bash
git add tests/docs.test.mjs doc/DEPLOYMENT.md doc/DOCKER.md doc/SEO.md
git commit -m "docs: align deployment and SEO with HTML publishing"
```

---

### Task 4: Move snapshot assets, update the prototype, and enforce final integrity

**Files:**
- Modify: `tests/docs.test.mjs`
- Modify: `tests/prototype.test.mjs`
- Modify: `doc/prototype.html`
- Move: `doc/价值线_贵州茅台_企业快照版.html` → `doc/snapshots/published/贵州茅台.html`
- Move: `doc/价值线_哔哩哔哩_企业快照版.html` → `doc/snapshots/published/哔哩哔哩.html`
- Move: `doc/价值线_贵州茅台_企业快照版.md` → `doc/snapshots/sources/贵州茅台.md`
- Move: `doc/价值线_哔哩哔哩_企业快照版.md` → `doc/snapshots/sources/哔哩哔哩.md`

**Interfaces:**
- Consumes: existing `html-snapshot-manifest`, `readSnapshotAsset()`, local HTTP test server, asset safety rules, and runtime Chrome workflow in `tests/prototype.test.mjs`.
- Produces: manifest `htmlPath` values `./snapshots/published/贵州茅台.html` and `./snapshots/published/哔哩哔哩.html`; basename-only `fileName` values; checked-in published/source asset pairs; final cross-document integrity tests.

- [ ] **Step 1: Record out-of-scope root duplicate hashes**

Run before any move:

```bash
shasum -a 256 '价值线_哔哩哔哩_企业快照版.html' '价值线_哔哩哔哩_企业快照版.md'
```

Expected hashes:

```text
7c0fc7c80c43eb29e5f942f2bec9f0b2439382c77f9f15b9a187ed255f8d0813  价值线_哔哩哔哩_企业快照版.html
1aadce7242618a16aed61e71f894f14a4f564654e38f67b5e6c58e88130ebca6  价值线_哔哩哔哩_企业快照版.md
```

If either hash differs before work starts, record the new baseline and do not edit the files. The only required invariant is identical before/after hashes.

- [ ] **Step 2: Change prototype tests first and verify RED**

Update `tests/prototype.test.mjs` so asset resolution uses `htmlPath`, while UI metadata keeps a basename:

```js
function readSnapshotAsset(htmlPath) {
  const url = new URL(htmlPath, docDirectory);
  assert.equal(existsSync(url), true, `missing ${htmlPath}`);
  return readFileSync(url, 'utf8');
}
```

In `startPrototypeServer()`, replace the path map and successful body read with:

```js
const byPath = new Map(manifest.map((snapshot) => [
  new URL(snapshot.htmlPath, 'http://localhost/doc/prototype.html').pathname,
  snapshot
]));

// Inside send():
response.end(status === 200 && request.method !== 'HEAD' ? readSnapshotAsset(snapshot.htmlPath) : '');
```

Change manifest assertions to:

```js
assert.equal(manifest[0].htmlPath, './snapshots/published/贵州茅台.html');
assert.equal(manifest[0].fileName, '贵州茅台.html');
assert.equal(manifest[1].htmlPath, './snapshots/published/哔哩哔哩.html');
assert.equal(manifest[1].fileName, '哔哩哔哩.html');
```

In the safe-document loop, read `snapshot.htmlPath`:

```js
const html = readSnapshotAsset(snapshot.htmlPath);
```

Run:

```bash
node --test tests/prototype.test.mjs
```

Expected: FAIL because the manifest and files still use the old paths.

- [ ] **Step 3: Add failing final documentation integrity tests**

Extend the imports in `tests/docs.test.mjs`:

```js
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
```

Append:

```js
const currentMarkdownDocs = [
  'README.md',
  'DEVELOPMENT.md',
  'PRODUCT_UI.md',
  'BACKEND.md',
  'DEPLOYMENT.md',
  'SEO.md'
];

test('published HTML and audit-only Markdown source pairs exist', () => {
  for (const path of [
    'snapshots/published/贵州茅台.html',
    'snapshots/published/哔哩哔哩.html',
    'snapshots/sources/贵州茅台.md',
    'snapshots/sources/哔哩哔哩.md'
  ]) assert.equal(existsSync(currentDocUrl(path)), true, `missing doc/${path}`);
});

test('current documents do not restore the retired Markdown runtime', () => {
  const combined = currentMarkdownDocs.map(readCurrentDoc).join('\n');
  assert.doesNotMatch(combined, /上传 Markdown|扫描 `?content\/inbox|Markdown 是.+唯一事实来源|网站.+解析 Markdown/s);
  assert.match(combined, /HTML 是网站唯一发布物/);
});

test('relative Markdown links in current documents resolve', () => {
  for (const name of currentMarkdownDocs) {
    const source = readCurrentDoc(name);
    const sourcePath = fileURLToPath(currentDocUrl(name));
    for (const match of source.matchAll(/\[[^\]]+\]\((?!https?:|#)([^)#]+)(?:#[^)]+)?\)/g)) {
      const target = decodeURIComponent(match[1]);
      assert.equal(existsSync(resolve(dirname(sourcePath), target)), true, `broken link in doc/${name}: ${target}`);
    }
  }
});

test('doc root contains only current entry documents and the prototype', () => {
  const rootFiles = readdirSync(docDirectory, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();
  assert.deepEqual(rootFiles, [
    'BACKEND.md',
    'DEPLOYMENT.md',
    'DEVELOPMENT.md',
    'PRODUCT_UI.md',
    'README.md',
    'SEO.md',
    'prototype.html'
  ]);
});
```

Run:

```bash
node --test tests/docs.test.mjs
```

Expected: FAIL because snapshot assets have not moved and old files remain in the `doc/` root until the move is complete.

- [ ] **Step 4: Move the four snapshot files**

Verify the four exact sources exist, then create destination directories and move without changing contents:

```bash
mkdir -p doc/snapshots/published doc/snapshots/sources
mv 'doc/价值线_贵州茅台_企业快照版.html' 'doc/snapshots/published/贵州茅台.html'
mv 'doc/价值线_哔哩哔哩_企业快照版.html' 'doc/snapshots/published/哔哩哔哩.html'
mv 'doc/价值线_贵州茅台_企业快照版.md' 'doc/snapshots/sources/贵州茅台.md'
mv 'doc/价值线_哔哩哔哩_企业快照版.md' 'doc/snapshots/sources/哔哩哔哩.md'
```

Do not touch the same-named Bilibili files in the repository root.

- [ ] **Step 5: Update the embedded prototype manifest**

In `doc/prototype.html`, keep the IDs, company metadata, title tickers, dates, statuses, and page titles unchanged. Change only these fields:

```json
{
  "id": "cn-600519-html",
  "htmlPath": "./snapshots/published/贵州茅台.html",
  "fileName": "贵州茅台.html"
}
```

```json
{
  "id": "hk-09626-html",
  "htmlPath": "./snapshots/published/哔哩哔哩.html",
  "fileName": "哔哩哔哩.html"
}
```

Do not change the invalid draft fixture filename because it intentionally has no manifest asset.

- [ ] **Step 6: Run all automated verification**

Run:

```bash
node --test tests/docs.test.mjs
node --test tests/prototype.test.mjs
git diff --check
```

Expected:

- all documentation tests PASS;
- all prototype tests PASS, including the three real Chrome runtime state-transition subtests;
- `git diff --check` exits 0.

- [ ] **Step 7: Verify browser behavior and file boundaries**

Serve the repository root locally and open `http://127.0.0.1:4173/doc/prototype.html`. Verify:

1. 贵州茅台 loads from `/doc/snapshots/published/贵州茅台.html`.
2. 哔哩哔哩 loads from `/doc/snapshots/published/哔哩哔哩.html`.
3. Public and administrator previews still use sandboxed iframes.
4. Withdrawing the selected company removes its old iframe and selects the remaining published company.
5. Re-publishing restores the company.
6. Mobile company drawer opens, closes, traps focus, and restores focus.
7. Runtime JavaScript console errors remain zero.

Re-run the root duplicate hashes:

```bash
shasum -a 256 '价值线_哔哩哔哩_企业快照版.html' '价值线_哔哩哔哩_企业快照版.md'
```

Expected: hashes are identical to Step 1.

Run:

```bash
git status --short
git diff --name-status
```

Expected: no root duplicate or `skills/` path appears in tracked changes. The four moved snapshot assets are ready to become tracked in their destination directories.

- [ ] **Step 8: Commit Task 4**

Stage only current documents, prototype, tests, and the four snapshot destination files:

```bash
git add doc tests/docs.test.mjs tests/prototype.test.mjs
git commit -m "docs: organize prototype snapshots and current guides"
```

After committing, confirm `git status --short` contains only the out-of-scope root duplicates and `skills/` if they were already untracked.

---

## Final Whole-Branch Review

Generate a review package from design commit `26a273a` to final `HEAD`. A fresh reviewer must verify:

- current-doc structure matches the approved design;
- useful authentication, audit, transaction, accessibility, deployment, backup, and SEO rules survived consolidation;
- no current document describes Markdown as a website runtime format;
- `prototype.html` retains its original path and uses the moved HTML assets;
- MD sources are tracked but unused by runtime code;
- root duplicate files and `skills/` were not modified or committed;
- documentation link tests and Chrome runtime tests genuinely execute the required behavior;
- no historical specs/plans were rewritten.

If the reviewer reports Critical or Important issues, dispatch one fresh fix agent with the complete finding list, verify, commit, and re-review before final delivery.
