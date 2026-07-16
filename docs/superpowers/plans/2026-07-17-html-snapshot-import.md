# Direct HTML Snapshot Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Skill-generated HTML files the only financial-report body used by the public company workspace and administrator review preview.

**Architecture:** Add an embedded metadata-only HTML snapshot manifest, then load its registered relative paths through a shared sandboxed iframe renderer. Migrate the public workspace first, then the administrator workflow, and finally delete the old embedded Moutai financial JSON, simple company content, value-line renderers, and their unused CSS.

**Tech Stack:** Standalone HTML, CSS, vanilla JavaScript, sandboxed iframe, embedded JSON manifest, Node.js built-in test runner.

## Global Constraints

- Public and administrator previews load the same HTML file path.
- The public directory contains only 贵州茅台 and 哔哩哔哩.
- 贵州茅台 is selected by default.
- The iframe uses an empty `sandbox` attribute; do not add any sandbox allowances.
- Financial metrics, tables, verdicts, and prose remain exclusively inside the generated HTML files.
- The outer prototype must not parse or inject HTML source strings.
- The outer prototype must remain free of remote scripts, stylesheets, fonts, and images.
- Keep desktop `320px + remaining width`, the mobile drawer, search, market filter, sorting, empty state, and request-failure demonstration.
- Migrate the administrator copy and workflow from Markdown to HTML.
- A failed HTML record remains administrator-only, has exactly two validation errors, creates no iframe, and cannot be published.
- Do not modify or commit the generated HTML/Markdown inputs or `skills/`.

## File Map

- Modify `doc/prototype.html`: metadata manifest, shared iframe renderer, public directory/detail, administrator records, validation copy, review preview, and old-renderer cleanup.
- Modify `tests/prototype.test.mjs`: manifest parsing, generated-file validation, iframe contracts, administrator HTML contracts, old-content removal, and regressions.
- Read only `doc/价值线_贵州茅台_企业快照版.html` and `doc/价值线_哔哩哔哩_企业快照版.html`.

---

### Task 1: Register and validate generated HTML snapshots

**Files:**
- Modify: `doc/prototype.html` immediately before the executable `<script>`
- Modify: `doc/prototype.html` at the executable script bootstrap
- Test: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: the two generated HTML files in `doc/` and the existing `readEmbeddedSnapshot()` JSON parsing pattern.
- Produces: embedded JSON `html-snapshot-manifest`, `readEmbeddedJson(id)`, and `htmlSnapshots: Array<HtmlSnapshot>`.

- [ ] **Step 1: Write failing manifest and file-safety tests**

Change the existing filesystem import and add this helper near the top of `tests/prototype.test.mjs`:

```js
import { existsSync, readFileSync } from 'node:fs';

const docDirectory = new URL('../doc/', import.meta.url);

function readSnapshotAsset(fileName) {
  const url = new URL(fileName, docDirectory);
  assert.equal(existsSync(url), true, `missing ${fileName}`);
  return readFileSync(url, 'utf8');
}
```

Append:

```js
test('HTML snapshot manifest registers only generated public reports', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  assert.deepEqual(manifest.map((item) => item.id), ['cn-600519-html', 'hk-09626-html']);
  assert.deepEqual(manifest.map((item) => item.companyName), ['贵州茅台', '哔哩哔哩']);
  assert.deepEqual(manifest.map((item) => item.status), ['published', 'published']);
  assert.equal(manifest[0].htmlPath, './价值线_贵州茅台_企业快照版.html');
  assert.equal(manifest[1].htmlPath, './价值线_哔哩哔哩_企业快照版.html');
});

test('generated HTML snapshots are self-contained safe documents', () => {
  const manifest = embeddedJson(readPrototype(), 'html-snapshot-manifest');
  for (const snapshot of manifest) {
    const html = readSnapshotAsset(snapshot.fileName);
    assert.match(html, /^<!doctype html>/i, `${snapshot.fileName} missing doctype`);
    assert.match(html, /<html[^>]+lang=["']zh-CN["']/i, `${snapshot.fileName} missing lang`);
    assert.match(html, /<meta[^>]+charset=["']?utf-8/i, `${snapshot.fileName} missing charset`);
    assert.match(html, /<meta[^>]+name=["']viewport["']/i, `${snapshot.fileName} missing viewport`);
    assert.match(html, /<title>[^<]+<\/title>/i, `${snapshot.fileName} missing title`);
    assert.match(html, /<style>[\s\S]+<\/style>/i, `${snapshot.fileName} missing style`);
    assert.match(html, /<body>[\s\S]+<\/body>/i, `${snapshot.fileName} missing body`);
    assert.ok(html.includes(snapshot.companyName), `${snapshot.fileName} missing company`);
    assert.ok(html.includes(snapshot.titleTicker), `${snapshot.fileName} missing title ticker`);
    assert.doesNotMatch(html, /<script\b/i, `${snapshot.fileName} contains script`);
    assert.doesNotMatch(html, /<iframe\b/i, `${snapshot.fileName} contains iframe`);
    assert.doesNotMatch(html, /(?:src|href)=["']https?:\/\//i, `${snapshot.fileName} contains remote asset`);
    assert.doesNotMatch(html, /@import\s+(?:url\()?\s*["']?https?:\/\//i, `${snapshot.fileName} contains remote import`);
  }
});
```

- [ ] **Step 2: Run the targeted tests and verify RED**

```bash
node --test --test-name-pattern="HTML snapshot manifest|generated HTML snapshots" tests/prototype.test.mjs
```

Expected: both tests fail because `html-snapshot-manifest` does not exist.

- [ ] **Step 3: Add the metadata-only manifest**

Insert after `<div id="app"></div>` and before the current Moutai JSON:

```html
<script type="application/json" id="html-snapshot-manifest">
[
  {
    "id": "cn-600519-html",
    "companyName": "贵州茅台",
    "ticker": "600519",
    "titleTicker": "600519.SH",
    "market": "CN",
    "exchange": "SSE",
    "dataAsOf": "2025-12-31",
    "quoteAsOf": "2026-07-15 12:05",
    "publishedAt": "2026-07-16",
    "updatedAt": "2026-07-16",
    "htmlPath": "./价值线_贵州茅台_企业快照版.html",
    "fileName": "价值线_贵州茅台_企业快照版.html",
    "pageTitle": "价值线企业快照版 — 贵州茅台 (600519.SH) · 只寻找事实，不寻求意见",
    "status": "published",
    "report": "clean",
    "isLatest": true
  },
  {
    "id": "hk-09626-html",
    "companyName": "哔哩哔哩",
    "ticker": "09626",
    "titleTicker": "09626.HK",
    "market": "HK",
    "exchange": "HKEX",
    "dataAsOf": "2025-12-31",
    "quoteAsOf": "2026-07-16 16:08:38",
    "publishedAt": "2026-07-17",
    "updatedAt": "2026-07-17",
    "htmlPath": "./价值线_哔哩哔哩_企业快照版.html",
    "fileName": "价值线_哔哩哔哩_企业快照版.html",
    "pageTitle": "价值线企业快照版 — 哔哩哔哩 (09626.HK) · 只寻找事实，不寻求意见",
    "status": "published",
    "report": "clean",
    "isLatest": true
  }
]
</script>
```

Rename the JSON reader and initialize the new collection without changing current public behavior yet:

```js
function readEmbeddedJson(id) {
  return JSON.parse(document.querySelector(`#${id}`).textContent);
}

const htmlSnapshots = readEmbeddedJson('html-snapshot-manifest');
const maotaiSnapshot = readEmbeddedJson('maotai-snapshot-data');
```

- [ ] **Step 4: Run targeted and full tests**

```bash
node --test --test-name-pattern="HTML snapshot manifest|generated HTML snapshots" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git diff --check
```

Expected: the new tests pass, existing tests remain green, and the whitespace check prints nothing.

- [ ] **Step 5: Commit the manifest**

```bash
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: register generated HTML snapshots"
```

---

### Task 2: Render public reports through a shared iframe

**Files:**
- Modify: `doc/prototype.html` public state, filters, directory cards, workspace detail, snapshot route, iframe events, and workspace CSS
- Test: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: `htmlSnapshots`, `escapeHtml()`, public selection/filter state, desktop workspace, and mobile drawer.
- Produces: `renderSnapshotFrame(snapshot, mode): string`, `renderWorkspaceDetail(snapshot): string`, `renderHtmlSnapshotPage(snapshot): string`, and `armSnapshotFrameTimeouts(): void`.

- [ ] **Step 1: Replace old public-content tests with failing iframe contracts**

Delete these obsolete tests:

```text
Moutai payload preserves the Skill facts and aligned history
Moutai detail exposes every value-line research module
value-line tables preserve readable mobile behavior
value-line grid children cannot widen the mobile stage
workspace detail responds to its own readable width
```

Remove the now-unused test helpers `assertAlignedTable()` after deleting those tests. Update `prototype contains the complete public research flow` so its required tokens are:

```js
for (const required of [
  'data-route="home"',
  'data-route="snapshot"',
  'data-action="search"',
  'data-action="market"',
  'data-action="sort"',
  'data-action="select-company"',
  'renderSnapshotFrame',
  '企业财报 HTML'
]) assert.ok(html.includes(required), `missing ${required}`);
```

Update the selection test to expect `selectedSnapshotId: 'cn-600519-html'`. Append:

```js
test('public workspace loads registered HTML through a sandboxed iframe', () => {
  const html = readPrototype();
  for (const required of [
    'function renderSnapshotFrame(snapshot, mode)',
    "class='snapshot-html-frame'",
    "src='${escapeHtml(snapshot.htmlPath)}'",
    "title='${escapeHtml(snapshot.companyName)}企业财报快照'",
    'sandbox',
    'data-frame-load',
    '正在加载 HTML 快照',
    'HTML 快照未能加载，请检查文件路径'
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /\.snapshot-html-frame \{[^}]*width: 100%;[^}]*height: 100%;/s);
  assert.match(html, /\.snapshot-frame-shell \{[^}]*flex: 1;/s);
  assert.doesNotMatch(html, /sandbox=["'][^"']+/, 'iframe sandbox must have no allowances');
});

test('public company cards contain identity metadata but no copied financial metrics', () => {
  const html = readPrototype();
  assert.match(html, /HTML 快照/);
  assert.match(html, /已发布/);
  assert.doesNotMatch(html, /function metricItems\(/);
  assert.doesNotMatch(html, /class='mini-metrics'/);
  assert.doesNotMatch(html, /class='verdict(?:\s|')/);
});
```

- [ ] **Step 2: Run public iframe tests and verify RED**

```bash
node --test --test-name-pattern="public workspace loads registered HTML|public company cards" tests/prototype.test.mjs
```

Expected: failures because the workspace still renders copied financial content.

- [ ] **Step 3: Switch selection and filtering to the HTML manifest**

Change initial state:

```js
selectedSnapshotId: 'cn-600519-html',
```

Change `filteredSnapshots()` to start from published HTML records:

```js
const records = htmlSnapshots.filter((snapshot) => snapshot.isLatest && snapshot.status === 'published');
```

Change `selectedPublicSnapshot()`:

```js
function selectedPublicSnapshot() {
  if (state.publicScenario !== 'normal') return null;
  return htmlSnapshots.find((snapshot) => snapshot.id === state.selectedSnapshotId && snapshot.status === 'published') || null;
}
```

Keep the existing query normalization, sorting, automatic selection, market filter, empty state, drawer state, and focus restoration.

- [ ] **Step 4: Simplify public company cards**

Delete `metricItems()`. Replace `renderCompanyCard()` with:

```js
function renderCompanyCard(snapshot, selected) {
  return `
    <button class='directory-card ${selected ? 'is-selected' : ''}' type='button' data-action="select-company" data-id='${snapshot.id}' aria-current='${selected ? 'true' : 'false'}'>
      <div class='card-meta'><span class='market-tag'>${snapshot.market === 'CN' ? 'A 股' : '港股'}</span><time>${snapshot.dataAsOf}</time></div>
      <h2>${escapeHtml(snapshot.companyName)}</h2>
      <span class='ticker'>${escapeHtml(snapshot.ticker)} · ${escapeHtml(snapshot.exchange)}</span>
      <div class='file-kind'><span>HTML 快照</span><span class='status-pill status-pill--published'>已发布</span></div>
      <div class='card-footer'>${selected ? `<span class='directory-card__current'>当前阅读</span>` : `<span class='ticker'>点击阅读原始页面</span>`}</div>
    </button>`;
}
```

- [ ] **Step 5: Add the shared iframe renderer and public wrappers**

Add:

```js
function renderSnapshotFrame(snapshot, mode) {
  if (!snapshot?.htmlPath) return renderInvalidHtmlPreview();
  return `
    <div class='snapshot-frame-shell snapshot-frame-shell--${mode}'>
      <div class='snapshot-frame-loading' data-frame-loading>正在加载 HTML 快照</div>
      <iframe class='snapshot-html-frame' src='${escapeHtml(snapshot.htmlPath)}' title='${escapeHtml(snapshot.companyName)}企业财报快照' sandbox data-frame-load></iframe>
    </div>`;
}

function renderWorkspaceDetail(snapshot) {
  if (!snapshot) return `<section class='workspace-detail workspace-empty'><div class='empty-state'><span class='empty-state__mark'>0</span><h3>没有可阅读的企业财报 HTML</h3><p>请调整公司名称或市场条件。</p><button class='button' type='button' data-action='clear-search'>清除筛选</button></div></section>`;
  return `
    <section class='workspace-detail'>
      <div class='workspace-context'><button class='button company-drawer-button' type='button' data-action="open-company-drawer" aria-haspopup='dialog'>选择公司</button><div class='workspace-context__identity'><strong>${escapeHtml(snapshot.companyName)}</strong><span>${escapeHtml(snapshot.ticker)} · ${snapshot.market === 'CN' ? 'A 股' : '港股'}</span></div><span class='workspace-context__category'>企业财报 HTML</span></div>
      ${renderSnapshotFrame(snapshot, 'public')}
    </section>`;
}

function renderHtmlSnapshotPage(snapshot) {
  return `<div class='site-shell html-snapshot-page' data-route="snapshot">${renderSiteHeader()}<main class='html-snapshot-main'><button class='back-link' type='button' data-action='back-results'>← 返回公司目录</button>${renderSnapshotFrame(snapshot, 'standalone')}</main></div>`;
}

function renderSnapshot() {
  return renderHtmlSnapshotPage(selectedPublicSnapshot() || htmlSnapshots[0]);
}
```

Add a capture-phase load listener without re-rendering the iframe:

```js
app.addEventListener('load', (event) => {
  if (!event.target.matches('[data-frame-load]')) return;
  event.target.closest('.snapshot-frame-shell')?.querySelector('[data-frame-loading]')?.classList.add('is-hidden');
}, true);
```

Add the missing-file timeout helper:

```js
function armSnapshotFrameTimeouts() {
  app.querySelectorAll('[data-frame-load]').forEach((frame) => {
    const loading = frame.closest('.snapshot-frame-shell')?.querySelector('[data-frame-loading]');
    window.setTimeout(() => {
      if (!loading?.isConnected || loading.classList.contains('is-hidden')) return;
      loading.textContent = 'HTML 快照未能加载，请检查文件路径';
      loading.classList.add('is-error');
    }, 3500);
  });
}
```

Call `armSnapshotFrameTimeouts()` immediately after assigning `app.innerHTML` in `render()`.

- [ ] **Step 6: Add iframe and simplified card CSS**

Add:

```css
.file-kind { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 16px; padding-top: 13px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
.workspace-detail { display: flex; flex-direction: column; }
.snapshot-frame-shell { position: relative; flex: 1; min-width: 0; min-height: 0; background: #fff; }
.snapshot-frame-shell--review { min-height: 720px; border: 1px solid var(--line); border-radius: var(--radius-card); overflow: hidden; }
.snapshot-frame-shell--standalone { min-height: calc(100dvh - 150px); }
.snapshot-html-frame { display: block; width: 100%; height: 100%; min-height: 0; background: #f7f5f1; border: 0; }
.snapshot-frame-loading { position: absolute; inset: 0; z-index: 1; display: grid; place-items: center; color: var(--muted); background: #f7f5f1; font-size: 13px; }
.snapshot-frame-loading.is-hidden { display: none; }
.snapshot-frame-loading.is-error { color: var(--negative); background: var(--negative-soft); }
.html-snapshot-main { display: flex; min-height: calc(100dvh - 116px); flex-direction: column; padding: 18px 24px 24px; }
```

Remove `.workspace-detail__scroll` from the public iframe markup. Keep its CSS until Task 4, when unused rules are removed.

- [ ] **Step 7: Run public tests and commit**

```bash
node --test --test-name-pattern="public workspace loads registered HTML|public company cards|public workspace defaults|homepage renders" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git diff --check
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: load public reports from HTML snapshots"
```

Expected: all tests pass and no whitespace errors remain.

---

### Task 3: Migrate administrator import, validation, and preview to HTML

**Files:**
- Modify: `doc/prototype.html` administrator records, reports, copy, list, upload panel, metadata, preview, audit, and actions
- Test: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: `htmlSnapshots`, `renderSnapshotFrame(snapshot, mode)`, administrator state/actions, and dialog workflow.
- Produces: three HTML administrator records, HTML validation reports, `renderInvalidHtmlPreview()`, and a shared iframe review preview.

- [ ] **Step 1: Write failing administrator HTML tests**

Replace `Moutai is clean and published while the invalid demo stays admin-only` with:

```js
test('administrator manages two valid HTML snapshots and one invalid draft', () => {
  const html = readPrototype();
  assert.match(html, /id: 'published-maotai-html'[\s\S]*snapshotId: 'cn-600519-html'[\s\S]*status: 'published'[\s\S]*report: 'clean'/);
  assert.match(html, /id: 'published-bilibili-html'[\s\S]*snapshotId: 'hk-09626-html'[\s\S]*status: 'published'[\s\S]*report: 'clean'/);
  assert.match(html, /id: 'demo-invalid-html'[\s\S]*snapshotId: null[\s\S]*status: 'draft'[\s\S]*report: 'html-error'/);
  assert.doesNotMatch(html, /draft-tencent|published-meituan|id: 'demo-invalid'/);
});

test('administrator copy and preview use the HTML artifact', () => {
  const html = readPrototype();
  for (const required of ['上传 HTML', '使用演示 HTML', 'HTML 文件', '页面标题', 'text/html', '完成 HTML 校验', "renderSnapshotFrame(snapshot, 'review')", 'HTML 校验失败，无法生成预览']) assert.ok(html.includes(required), `missing ${required}`);
  assert.doesNotMatch(html, /上传 Markdown|使用演示 Markdown|完成 Markdown 校验/);
});

test('invalid HTML is blocked with two explicit errors and no iframe', () => {
  const html = readPrototype();
  assert.match(html, /'html-error': \{[\s\S]*errors: \[[\s\S]*HTML 缺少非空 &lt;title&gt;[\s\S]*HTML 包含远程 &lt;script&gt;[\s\S]*warnings: \[\]/);
  assert.match(html, /data-action="publish" \$\{hasErrors \? 'disabled' : ''\}/);
  assert.match(html, /if \(!record\.snapshotId\) return renderInvalidHtmlPreview\(\)/);
});
```

- [ ] **Step 2: Run administrator tests and verify RED**

```bash
node --test --test-name-pattern="administrator manages|administrator copy|invalid HTML" tests/prototype.test.mjs
```

Expected: failures because the administrator still manages Markdown records.

- [ ] **Step 3: Replace administrator records and validation reports**

Use:

```js
let adminRecords = [
  { id: 'published-maotai-html', snapshotId: 'cn-600519-html', companyName: '贵州茅台', ticker: '600519', market: 'CN', dataAsOf: '2025-12-31', quoteAsOf: '2026-07-15 12:05', status: 'published', report: 'clean', updatedAt: '2026-07-16' },
  { id: 'published-bilibili-html', snapshotId: 'hk-09626-html', companyName: '哔哩哔哩', ticker: '09626', market: 'HK', dataAsOf: '2025-12-31', quoteAsOf: '2026-07-16 16:08:38', status: 'published', report: 'clean', updatedAt: '2026-07-17' },
  { id: 'demo-invalid-html', snapshotId: null, companyName: 'HTML 格式错误示例', ticker: '000000', market: 'CN', dataAsOf: '2025-12-31', quoteAsOf: null, fileName: '价值线_格式错误示例_企业快照版.html', pageTitle: '', status: 'draft', report: 'html-error', updatedAt: '今天 09:15' }
];

const validationReports = {
  clean: { errors: [], warnings: [], info: ['完整 HTML、自包含资源和标题元数据校验通过。'] },
  'html-error': { errors: ['HTML 缺少非空 &lt;title&gt;。', 'HTML 包含远程 &lt;script&gt;，禁止发布。'], warnings: [], info: [] }
};
```

Change `selectedAdminRecord` to `published-maotai-html`.

- [ ] **Step 4: Update upload, login, list, and action copy**

Use these exact user-facing strings:

```text
管理端只处理 HTML 导入、校验、预览和发布。正文需要修改时，回到 Skill 重新生成。
导入 HTML，检查文件，再决定是否发布。
上传 HTML
扫描 inbox 中的企业快照 HTML
使用演示 HTML
原型使用内置的 HTML 格式错误演示文件，不读取你的本地文件。
演示 HTML 已导入为草稿。
扫描完成：发现 2 个 HTML 文件。
```

Change the simulated upload action to select `demo-invalid-html`.

In `renderUploadPanel()`, use the HTML error report:

```js
const report = validationReports['html-error'];
```

Render the three result cells with these expressions so empty collections display `无`:

```js
report.errors.length ? report.errors.join('；') : '无'
report.warnings.length ? report.warnings.join('；') : '无'
report.info.length ? report.info.join('；') : '无'
```

- [ ] **Step 5: Replace review metadata and preview**

Resolve the snapshot from `htmlSnapshots`:

```js
function snapshotForRecord(record) {
  return htmlSnapshots.find((snapshot) => snapshot.id === record.snapshotId) || null;
}
```

Use this metadata renderer body:

```js
function renderReviewCheck(record, report) {
  const snapshot = snapshotForRecord(record);
  const fileName = snapshot?.fileName || record.fileName;
  const pageTitle = snapshot?.pageTitle || record.pageTitle || '无法识别';
  return `<section class='review-panel'><h2>元数据</h2><dl class='metadata-list'><dt>公司</dt><dd>${escapeHtml(record.companyName)}</dd><dt>代码</dt><dd>${escapeHtml(record.ticker)}</dd><dt>市场</dt><dd>${escapeHtml(record.market)}</dd><dt>数据日期</dt><dd>${escapeHtml(record.dataAsOf)}</dd>${record.quoteAsOf ? `<dt>行情时间</dt><dd>${escapeHtml(record.quoteAsOf)}</dd>` : ''}<dt>HTML 文件</dt><dd>${escapeHtml(fileName)}</dd><dt>页面标题</dt><dd>${escapeHtml(pageTitle)}</dd><dt>文件类型</dt><dd>text/html</dd></dl>${renderValidationList('校验错误', report.errors, 'report-error', '没有错误')}${renderValidationList('校验警告', report.warnings, 'report-warning', '没有警告')}${renderValidationList('标准化信息', report.info, 'report-info', '没有标准化信息')}</section>`;
}
```

Replace the preview functions with:

```js
function renderInvalidHtmlPreview() {
  return `<div class='empty-state'><span class='empty-state__mark'>!</span><h3>无法生成 HTML 预览</h3><p>HTML 校验失败，无法生成预览。请补全页面标题并移除远程脚本。</p></div>`;
}

function renderReviewSnapshotContent(record) {
  if (!record.snapshotId) return renderInvalidHtmlPreview();
  const snapshot = snapshotForRecord(record);
  return renderSnapshotFrame(snapshot, 'review');
}
```

Change audit copy to `完成 HTML 校验` and `导入 HTML 草稿`.

- [ ] **Step 6: Run administrator tests and commit**

```bash
node --test --test-name-pattern="administrator manages|administrator copy|invalid HTML" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git diff --check
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: review and publish HTML snapshots"
```

Expected: all tests pass and the administrator contains exactly the three planned records.

---

### Task 4: Remove copied financial content and verify the complete prototype

**Files:**
- Modify: `doc/prototype.html` embedded data, unused JavaScript renderers/actions, and unused CSS
- Modify: `tests/prototype.test.mjs` cleanup and regression contracts

**Interfaces:**
- Consumes: `htmlSnapshots`, public iframe renderer, administrator iframe renderer, and all existing shell interactions.
- Produces: a smaller prototype that contains no duplicate financial body.

- [ ] **Step 1: Write the failing duplicate-content cleanup test**

Append:

```js
test('prototype no longer stores or renders copied financial bodies', () => {
  const html = readPrototype();
  for (const obsolete of [
    'maotai-snapshot-data',
    'renderValueLineBody',
    'renderValueLineSnapshot',
    'renderValueTable',
    'renderEvidenceNote',
    'renderSimpleSnapshot',
    'renderSimpleWorkspaceBody',
    'renderResearchSection',
    'metricItems',
    'table-earliest',
    'table-latest',
    'hk-00700-2025',
    'hk-03690-2025',
    '¥15,563.14亿元'
  ]) assert.equal(html.includes(obsolete), false, `obsolete content remains: ${obsolete}`);
});
```

- [ ] **Step 2: Run the cleanup test and verify RED**

```bash
node --test --test-name-pattern="prototype no longer stores" tests/prototype.test.mjs
```

Expected: failure listing the old embedded Moutai data and renderers.

- [ ] **Step 3: Delete obsolete data and JavaScript**

Delete the entire `<script type="application/json" id="maotai-snapshot-data">…</script>` block.

Delete the old `maotaiSnapshot`, `snapshots`, and simple company object initialization. Delete these functions in full:

```text
renderResearchSection
renderSimpleSnapshot
renderValueTable
renderEvidenceNote
renderValueLineBody
renderSimpleWorkspaceBody
renderValueLineSnapshot
```

Delete obsolete event actions:

```text
open-snapshot
select-version
toggle-toc
table-earliest
table-latest
```

Remove `tocOpen` from state. Remove the render-time block that initializes `.value-table-scroll` to the latest year. Confirm `renderSnapshot()` is the HTML iframe version from Task 2.

- [ ] **Step 4: Delete unused financial-body CSS**

Delete complete selector blocks whose only consumers were removed:

```text
.metric-strip, .metric, .metric-label, .metric-value
.verdict-banner and descendants
.scan-rail, .scan-step, .scan-number, .scan-label
.snapshot-grid, .snapshot-body, .research-section and evidence/source descendants
.snapshot-toc, .version-list, .mobile-toc-toggle
.value-page and every .value-* selector
.question-scroll, .question-table and related question selectors
.mental-table and descendants
```

Remove their corresponding `@media`, `.prototype-stage.is-mobile`, and `@container workspace-detail` rules. Keep shared shell, directory, iframe, admin, dialog, toast, and focus styles.

Run this search and inspect every remaining match:

```bash
rg -n "value-|metric-strip|scan-rail|research-section|snapshot-toc|question-table|mental-table" doc/prototype.html
```

Expected: no output.

- [ ] **Step 5: Run cleanup and complete automated verification**

```bash
node --test --test-name-pattern="prototype no longer stores" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git diff --check
```

Expected: every test passes and the whitespace check prints nothing.

- [ ] **Step 6: Start the local preview and verify public behavior**

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

Open `http://127.0.0.1:4173/doc/prototype.html` and verify:

```text
The directory has exactly two companies.
贵州茅台 is selected by default.
The public iframe src ends with 价值线_贵州茅台_企业快照版.html.
The iframe visible heading contains 贵州茅台.
Selecting 哔哩哔哩 changes iframe src and visible heading to 哔哩哔哩.
The outer route remains home.
Search, CN/HK filters, empty state, retry, and same-page selection remain correct.
The outer stage has no horizontal overflow.
The generated report tables scroll horizontally inside the iframe.
Fragment links inside each iframe navigate within that iframe.
```

- [ ] **Step 7: Verify mobile drawer and administrator behavior**

At 390px verify drawer open, close, Escape, backdrop, focus trap, and company selection. Then log in with `admin / demo123` and verify:

```text
The list contains 贵州茅台, 哔哩哔哩, and HTML 格式错误示例.
Both valid records are published, clean, and preview their registered HTML path.
The invalid record has two errors, no iframe, and a disabled publish button.
Upload and scan copy consistently says HTML.
```

- [ ] **Step 8: Check console, final tests, and commit**

The page console must contain zero error-level messages. Then run:

```bash
node --test tests/prototype.test.mjs
git diff --check
git status --short
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "refactor: remove copied financial snapshot content"
```

Expected: all tests pass; after commit, status contains only user-owned untracked generated inputs, the root-level duplicate Bilibili files, and `skills/`.

## Plan Self-Review

- Spec coverage: manifest, file existence and safety, public iframe, shared administrator preview, two-company scope, HTML upload copy, validation failure, sandbox isolation, mobile drawer, old-content removal, and browser verification each map to a task.
- Placeholder scan: no deferred implementation markers or unspecified validation steps remain.
- Interface consistency: `htmlSnapshots`, `selectedSnapshotId`, `renderSnapshotFrame(snapshot, mode)`, `snapshotForRecord(record)`, and `renderInvalidHtmlPreview()` keep the same names across public rendering, administrator rendering, tests, and cleanup.
