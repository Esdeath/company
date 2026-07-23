# Compact Company Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display each public library company entry as a single-line `公司名(股票代码)` label that truncates with an ellipsis when necessary.

**Architecture:** Keep the formatting local to `LibraryDirectory.vue` because it is presentation-only and has no API impact. Replace the two-row name/metadata markup with one strong label, then apply standard single-line overflow styling in the shared web stylesheet.

**Tech Stack:** Vue 3, Nuxt 4, TypeScript, CSS, Vitest, Vue Test Utils

## Global Constraints

- Render a company with a ticker as `公司名(股票代码)`.
- Render a company without a ticker as its company name only.
- Do not include the market in the company entry label.
- Keep the label on one line and truncate overflowing text with an ellipsis.
- Do not change document entries or the mobile directory trigger.

---

### Task 1: Compact Company Entry Label

**Files:**
- Modify: `apps/web/tests/LibraryDirectory.test.ts`
- Modify: `apps/web/app/components/LibraryDirectory.vue`
- Modify: `apps/web/app/assets/css/main.css`

**Interfaces:**
- Consumes: existing `Company` fields `name: string` and `ticker: string | null`
- Produces: `.company-entry__label` text formatted as `name(ticker)` or `name`

- [ ] **Step 1: Write the failing component test**

Replace the current long-name test with assertions covering label formatting and the dedicated truncation class:

```ts
it('formats company labels as name(ticker) and exposes a single-line truncation target', () => {
  const wrapper = mountDirectory(true)
  const labels = wrapper.findAll('.company-entry__label')

  expect(labels.map((label) => label.text())).toEqual(['泡泡玛特(09992)', '贵州茅台(600519)'])
  expect(wrapper.find('.company-entry small').exists()).toBe(false)
})
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts`

Expected: FAIL because `.company-entry__label` does not exist and the current entries still render market metadata.

- [ ] **Step 3: Implement the compact label**

Update the company copy markup in `LibraryDirectory.vue`:

```vue
<span class="company-entry__copy"><strong class="company-entry__label">
  {{ company.name }}{{ company.ticker ? `(${company.ticker})` : '' }}
</strong></span>
```

Update `main.css` so `.company-entry__label` stays on one line and truncates:

```css
.company-entry__label {
  min-width: 0;
  overflow: hidden;
  font-family: var(--font-display);
  font-size: 0.98rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

- [ ] **Step 4: Run focused and package verification**

Run: `corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts`

Expected: all tests in `LibraryDirectory.test.ts` pass.

Run: `corepack pnpm --filter @company/web check`

Expected: lint, typecheck, tests, and build all exit successfully.

- [ ] **Step 5: Review the diff**

Run: `git diff --check && git diff -- apps/web/app/components/LibraryDirectory.vue apps/web/app/assets/css/main.css apps/web/tests/LibraryDirectory.test.ts`

Expected: no whitespace errors; the diff is limited to the label markup, truncation styling, and component regression test.
