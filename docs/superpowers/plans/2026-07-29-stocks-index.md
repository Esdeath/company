# Stocks Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a standalone `stocks/index.html` that groups every stock research HTML by industry and supports name/code search plus industry filtering.

**Architecture:** Build one dependency-free static HTML document whose embedded stock records are derived from the current `stocks/<行业>/*.html` files. Semantic markup provides the complete link grid before JavaScript runs; a small inline script progressively enhances it with combined search and industry filtering.

**Tech Stack:** HTML5, CSS, vanilla JavaScript, Node.js 24 for verification.

## Global Constraints

- Only add `stocks/index.html`; do not modify existing research files.
- Include only `stocks/<行业>/*.html`; exclude Markdown, hidden files, the root index, and directories without stock HTML.
- Use URL-encoded relative links that work from both `file://` and a static HTTP server.
- Sort industries by name and stocks within each industry by five-digit stock code.
- Keep the page dependency-free and usable before JavaScript runs.
- Use a responsive 1/2/4-column grid without horizontal overflow or text overlap.

---

## File Map

- `stocks/index.html`: owns the static stock dataset, semantic industry sections and links, responsive presentation, search/filter controls, result count, empty state, and inline progressive-enhancement script.

### Task 1: Build And Verify The Static Stocks Index

**Files:**
- Create: `stocks/index.html`

**Interfaces:**
- Consumes: filenames matching `stocks/<行业>/HK_<公司名>(<五位代码>).html`.
- Produces: `.stock-card[data-name][data-code][data-industry]` links, `.industry-section[data-industry]` groups, and the query/filter DOM contract used by the inline script.

- [ ] **Step 1: Verify the index is absent**

Run:

```bash
node -e "const fs=require('node:fs'); if(!fs.existsSync('stocks/index.html')) process.exit(1)"
```

Expected: exit code 1 because `stocks/index.html` has not been created.

- [ ] **Step 2: Create the complete semantic document**

Generate a single HTML document with this stable structure and one actual anchor per discovered stock HTML:

```html
<header class="masthead">
  <p class="eyebrow">COMPANY RESEARCH</p>
  <h1>股票研究资料库</h1>
  <p><strong id="visibleCount">613</strong> 份股票研究 · <strong>11</strong> 个行业</p>
</header>
<main>
  <section class="toolbar" aria-label="资料筛选">
    <label for="stockSearch">搜索公司或股票代码</label>
    <input id="stockSearch" type="search" autocomplete="off">
    <div id="industryFilters" aria-label="按行业筛选"></div>
  </section>
  <div id="industryList">
    <section class="industry-section" data-industry="信息技术">
      <h2>信息技术 <span>77</span></h2>
      <div class="stock-grid">
        <a class="stock-card" data-name="中芯国际" data-code="00981" data-industry="信息技术" href="%E4%BF%A1%E6%81%AF%E6%8A%80%E6%9C%AF/HK_%E4%B8%AD%E8%8A%AF%E5%9B%BD(00981).html">
          <span class="company-name">中芯国际</span>
          <span class="stock-code">HK 00981</span>
          <span class="card-arrow" aria-hidden="true">→</span>
        </a>
      </div>
    </section>
  </div>
  <section id="emptyState" hidden><h2>没有找到匹配的股票</h2><button type="button" id="clearFilters">清除筛选</button></section>
</main>
```

CSS must define a white/charcoal/green palette, visible focus states, industry accents, stable card dimensions, `overflow-wrap: anywhere`, and breakpoints that produce 1, 2, and 4 columns. Include `prefers-reduced-motion: reduce` handling.

- [ ] **Step 3: Add combined search and industry filtering**

Implement one `applyFilters()` function using these normalized values:

```js
const normalize = (value) => value.trim().toLocaleLowerCase('zh-CN');

function applyFilters() {
  const query = normalize(searchInput.value);
  let visibleCount = 0;

  for (const card of stockCards) {
    const matchesIndustry = activeIndustry === '全部' || card.dataset.industry === activeIndustry;
    const haystack = normalize(`${card.dataset.name} ${card.dataset.code} ${card.dataset.industry}`);
    const visible = matchesIndustry && haystack.includes(query);
    card.hidden = !visible;
    if (visible) visibleCount += 1;
  }

  for (const section of industrySections) {
    section.hidden = !section.querySelector('.stock-card:not([hidden])');
  }

  visibleCountElement.textContent = String(visibleCount);
  emptyState.hidden = visibleCount !== 0;
}
```

Create filter buttons from the rendered industry sections, update `aria-pressed`, run filtering on search `input`, and make the clear button restore an empty query plus the “全部” industry.

- [ ] **Step 4: Verify exact source coverage and link validity**

Run a Node script that recursively reads one directory level under `stocks`, extracts every `.stock-card` `href`, decodes it, and asserts set equality with the actual stock HTML paths. It must also assert unique links, valid filename parsing, matching industry/card totals, no remote assets, and no `javascript:` URLs.

```bash
node --input-type=module <<'NODE'
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = 'stocks';
const expected = [];
for (const industry of readdirSync(root).sort()) {
  const directory = join(root, industry);
  if (!statSync(directory).isDirectory()) continue;
  for (const file of readdirSync(directory).sort()) {
    if (file.endsWith('.html')) expected.push(`${industry}/${file}`);
  }
}

const html = readFileSync(join(root, 'index.html'), 'utf8');
const actual = [...html.matchAll(/<a class="stock-card"[^>]+href="([^"]+)"/g)]
  .map((match) => decodeURIComponent(match[1]));
assert.deepEqual(new Set(actual), new Set(expected));
assert.equal(actual.length, expected.length);
assert.equal(new Set(actual).size, actual.length);
assert.equal(actual.every((path) => /^.+\/HK_.+\(\d{5}\)\.html$/.test(path)), true);
assert.doesNotMatch(html, /(?:src|href)=["']https?:\/\//i);
assert.doesNotMatch(html, /javascript:/i);
console.log(`verified ${actual.length} stock links`);
NODE
```

Expected: `verified 613 stock links` with exit code 0.

- [ ] **Step 5: Run repository contract checks**

Run:

```bash
node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
```

Expected: all tests pass.

- [ ] **Step 6: Inspect desktop and mobile rendering**

Open `stocks/index.html` in a browser at 1440×900 and 390×844. Confirm the title, counts, search, filter controls, industry headings, cards, and empty state do not overlap or overflow. Search `00981`, select “信息技术”, clear the filters, and open the 中芯国际 card to verify navigation.

- [ ] **Step 7: Commit**

```bash
git add stocks/index.html
git commit -m "feat: add stocks research index"
```
