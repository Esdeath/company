# Interactive HTML Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `doc/prototype.html`, a self-contained, mobile-first interactive prototype covering the public company snapshot experience and the administrator import-and-publish workflow.

**Architecture:** One HTML document contains semantic markup, design tokens, responsive CSS, mock data, and an in-memory state renderer. A small Node test reads the file as text, verifies the standalone contract and required interaction surfaces, and compiles the inline JavaScript to catch syntax failures. Browser verification covers DOM behavior that cannot be exercised without adding a frontend dependency.

**Tech Stack:** HTML5, CSS, browser JavaScript, Node.js built-in `node:test`, no external packages.

## Global Constraints

- Create one deliverable at `doc/prototype.html`; keep CSS and JavaScript inline.
- Do not load frameworks, CDNs, network images, web fonts, or third-party scripts.
- The prototype must work when opened through `file://` without a server.
- Mock data stays in memory and resets on refresh.
- Cover public home/search, snapshot detail, admin login, snapshot management, and review/publish.
- Provide an evaluator-only control bar with page and 390px mobile-width switches.
- Use the visual tokens and content boundaries in `docs/superpowers/specs/2026-07-16-interactive-html-prototype-design.md`.
- Do not modify or commit `skills/`.

---

### Task 1: Standalone shell and prototype state

**Files:**
- Create: `tests/prototype.test.mjs`
- Create: `doc/prototype.html`

**Interfaces:**
- Consumes: the approved prototype specification and page documents under `doc/`.
- Produces: `window.prototypeApp.navigate(route)`, `window.prototypeApp.setViewport(mode)`, `window.prototypeApp.reset()`, and a root element `#app` used by all later tasks.

- [ ] **Step 1: Write the failing standalone contract test**

Create `tests/prototype.test.mjs` with these imports, helpers, and first test:

```js
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const prototypePath = new URL('../doc/prototype.html', import.meta.url);

function readPrototype() {
  return readFileSync(prototypePath, 'utf8');
}

function inlineScript(html) {
  const matches = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  return matches.map((match) => match[1]).join('\n');
}

test('prototype is a standalone HTML document', () => {
  const html = readPrototype();
  assert.match(html, /^<!doctype html>/i);
  assert.match(html, /id="app"/);
  assert.match(html, /window\.prototypeApp/);
  assert.doesNotMatch(html, /<(?:script|img)[^>]+src=["']https?:\/\//i);
  assert.doesNotMatch(html, /<link[^>]+href=["']https?:\/\//i);
  assert.doesNotMatch(html, /@import\s+url\(["']?https?:\/\//i);
  assert.doesNotThrow(() => new Function(inlineScript(html)));
});
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run:

```bash
node --test tests/prototype.test.mjs
```

Expected: FAIL with `ENOENT` for `doc/prototype.html`.

- [ ] **Step 3: Create the semantic shell, tokens, state, and renderer**

Create `doc/prototype.html` with:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>企业快照库 · 交互原型</title>
  <style>
    :root {
      --canvas: #f2f5f6;
      --surface: #ffffff;
      --ink: #17212b;
      --muted: #66727d;
      --line: #d7dee3;
      --accent: #155e75;
      --positive: #2f6b4f;
      --caution: #a15c16;
      --negative: #a33a3a;
      --radius-card: 8px;
      --radius-control: 6px;
      --shadow: 0 18px 55px rgba(23, 33, 43, 0.1);
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: #dfe5e7; color: var(--ink); font-family: system-ui, sans-serif; }
    button, input, select { font: inherit; }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
      outline: 3px solid rgba(21, 94, 117, 0.35);
      outline-offset: 2px;
    }
    .prototype-frame { min-height: 100vh; }
    .prototype-stage { margin: 0 auto; min-height: calc(100vh - 52px); background: var(--canvas); }
    .prototype-stage.is-mobile { width: min(390px, 100%); box-shadow: var(--shadow); }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; }
    }
  </style>
</head>
<body>
  <div id="app"></div>
  <script>
    (() => {
      const initialState = Object.freeze({
        route: 'home',
        viewportMode: 'desktop',
        isAuthenticated: false,
        searchQuery: '',
        marketFilter: 'ALL',
        sortMode: 'data_desc',
        selectedSnapshot: 'hk-00700-2025',
        adminStatusFilter: 'all',
        validationScenario: 'warning',
        dialog: null,
        toast: null
      });
      let state = { ...initialState };
      const app = document.querySelector('#app');

      function setState(patch) {
        state = { ...state, ...patch };
        render();
      }

      function render() {
        app.innerHTML = `<div class="prototype-frame"><main class="prototype-stage ${state.viewportMode === 'mobile' ? 'is-mobile' : ''}"><p>原型正在构建</p></main></div>`;
      }

      window.prototypeApp = {
        navigate(route) { setState({ route, dialog: null, toast: null }); },
        setViewport(viewportMode) { setState({ viewportMode }); },
        reset() { state = { ...initialState }; render(); }
      };
      render();
    })();
  </script>
</body>
</html>
```

- [ ] **Step 4: Run the standalone test**

Run:

```bash
node --test tests/prototype.test.mjs
```

Expected: 1 test passes, 0 fail.

- [ ] **Step 5: Commit the shell**

```bash
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: add standalone prototype shell"
```

### Task 2: Public search and snapshot reading flow

**Files:**
- Modify: `doc/prototype.html`
- Modify: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: Task 1 `setState()`, `render()`, and the `#app` root.
- Produces: `renderHome()`, `renderSnapshot()`, `normalizeTicker(value, market)`, `filteredSnapshots()`, and actions `search`, `market`, `sort`, `open-snapshot`, `back-results`, `select-version`, `toggle-toc`, `retry-public`.

- [ ] **Step 1: Add failing public-surface tests**

Append:

```js
test('prototype contains the complete public research flow', () => {
  const html = readPrototype();
  for (const required of [
    'data-route="home"',
    'data-route="snapshot"',
    'data-action="search"',
    'data-action="market"',
    'data-action="sort"',
    'data-action="open-snapshot"',
    'data-action="select-version"',
    'data-action="toggle-toc"',
    '事实',
    '判断',
    '待验证',
    '快照扫描轨'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});
```

- [ ] **Step 2: Run the public-surface test and verify it fails**

Run:

```bash
node --test --test-name-pattern="public research" tests/prototype.test.mjs
```

Expected: FAIL with the first missing public marker.

- [ ] **Step 3: Add realistic snapshot data and public renderers**

Add three companies and one historical version to the inline script. Each item must follow this shape:

```js
{
  id: 'hk-00700-2025',
  companyName: '腾讯控股',
  ticker: '00700',
  market: 'HK',
  exchange: 'HKEX',
  dataAsOf: '2025-12-31',
  publishedAt: '2026-07-16',
  generatedAt: '2026-07-16 10:30',
  summary: '现金流和资产负债表稳健，增长持续性仍需结合核心业务继续验证。',
  verdict: 'second_round',
  metrics: { pe: '18.2', pb: '3.4', dividend: '2.1%', marketCap: '44,500 亿港元' },
  sections: [
    { id: 'entry', title: '一、入口检验', kind: 'fact', body: '经营现金流为正，净现金覆盖主要短期偿债需求。' },
    { id: 'scan', title: '二、五步扫描', kind: 'judgement', body: '盈利质量通过第一轮检查，但资本开支回报仍需持续跟踪。' },
    { id: 'mental', title: '三、5 秒心算', kind: 'fact', body: '以当前市值和近年自由现金流计算，现金回报率仍需结合增长判断。' },
    { id: 'questions', title: '四、五问清单', kind: 'todo', body: '待验证视频号商业化对利润结构的长期影响。' },
    { id: 'sources', title: '五、资料来源', kind: 'source', body: '2025 年年度报告；港交所披露易；行情日期 2026-07-15。' }
  ]
}
```

Implement exact code normalization:

```js
function normalizeTicker(value, market) {
  const digits = value.trim().replace(/\D/g, '');
  if (!digits) return value.trim().toLowerCase();
  return market === 'HK' ? digits.padStart(5, '0') : digits.padStart(6, '0');
}
```

`renderHome()` must output the hero, search form, market buttons, sort select, state controls, result count, cards, empty state, and retry state. `renderSnapshot()` must output metadata, metric strip, verdict, five-step rail, TOC, version buttons, tagged content blocks, sources, and disclaimer.

- [ ] **Step 4: Add delegated public event handling**

Use one click listener and one submit listener on `#app`:

```js
app.addEventListener('click', (event) => {
  const trigger = event.target.closest('[data-action]');
  if (!trigger) return;
  const { action, value, id } = trigger.dataset;
  if (action === 'market') setState({ marketFilter: value });
  if (action === 'open-snapshot') setState({ route: 'snapshot', selectedSnapshot: id });
  if (action === 'back-results') setState({ route: 'home' });
  if (action === 'select-version') setState({ selectedSnapshot: id });
  if (action === 'retry-public') setState({ publicScenario: 'normal' });
  if (action === 'toggle-toc') trigger.closest('.snapshot-page').classList.toggle('toc-open');
});

app.addEventListener('submit', (event) => {
  if (!event.target.matches('[data-action="search"]')) return;
  event.preventDefault();
  setState({ searchQuery: new FormData(event.target).get('q').trim() });
});

app.addEventListener('change', (event) => {
  if (event.target.matches('[data-action="sort"]')) setState({ sortMode: event.target.value });
});
```

- [ ] **Step 5: Run all static tests**

Run:

```bash
node --test tests/prototype.test.mjs
```

Expected: 2 tests pass, 0 fail.

- [ ] **Step 6: Commit the public flow**

```bash
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: prototype public snapshot flow"
```

### Task 3: Administrator login, import, validation, and publishing

**Files:**
- Modify: `doc/prototype.html`
- Modify: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: Task 1 state renderer and Task 2 event delegation.
- Produces: `renderLogin()`, `renderAdminList()`, `renderReview()`, `openDialog(kind, snapshotId)`, `closeDialog()`, `showToast(message, tone)`, and actions `login`, `logout`, `admin-filter`, `simulate-upload`, `scan-inbox`, `review-snapshot`, `review-tab`, `publish`, `confirm-dialog`, `withdraw`, `delete-draft`.

- [ ] **Step 1: Add failing administrator-flow tests**

Append:

```js
test('prototype contains the complete administrator workflow', () => {
  const html = readPrototype();
  for (const required of [
    'data-route="login"',
    'data-route="admin-list"',
    'data-route="review"',
    'data-action="login"',
    'data-action="simulate-upload"',
    'data-action="scan-inbox"',
    'data-action="review-snapshot"',
    'data-action="publish"',
    'data-action="confirm-dialog"',
    'demo123',
    '校验错误',
    '校验警告'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});
```

- [ ] **Step 2: Run the administrator-flow test and verify it fails**

Run:

```bash
node --test --test-name-pattern="administrator workflow" tests/prototype.test.mjs
```

Expected: FAIL with the first missing administrator marker.

- [ ] **Step 3: Implement login and protected prototype navigation**

Use `admin` / `demo123` as the visible demo credential. The login submit branch must be:

```js
function handleLogin(form) {
  const data = new FormData(form);
  const username = String(data.get('username') || '').trim();
  const password = String(data.get('password') || '');
  if (!username || !password) return setState({ loginError: '请输入用户名和密码。' });
  if (username !== 'admin' || password !== 'demo123') {
    return setState({ loginError: '用户名或密码不正确。请使用页面上的演示账号。' });
  }
  setState({ isAuthenticated: true, route: 'admin-list', loginError: null, toast: { tone: 'success', message: '已登录。' } });
}
```

If the control bar opens `admin-list` or `review` while logged out, render the login view and preserve the requested destination.

- [ ] **Step 4: Implement admin list and simulated import states**

Render three records: a warning draft, an error draft, and a published snapshot. Add state filters, market filters, keyword search, upload panel, and inbox scan. `simulate-upload` must set the warning draft as selected and show this report:

```js
const validationReports = {
  warning: {
    errors: [],
    warnings: ['市盈率口径来自行情接口，与财报期末日期不同。'],
    info: ['港股代码 700 已标准化为 00700。']
  },
  error: {
    errors: ['frontmatter 缺少 reporting_currency。', '正文缺少“五、资料来源”。'],
    warnings: [],
    info: []
  }
};
```

- [ ] **Step 5: Implement review tabs, dialogs, and workflow transitions**

Use one native-like custom dialog with `role="dialog"`, `aria-modal="true"`, a heading, message, cancel, and confirm buttons. Exact status transitions:

```js
function confirmWorkflow(kind, snapshotId) {
  if (kind === 'publish') updateAdminRecord(snapshotId, { status: 'published', publishedAt: '刚刚' });
  if (kind === 'withdraw') updateAdminRecord(snapshotId, { status: 'withdrawn' });
  if (kind === 'delete') removeAdminRecord(snapshotId);
  closeDialog();
  showToast(kind === 'publish' ? '已发布。' : kind === 'withdraw' ? '已撤回。' : '草稿已删除。', 'success');
}
```

Disable publish when the selected report has errors. Warning-only reports open the publish confirmation. The delete action appears only for non-published records.

- [ ] **Step 6: Run all static tests**

Run:

```bash
node --test tests/prototype.test.mjs
```

Expected: 3 tests pass, 0 fail.

- [ ] **Step 7: Commit the administrator flow**

```bash
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: prototype admin publishing flow"
```

### Task 4: Responsive polish, accessibility, and browser verification

**Files:**
- Modify: `doc/prototype.html`
- Modify: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: all views and actions from Tasks 1–3.
- Produces: final standalone prototype with keyboard-safe dialogs, desktop/mobile review controls, empty/error demos, and documented interaction hints.

- [ ] **Step 1: Add failing accessibility and responsive contract tests**

Append:

```js
test('prototype exposes responsive and accessibility contracts', () => {
  const html = readPrototype();
  for (const required of [
    'lang="zh-CN"',
    'name="viewport"',
    'data-action="viewport"',
    'role="dialog"',
    'aria-modal="true"',
    'aria-live="polite"',
    '@media (max-width: 767px)',
    '@media (prefers-reduced-motion: reduce)'
  ]) assert.ok(html.includes(required), `missing ${required}`);
});
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```bash
node --test --test-name-pattern="responsive and accessibility" tests/prototype.test.mjs
```

Expected: FAIL with the first missing responsive or accessibility marker.

- [ ] **Step 3: Complete mobile layouts and evaluator controls**

Add a fixed evaluator bar that uses `data-action="prototype-route"` and `data-action="viewport"`. At `767px` and below:

```css
@media (max-width: 767px) {
  .site-shell { padding-inline: 16px; }
  .snapshot-grid, .admin-review-grid { grid-template-columns: 1fr; }
  .snapshot-cards { grid-template-columns: 1fr; }
  .admin-table { display: none; }
  .admin-card-list { display: grid; }
  .desktop-toc { display: none; }
  .mobile-toc-toggle { display: inline-flex; }
}
```

The 390px evaluator mode adds `is-mobile` to `.prototype-stage`, so the same media behavior must also be repeated under `.prototype-stage.is-mobile` selectors even when the browser window is wide.

- [ ] **Step 4: Implement dialog focus and transient feedback**

When opening a dialog, remember `document.activeElement`, focus the first dialog button, close on Escape, trap Tab inside, and restore focus after close. Render toast feedback inside:

```html
<div class="toast-region" aria-live="polite" aria-atomic="true"></div>
```

Clear a toast after 2.8 seconds. Store the timer ID so a new toast cancels the old timer.

- [ ] **Step 5: Run the complete automated verification**

Run:

```bash
node --test tests/prototype.test.mjs
git diff --check
```

Expected: 4 tests pass, 0 fail; `git diff --check` has no output.

- [ ] **Step 6: Verify all interaction scenarios in a browser**

Open `doc/prototype.html` through `file://` and verify this checklist:

```text
[ ] Control bar switches all five views
[ ] Desktop/mobile switch constrains the stage to 390px and restores it
[ ] Search “腾讯” returns Tencent
[ ] Search “700” returns 00700
[ ] HK filter hides CN companies
[ ] Empty and error states can return to normal
[ ] Snapshot card opens detail and back restores results
[ ] TOC and historical version controls work
[ ] Wrong login fails; admin/demo123 succeeds
[ ] Simulated upload displays warning and normalization info
[ ] Error draft cannot publish
[ ] Warning draft opens confirmation and publishes
[ ] Published record can be withdrawn
[ ] Escape closes the dialog and focus returns to its trigger
[ ] Browser console contains no JavaScript error
```

Expected: every item passes in desktop and mobile evaluator modes.

- [ ] **Step 7: Commit the final verified prototype**

```bash
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: finish responsive html prototype"
```
