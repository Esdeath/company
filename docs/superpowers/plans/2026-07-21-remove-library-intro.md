# Remove Library Intro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant public-site introduction banner so the research workspace follows the masthead directly.

**Architecture:** Keep the existing page structure and data flow unchanged. Remove only the banner markup and selectors that exist solely to style it, then encode its absence in the root app test.

**Tech Stack:** Nuxt 4, Vue 3, TypeScript, CSS, Vitest, Vue Test Utils

## Global Constraints

- Keep the masthead, three-column research workspace, and footer unchanged.
- Preserve the existing `.library-main` responsive spacing.
- Do not add dependencies or client state.

---

### Task 1: Remove the Library Introduction Banner

**Files:**
- Modify: `apps/web/tests/app.test.ts:116`
- Modify: `apps/web/app/app.vue:149`
- Modify: `apps/web/app/assets/css/main.css:87`

**Interfaces:**
- Consumes: The existing root `App` component mounted through Vue Test Utils.
- Produces: A root page without `.library-intro`, `Public research desk`, or the explanatory sentence.

- [ ] **Step 1: Write the failing test**

Replace the H1 assertions in the immediate-reading test with assertions for the banner's absence:

```ts
expect(wrapper.find('.library-intro').exists()).toBe(false)
expect(wrapper.text()).not.toContain('Public research desk')
expect(wrapper.text()).not.toContain('按公司查找研究资料，在独立阅读页中连续阅读。')
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pnpm --filter @company/web test -- app.test.ts`

Expected: FAIL because `.library-intro` and its copy still render.

- [ ] **Step 3: Remove the banner markup and dedicated styles**

Delete this block from `apps/web/app/app.vue`:

```vue
<header class="library-intro">
  <div>
    <p class="eyebrow">Public research desk</p>
    <h1>企业研究资料库</h1>
  </div>
  <p>按公司查找研究资料，在独立阅读页中连续阅读。</p>
</header>
```

Delete the `.library-intro` and `h1` rules from `apps/web/app/assets/css/main.css`, remove `.eyebrow` from grouped selectors, and retain the shared `h2` heading rule:

```css
h2 {
  margin: 0;
  font-family: var(--font-display);
  text-wrap: balance;
}
```

Also delete the desktop `.library-intro` media-query rule.

- [ ] **Step 4: Verify the focused test passes**

Run: `pnpm --filter @company/web test -- app.test.ts`

Expected: PASS with all tests in `app.test.ts` passing.

- [ ] **Step 5: Run the complete web verification**

Run: `pnpm --filter @company/web check`

Expected: lint, typecheck, unit tests, and production build all exit successfully.

- [ ] **Step 6: Review the final diff**

Run: `git diff --check && git diff -- apps/web/tests/app.test.ts apps/web/app/app.vue apps/web/app/assets/css/main.css`

Expected: No whitespace errors; the diff contains only the test assertion, banner markup removal, and dedicated CSS cleanup.
