# Remove Admin Intro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant authenticated admin introduction banner so the company and document workspace follows the masthead directly.

**Architecture:** Keep the existing authentication and workspace data flow unchanged. Remove only the banner markup and selectors dedicated to it, normalize alert spacing for the new layout, and encode the banner's absence in the root app tests.

**Tech Stack:** Vue 3, TypeScript, CSS, Vitest, Vue Test Utils

## Global Constraints

- Keep authentication, the masthead, company picker, document workspace, public-site link, and footer unchanged.
- Preserve shared `h1`, `h2`, and `.eyebrow` styling used by the login page and workspace sections.
- Do not add dependencies or client state.

---

### Task 1: Remove the Authenticated Admin Introduction

**Files:**
- Modify: `apps/admin/tests/App.test.ts:88-126`
- Modify: `apps/admin/src/App.vue:335-340`
- Modify: `apps/admin/src/style.css:191-235`

**Interfaces:**
- Consumes: The existing authenticated `App` component mounted through Vue Test Utils.
- Produces: An authenticated workspace without `.page-intro` or its three copy strings, while the login page retains its own `h1` and `.eyebrow`.

- [x] **Step 1: Write the failing assertions**

Replace the authenticated workspace heading assertions with:

```ts
expect(wrapper.find('.page-intro').exists()).toBe(false)
expect(wrapper.text()).not.toContain('资料入库与整理')
expect(wrapper.text()).not.toContain('资料归档台')
expect(wrapper.text()).not.toContain('按公司收纳 HTML 与 Markdown 原文件，文件会直接出现在公开资料库中。')
```

After the login submission, replace the `h1` assertion with:

```ts
expect(wrapper.find('.page-intro').exists()).toBe(false)
expect(wrapper.text()).not.toContain('资料归档台')
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `pnpm --filter @company/admin test -- App.test.ts`

Expected: FAIL because `.page-intro` and its copy still render for an authenticated session.

- [x] **Step 3: Remove the banner and dedicated styles**

Delete this block from `apps/admin/src/App.vue`:

```vue
<header class="page-intro">
  <p class="eyebrow">资料入库与整理</p>
  <h1>资料归档台</h1>
  <p>按公司收纳 HTML 与 Markdown 原文件，文件会直接出现在公开资料库中。</p>
</header>
```

Delete the `.page-intro` and `.page-intro > p:last-child` rules from `apps/admin/src/style.css`. Change the shared alert margin from `-2rem 0 2rem` to `0 0 2rem` so alerts remain below the masthead spacing without relying on the deleted banner.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `pnpm --filter @company/admin test -- App.test.ts`

Expected: PASS with all tests in `App.test.ts` passing.

- [x] **Step 5: Run complete admin verification**

Run: `pnpm --filter @company/admin check`

Expected: lint, typecheck, unit tests, and production build all exit successfully.

- [x] **Step 6: Review the final diff**

Run: `git diff --check && git diff -- apps/admin/tests/App.test.ts apps/admin/src/App.vue apps/admin/src/style.css`

Expected: No whitespace errors; existing authentication edits remain intact and the new diff is limited to banner assertions, markup removal, dedicated CSS cleanup, and alert spacing.
