# Master-Detail Company Homepage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the public card-grid homepage with a desktop master-detail research workspace and a mobile company drawer, defaulting to the complete Guizhou Moutai financial snapshot.

**Architecture:** Keep the standalone `doc/prototype.html` and its embedded snapshot data. Add a small public selection state layer, render the left directory and right document from the same snapshot object, reuse `renderValueLineBody()` for Moutai, and preserve the legacy detail and administrator routes.

**Tech Stack:** Standalone HTML, CSS, vanilla JavaScript, embedded JSON, Node.js built-in test runner.

## Global Constraints

- The public homepage has only one category: “财务快照”.
- Desktop uses a fixed `320px` rail and independently scrolling detail pane.
- Mobile uses a left drawer with width `min(88vw, 340px)`.
- The default selection is `cn-600519-2025` (贵州茅台).
- The browser reads parsed snapshot objects; it does not parse Markdown.
- `value_line` renders complete Moutai content; `simple` renders the five-section Tencent and Meituan content.
- Failed or unpublished records remain administrator-only.
- Keep the page standalone with no remote scripts, styles, fonts, or images.
- Preserve all existing administrator demonstrations.
- At 390px the page cannot scroll horizontally; financial tables retain local horizontal scrolling.
- Drawer motion respects `prefers-reduced-motion`.

## File Map

- Modify `doc/prototype.html`: state, workspace renderers, layout, drawer, focus handling, and delegated actions.
- Modify `tests/prototype.test.mjs`: state, structure, accessibility, responsive, and regression contracts.
- Do not modify the two user-owned `doc/价值线_贵州茅台_企业快照版.*` inputs or `skills/`.

---

### Task 1: Public selection and filter reconciliation

**Files:**
- Modify: `doc/prototype.html:859-918, 1162-1165, 1427-1458`
- Test: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: `snapshots`, `filteredSnapshots()`, `initialState`, and `setState()`.
- Produces: `selectedSnapshotId: string | null`, `companyDrawerOpen: boolean`, `selectedPublicSnapshot(): object | null`, and `publicSelectionPatch(patch): object`.

- [ ] **Step 1: Write the failing state-contract test**

Append:

```js
test('public workspace defaults to Moutai and reconciles selection after filtering', () => {
  const html = readPrototype();
  assert.match(html, /selectedSnapshotId: 'cn-600519-2025'/);
  assert.match(html, /companyDrawerOpen: false/);
  assert.match(html, /function selectedPublicSnapshot\(\)/);
  assert.match(html, /function publicSelectionPatch\(patch\)/);
  assert.match(html, /results\.some\(\(snapshot\) => snapshot\.id === nextSelectedId\)/);
  assert.match(html, /nextSelectedId = results\[0\]\?\.id \|\| null/);
});
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
node --test --test-name-pattern="public workspace defaults" tests/prototype.test.mjs
```

Expected: one failure because the new public state and helpers are absent.

- [ ] **Step 3: Add state and helpers**

Replace the existing `selectedSnapshot` field and add the drawer field:

```js
selectedSnapshotId: 'cn-600519-2025',
companyDrawerOpen: false,
```

Add after `filteredSnapshots()`:

```js
function selectedPublicSnapshot() {
  if (state.publicScenario !== 'normal') return null;
  return snapshots.find((snapshot) => snapshot.id === state.selectedSnapshotId && snapshot.isLatest) || null;
}

function publicSelectionPatch(patch) {
  const previousState = state;
  state = { ...state, ...patch };
  const results = filteredSnapshots();
  let nextSelectedId = state.selectedSnapshotId;
  state = previousState;
  if (!results.some((snapshot) => snapshot.id === nextSelectedId)) {
    nextSelectedId = results[0]?.id || null;
  }
  return { ...patch, selectedSnapshotId: nextSelectedId };
}
```

Update the legacy detail renderer and history-version active state:

```js
function renderSnapshot() {
  const snapshot = snapshots.find((item) => item.id === state.selectedSnapshotId) || maotaiSnapshot;
  return snapshot.format === 'value_line' ? renderValueLineSnapshot(snapshot) : renderSimpleSnapshot(snapshot);
}
```

Use `version.id === state.selectedSnapshotId` and set `selectedSnapshotId` in the `select-version` action.

- [ ] **Step 4: Reconcile selection in public actions**

Use these exact patches:

```js
if (action === 'market') setState(publicSelectionPatch({ marketFilter: value, publicScenario: 'normal' }));
if (action === 'retry-public') setState(publicSelectionPatch({ publicScenario: 'normal' }));
if (action === 'clear-search') setState(publicSelectionPatch({ searchQuery: '', marketFilter: 'ALL', publicScenario: 'normal' }));
if (action === 'select-version') setState({ selectedSnapshotId: id });
```

In the public search submit handler:

```js
const searchQuery = String(new FormData(event.target).get('q') || '').trim();
setState(publicSelectionPatch({ searchQuery, publicScenario: 'normal' }));
```

In the sort change handler:

```js
if (event.target.matches('[data-action="sort"]')) setState(publicSelectionPatch({ sortMode: event.target.value }));
```

- [ ] **Step 5: Run tests and commit**

```bash
node --test --test-name-pattern="public workspace defaults" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: add public company selection state"
```

Expected: all tests pass before the commit.

---

### Task 2: Desktop master-detail workspace

**Files:**
- Modify: `doc/prototype.html:150-290, 947-1165`
- Test: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: `filteredSnapshots()`, `selectedPublicSnapshot()`, `metricItems()`, `renderValueLineBody()`, and `renderResearchSection()`.
- Produces: `renderCompanyCard(snapshot, selected)`, `renderCompanyDirectory(options)`, `renderSimpleWorkspaceBody(snapshot)`, `renderWorkspaceDetail(snapshot)`, and `renderCompanyWorkspace()`.

- [ ] **Step 1: Write the failing workspace test**

Append:

```js
test('homepage renders a master-detail financial workspace', () => {
  const html = readPrototype();
  for (const required of [
    "class='company-workspace'",
    "aria-label='公司目录'",
    "class='company-directory__scroll'",
    "class='workspace-detail__scroll'",
    'data-action="select-company"',
    "aria-current='${selected ? 'true' : 'false'}'",
    'renderCompanyDirectory',
    'renderWorkspaceDetail',
    '财务快照'
  ]) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /grid-template-columns: 320px minmax\(0, 1fr\)/);
  assert.match(html, /\.company-directory__scroll[^}]*overflow-y: auto/s);
  assert.match(html, /\.workspace-detail__scroll[^}]*overflow-y: auto/s);
});
```

In `prototype contains the complete public research flow`, replace `data-action="open-snapshot"` with `data-action="select-company"`. Keep `data-route="snapshot"` because the prototype bar still exposes that regression route.

- [ ] **Step 2: Run the test and verify failure**

```bash
node --test --test-name-pattern="homepage renders a master-detail" tests/prototype.test.mjs
```

Expected: failure because the hero and three-column grid still render.

- [ ] **Step 3: Add the desktop layout CSS**

Insert after the existing card styles:

```css
.workspace-site-shell { display: flex; flex-direction: column; height: calc(100dvh - 52px); min-height: 620px; overflow: hidden; }
.company-workspace { display: grid; grid-template-columns: 320px minmax(0, 1fr); flex: 1; min-height: 0; overflow: hidden; }
.company-directory { z-index: 2; display: flex; min-width: 0; min-height: 0; flex-direction: column; background: #e8edef; border-right: 1px solid var(--line); }
.company-directory__head { position: relative; padding: 20px 18px 14px; border-bottom: 1px solid var(--line); }
.company-directory__title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.company-directory__title h1 { margin: 0; font-family: var(--font-display); font-size: 25px; font-weight: 600; }
.company-directory__title span { color: var(--muted); font-family: var(--font-data); font-size: 11px; }
.directory-search { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 7px; margin-top: 14px; }
.directory-search .search-input { min-height: 42px; padding: 0 12px; }
.directory-search .button { min-height: 42px; padding-inline: 12px; }
.directory-filter { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 10px; }
.directory-filter .sort-control { width: 104px; }
.company-directory__scroll { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 12px; }
.directory-card { position: relative; width: 100%; margin: 0 0 10px; padding: 16px; overflow: hidden; color: var(--ink); text-align: left; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); cursor: pointer; }
.directory-card::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 4px; background: transparent; }
.directory-card:hover { border-color: #9eafb7; }
.directory-card.is-selected { background: #f7fbfc; border-color: #8fb8c3; box-shadow: 0 10px 28px rgba(23, 33, 43, 0.08); }
.directory-card.is-selected::before { background: var(--accent); }
.directory-card__current { color: var(--accent); font-size: 11px; font-weight: 750; }
.directory-card h2 { margin: 13px 0 4px; font-family: var(--font-display); font-size: 22px; font-weight: 600; }
.directory-card .card-summary { display: -webkit-box; margin: 12px 0 14px; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.workspace-detail { min-width: 0; min-height: 0; background: var(--canvas); }
.workspace-detail__scroll { height: 100%; overflow-y: auto; overscroll-behavior: contain; scroll-behavior: smooth; }
.workspace-context { position: sticky; top: 0; z-index: 12; display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 64px; padding: 10px 24px; background: rgba(242, 245, 246, 0.95); border-bottom: 1px solid var(--line); backdrop-filter: blur(10px); }
.workspace-context__identity { min-width: 0; }
.workspace-context__identity strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workspace-context__identity span { color: var(--muted); font-family: var(--font-data); font-size: 11px; }
.workspace-context__category { color: var(--accent); font-size: 12px; font-weight: 750; }
.workspace-document { width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding: 0 0 64px; }
.workspace-document .snapshot-head { padding-top: 28px; }
.workspace-empty { display: grid; min-height: 100%; place-items: center; padding: 32px; }
.company-drawer-button { display: none; }
```

- [ ] **Step 4: Add directory renderers**

Replace `renderCard()` and `renderHomeResults()` with:

```js
function renderCompanyCard(snapshot, selected) {
  const skip = snapshot.verdict === 'skip';
  return `<button class='directory-card ${selected ? 'is-selected' : ''}' type='button' data-action="select-company" data-id='${snapshot.id}' aria-current='${selected ? 'true' : 'false'}'><div class='card-meta'><span class='market-tag'>${snapshot.market === 'CN' ? 'A 股' : '港股'}</span><time>${snapshot.dataAsOf}</time></div><h2>${snapshot.companyName}</h2><span class='ticker'>${snapshot.ticker} · ${snapshot.exchange}</span><p class='card-summary'>${snapshot.summary}</p><div class='mini-metrics'>${metricItems(snapshot)}</div><div class='card-footer'><span class='verdict ${skip ? 'verdict--skip' : ''}'>${skip ? '暂不进入第二轮' : '进入第二轮研究'}</span>${selected ? `<span class='directory-card__current'>当前阅读</span>` : ''}</div></button>`;
}

function renderDirectoryResults() {
  if (state.publicScenario === 'error') return `<div class='empty-state'><span class='empty-state__mark'>!</span><h3>公司目录没有加载成功</h3><p>恢复后可以继续查看公司快照。</p><button class='button button--primary' type='button' data-action='retry-public'>重新加载</button></div>`;
  const results = filteredSnapshots();
  if (!results.length) return `<div class='empty-state'><span class='empty-state__mark'>0</span><h3>没有找到公司</h3><p>尝试公司简称、证券代码，或清除市场筛选。</p><button class='button' type='button' data-action='clear-search'>清除筛选</button></div>`;
  return results.map((snapshot) => renderCompanyCard(snapshot, snapshot.id === state.selectedSnapshotId)).join('');
}

function renderCompanyDirectory({ drawer = false } = {}) {
  const count = state.publicScenario === 'error' ? 0 : filteredSnapshots().length;
  return `<aside class='company-directory ${drawer ? 'company-directory--drawer' : ''}' aria-label='公司目录' ${drawer ? `role='dialog' aria-modal='true' aria-labelledby='company-drawer-title'` : ''}><div class='company-directory__head'><div class='company-directory__title'><h1 id='${drawer ? 'company-drawer-title' : 'company-directory-title'}'>公司目录</h1><span>${count} 家公司</span></div>${drawer ? `<button class='drawer-close' type='button' data-action="close-company-drawer" data-drawer-initial aria-label='关闭公司列表'>×</button>` : ''}<form class='directory-search' data-action="search"><input class='search-input' name='q' value='${escapeHtml(state.searchQuery)}' aria-label='公司名称或证券代码' placeholder='公司名称或代码'><button class='button button--primary' type='submit'>搜索</button></form><div class='directory-filter'><div class='filter-group' aria-label='市场筛选'>${[['ALL', '全部'], ['CN', 'A 股'], ['HK', '港股']].map(([value, label]) => `<button class='filter-button ${state.marketFilter === value ? 'is-active' : ''}' type='button' data-action="market" data-value='${value}' aria-pressed='${state.marketFilter === value}'>${label}</button>`).join('')}</div><select class='sort-control' data-action="sort" aria-label='结果排序'><option value='data_desc' ${state.sortMode === 'data_desc' ? 'selected' : ''}>日期</option><option value='published_desc' ${state.sortMode === 'published_desc' ? 'selected' : ''}>发布</option><option value='name_asc' ${state.sortMode === 'name_asc' ? 'selected' : ''}>名称</option></select></div></div><div class='company-directory__scroll' aria-live='polite'>${renderDirectoryResults()}</div></aside>`;
}
```

- [ ] **Step 5: Add detail and workspace renderers**

Add:

```js
function renderSimpleWorkspaceBody(snapshot) {
  const skip = snapshot.verdict === 'skip';
  return `<header class='snapshot-head'><div class='snapshot-kicker'><span>${snapshot.market} · ${snapshot.exchange}</span><span>${snapshot.ticker}</span><span>数据截至 ${snapshot.dataAsOf}</span></div><h1 class='snapshot-title'>${snapshot.companyName}</h1><p class='snapshot-summary'>${snapshot.summary}</p></header><div class='metric-strip'>${[['市盈率 TTM', snapshot.metrics.pe], ['市净率', snapshot.metrics.pb], ['股息率', snapshot.metrics.dividend], ['总市值', snapshot.metrics.marketCap]].map(([label, value]) => `<div class='metric'><span class='metric-label'>${label}</span><span class='metric-value'>${value}</span></div>`).join('')}</div><div class='verdict-banner ${skip ? 'is-skip' : ''}'><div><strong>${skip ? '暂不进入第二轮研究' : '进入第二轮研究'}</strong><small>这是第一轮筛选结论，不是买卖建议。</small></div><span class='ticker'>生成于 ${snapshot.generatedAt}</span></div><div class='scan-rail' aria-label='快照扫描轨'>${snapshot.sections.map((section, index) => `<div class='scan-step'><span class='scan-number'>0${index + 1}</span><span class='scan-label'>${section.title.replace(/^.+、/, '')}</span></div>`).join('')}</div><article class='snapshot-body'>${snapshot.sections.map(renderResearchSection).join('')}<div class='disclaimer'>内容基于公开资料整理，仅供研究参考，不构成投资建议。财务数据以公司正式披露为准。</div></article>`;
}

function renderWorkspaceDetail(snapshot) {
  if (!snapshot) return `<section class='workspace-detail workspace-empty'><div class='empty-state'><span class='empty-state__mark'>0</span><h3>没有可阅读的财务快照</h3><p>请调整公司名称或市场条件。</p><button class='button' type='button' data-action='clear-search'>清除筛选</button></div></section>`;
  const toc = [['quick-conclusion', '30 秒结论'], ['business-model', '商业模式'], ['per-share-history', '每股数据'], ['operating-history', '经营数据'], ['mental-math', '5 秒心算'], ['capital-structure', '资本结构'], ['five-questions', '五问清单'], ['methodology', '数据口径']];
  const body = snapshot.format === 'value_line' ? `<header class='snapshot-head'><div class='snapshot-kicker'><span>A 股 · ${snapshot.exchange}</span><span>${snapshot.ticker}</span><span>行情 ${snapshot.quoteAsOf}</span></div><h1 class='snapshot-title'>${snapshot.companyName}</h1><p class='snapshot-summary'>只寻找事实，不寻求意见。${snapshot.summary}</p></header><button class='button mobile-toc-toggle' type='button' data-action="toggle-toc">${state.tocOpen ? '收起目录' : '展开目录'}</button><div class='value-layout'><article class='value-body'>${renderValueLineBody(snapshot)}</article><aside class='value-toc ${state.tocOpen ? '' : 'desktop-toc'}'><h2>本页目录</h2>${toc.map(([id, label]) => `<a href='#${id}'>${label}</a>`).join('')}</aside></div><div class='disclaimer'>内容基于公开资料和直接计算，仅供研究参考，不构成投资建议。财务数据以公司正式披露为准。</div>` : renderSimpleWorkspaceBody(snapshot);
  return `<section class='workspace-detail'><div class='workspace-context'><button class='button company-drawer-button' type='button' data-action="open-company-drawer" aria-haspopup='dialog'>选择公司</button><div class='workspace-context__identity'><strong>${snapshot.companyName}</strong><span>${snapshot.ticker} · ${snapshot.market === 'CN' ? 'A 股' : '港股'}</span></div><span class='workspace-context__category'>财务快照</span></div><div class='workspace-detail__scroll' tabindex='-1' data-workspace-scroll><div class='workspace-document ${snapshot.format === 'value_line' ? 'value-page' : ''}'>${body}</div></div></section>`;
}

function renderCompanyWorkspace() {
  return `<div class='site-shell workspace-site-shell' data-route='home'>${renderSiteHeader()}<main class='company-workspace'>${renderCompanyDirectory()}${renderWorkspaceDetail(selectedPublicSnapshot())}</main>${state.companyDrawerOpen ? `<div class='company-drawer-layer'><button class='company-drawer-backdrop' type='button' data-action="close-company-drawer" aria-label='关闭公司列表'></button>${renderCompanyDirectory({ drawer: true })}</div>` : ''}</div>`;
}

function renderHome() { return renderCompanyWorkspace(); }
```

Add the selection action:

```js
if (action === 'select-company') {
  setState({ selectedSnapshotId: id, companyDrawerOpen: false, tocOpen: false });
  app.querySelector('[data-workspace-scroll]')?.scrollTo({ top: 0 });
}
```

- [ ] **Step 6: Run tests and commit**

```bash
node --test --test-name-pattern="homepage renders a master-detail" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git diff --check
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: build master-detail company homepage"
```

Expected: all tests pass and the whitespace check prints nothing.

---

### Task 3: Mobile drawer and focus management

**Files:**
- Modify: `doc/prototype.html:490-620, 1386-1504`
- Test: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: `state.companyDrawerOpen`, `renderCompanyDirectory({ drawer: true })`, and `setState()`.
- Produces: `openCompanyDrawer()`, `closeCompanyDrawer(options)`, and `trapFocus(container, event)`.

- [ ] **Step 1: Write the failing drawer test**

Append:

```js
test('mobile company drawer has complete dismissal and focus contracts', () => {
  const html = readPrototype();
  for (const required of ['data-action="open-company-drawer"', 'data-action="close-company-drawer"', "role='dialog' aria-modal='true'", 'data-drawer-initial', 'function openCompanyDrawer()', 'function closeCompanyDrawer', 'function trapFocus', 'document.body.classList.toggle(\'company-drawer-open\'']) assert.ok(html.includes(required), `missing ${required}`);
  assert.match(html, /\.company-drawer-layer[^}]*position: fixed/s);
  assert.match(html, /width: min\(88vw, 340px\)/);
  assert.match(html, /\.prototype-stage\.is-mobile \.company-workspace > \.company-directory:not\(\.company-directory--drawer\)/);
});
```

- [ ] **Step 2: Run the drawer test and verify failure**

```bash
node --test --test-name-pattern="mobile company drawer" tests/prototype.test.mjs
```

Expected: failure because drawer helpers and responsive rules are absent.

- [ ] **Step 3: Add drawer and mobile CSS**

Insert before the reduced-motion block:

```css
body.company-drawer-open { overflow: hidden; }
.company-drawer-layer { position: fixed; inset: 52px 0 0; z-index: 45; display: none; }
.company-drawer-backdrop { position: absolute; inset: 0; width: 100%; padding: 0; background: rgba(9, 18, 23, 0.52); border: 0; }
.company-directory--drawer { position: relative; width: min(88vw, 340px); height: 100%; box-shadow: 18px 0 52px rgba(23, 33, 43, 0.24); animation: drawer-in 180ms ease-out; }
.drawer-close { position: absolute; top: 13px; right: 12px; display: grid; width: 36px; height: 36px; place-items: center; color: var(--muted); background: transparent; border: 1px solid var(--line); border-radius: 50%; cursor: pointer; }
@keyframes drawer-in { from { transform: translateX(-100%); } to { transform: translateX(0); } }
@media (max-width: 767px) {
  .workspace-site-shell { height: calc(100dvh - 52px); min-height: 0; }
  .company-workspace { grid-template-columns: minmax(0, 1fr); }
  .company-workspace > .company-directory:not(.company-directory--drawer) { display: none; }
  .company-drawer-layer { display: block; }
  .company-drawer-button { display: inline-flex; flex: 0 0 auto; }
  .workspace-context { padding: 8px 16px; }
  .workspace-context__identity { flex: 1; }
  .workspace-context__category { display: none; }
  .workspace-document { width: calc(100% - 32px); }
}
.prototype-stage.is-mobile .workspace-site-shell { height: calc(100dvh - 52px); min-height: 0; }
.prototype-stage.is-mobile .company-workspace { grid-template-columns: minmax(0, 1fr); }
.prototype-stage.is-mobile .company-workspace > .company-directory:not(.company-directory--drawer) { display: none; }
.prototype-stage.is-mobile .company-drawer-layer { display: block; inset: 52px calc((100% - min(390px, 100%)) / 2) 0; }
.prototype-stage.is-mobile .company-drawer-button { display: inline-flex; flex: 0 0 auto; }
.prototype-stage.is-mobile .workspace-context { padding: 8px 16px; }
.prototype-stage.is-mobile .workspace-context__identity { flex: 1; }
.prototype-stage.is-mobile .workspace-context__category { display: none; }
.prototype-stage.is-mobile .workspace-document { width: calc(100% - 32px); }
```

- [ ] **Step 4: Add focus lifecycle helpers**

Add above `setState()`:

```js
function trapFocus(container, event) {
  const focusable = [...container.querySelectorAll('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])')];
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function openCompanyDrawer() {
  setState({ companyDrawerOpen: true });
  window.requestAnimationFrame(() => app.querySelector('[data-drawer-initial]')?.focus());
}

function closeCompanyDrawer({ restoreFocus = true } = {}) {
  setState({ companyDrawerOpen: false });
  if (restoreFocus) window.requestAnimationFrame(() => app.querySelector('[data-action="open-company-drawer"]')?.focus());
}
```

After assigning `app.innerHTML` in `render()`:

```js
document.body.classList.toggle('company-drawer-open', state.companyDrawerOpen);
```

Add actions:

```js
if (action === 'open-company-drawer') openCompanyDrawer();
if (action === 'close-company-drawer') closeCompanyDrawer();
```

Replace the Task 2 `select-company` action with the focus-restoring form:

```js
if (action === 'select-company') {
  const wasDrawerOpen = state.companyDrawerOpen;
  setState({ selectedSnapshotId: id, companyDrawerOpen: false, tocOpen: false });
  app.querySelector('[data-workspace-scroll]')?.scrollTo({ top: 0 });
  if (wasDrawerOpen) window.requestAnimationFrame(() => app.querySelector('[data-action="open-company-drawer"]')?.focus());
}
```

Replace the keydown handler with:

```js
document.addEventListener('keydown', (event) => {
  if (state.companyDrawerOpen) {
    if (event.key === 'Escape') { event.preventDefault(); closeCompanyDrawer(); return; }
    if (event.key === 'Tab') {
      const drawer = app.querySelector('.company-directory--drawer');
      if (drawer) trapFocus(drawer, event);
    }
    return;
  }
  if (!state.dialog) return;
  if (event.key === 'Escape') { event.preventDefault(); closeDialog(); return; }
  if (event.key === 'Tab') {
    const dialog = app.querySelector('[role="dialog"]');
    if (dialog) trapFocus(dialog, event);
  }
});
```

- [ ] **Step 5: Run tests and commit**

```bash
node --test --test-name-pattern="mobile company drawer" tests/prototype.test.mjs
node --test tests/prototype.test.mjs
git diff --check
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: add mobile company drawer"
```

Expected: all tests pass and the whitespace check prints nothing.

---

### Task 4: Browser acceptance and regression polish

**Files:**
- Modify only for verified defects: `doc/prototype.html`
- Test verified defects: `tests/prototype.test.mjs`

**Interfaces:**
- Consumes: completed workspace, drawer, legacy detail renderers, and administrator flows.
- Produces: a browser-verified prototype with no console errors.

- [ ] **Step 1: Start the preview**

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

Open `http://127.0.0.1:4173/doc/prototype.html` in the in-app browser.

- [ ] **Step 2: Verify desktop behavior**

Confirm exactly:

```text
贵州茅台 is selected by default.
The company rail is 320px.
The rail and detail pane scroll independently.
腾讯控股 and 美团 each render five .research-section elements.
贵州茅台 renders eight [data-value-section] elements.
Exactly one card has aria-current="true".
The public route remains data-route="home" after selection.
```

- [ ] **Step 3: Verify filters and failures**

Confirm:

```text
Select 腾讯控股 then filter A 股: 贵州茅台 becomes selected.
Filter 港股 while 贵州茅台 is selected: the first sorted Hong Kong company becomes selected.
A missing search shows directed empty states in both panes.
Clear filters restores a valid selection and content.
请求失败 removes stale detail and exposes retry; retry restores results.
```

- [ ] **Step 4: Verify the 390px drawer**

Confirm:

```text
Desktop rail is hidden and “选择公司” is visible.
Opening focuses the close button and locks body scrolling.
Tab and Shift+Tab stay inside the drawer.
Escape and backdrop close it and restore trigger focus.
Selecting a company closes it and resets detail scroll to top.
The stage has scrollWidth === clientWidth.
Moutai tables remain locally horizontally scrollable.
```

- [ ] **Step 5: Verify existing workflows**

Confirm Moutai earliest/latest buttons and `#mental-math` anchor. Log in with `admin / demo123`; confirm Moutai remains published and clean, while 格式错误示例 retains two errors, disabled publish, and no public preview.

- [ ] **Step 6: Add regressions only for observed defects**

For each observed defect, append a narrowly named test, run it to see the expected failure, patch the smallest related block, and rerun targeted plus full tests. Do not change unrelated administrator or snapshot content.

- [ ] **Step 7: Run final verification and commit**

```bash
node --test tests/prototype.test.mjs
git diff --check
git status --short
git add doc/prototype.html tests/prototype.test.mjs
git commit -m "feat: finish company workspace prototype"
```

Expected: all tests pass, `git diff --check` prints nothing, browser console has zero errors, and status contains only the user's pre-existing untracked sources and `skills/` after commit.

## Plan Self-Review

- Spec coverage: desktop split layout, rich cards, same-page selection, default Moutai, filtering, empty/error behavior, mobile drawer, focus trapping, responsive overflow, rich/simple renderers, administrator preservation, and browser acceptance all map to explicit tasks.
- Placeholder scan: there are no deferred markers or unspecified error-handling steps.
- Interface consistency: `selectedSnapshotId`, `companyDrawerOpen`, `selectedPublicSnapshot()`, `publicSelectionPatch()`, `renderCompanyDirectory()`, `renderWorkspaceDetail()`, `openCompanyDrawer()`, `closeCompanyDrawer()`, and `trapFocus()` use the same names throughout.
