# Footer ICP Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a centered public-site footer link for “浙ICP备17053536号-2” that opens the MIIT filing site in a new tab.

**Architecture:** Keep the change inside the existing public Web app. Extend the current footer markup with one semantic anchor, convert the footer from a two-item flex row to a responsive three-position grid, and lock the link contract with an app-level component test.

**Tech Stack:** Nuxt 4, Vue 3, CSS Grid, Vitest, Vue Test Utils

## Global Constraints

- The visible link text is exactly `浙ICP备17053536号-2`.
- The destination is exactly `https://beian.miit.gov.cn/`.
- The link opens with `target="_blank"` and includes `rel="noopener noreferrer"`.
- Desktop layout is left brand, centered ICP link, and right reader note; narrow screens use one column without horizontal overflow.
- Do not modify Admin, API, `DocumentReader.vue`, iframe sandboxing, or deployment configuration.
- Use the repository's existing pnpm commands through `corepack pnpm`.

---

### Task 1: Add the responsive ICP footer link

**Files:**
- Modify: `apps/web/tests/app.test.ts`
- Modify: `apps/web/app/app.vue:181-184`
- Modify: `apps/web/app/assets/css/main.css:431-448`

**Interfaces:**
- Consumes: the existing `.footer` element rendered by `App` and the global `:where(a, button):focus-visible` rule.
- Produces: one `a.footer__icp` with the exact text and link attributes above; a three-position responsive footer layout.

- [ ] **Step 1: Write the failing link contract test**

Add this test after the existing brand-mark test in `apps/web/tests/app.test.ts`:

```ts
it('opens the ICP filing page from the footer in a new tab', async () => {
  const wrapper = await mountWorkspace()
  const filingLink = wrapper.get('footer.footer a.footer__icp')

  expect(filingLink.text()).toBe('浙ICP备17053536号-2')
  expect(filingLink.attributes()).toMatchObject({
    href: 'https://beian.miit.gov.cn/',
    target: '_blank',
    rel: 'noopener noreferrer',
  })
})
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/app.test.ts
```

Expected: FAIL because `footer.footer a.footer__icp` does not exist.

- [ ] **Step 3: Add the semantic footer link**

Replace the footer in `apps/web/app/app.vue` with:

```vue
<footer class="footer">
  <p>企业研究资料库</p>
  <a
    class="footer__icp"
    href="https://beian.miit.gov.cn/"
    target="_blank"
    rel="noopener noreferrer"
  >浙ICP备17053536号-2</a>
  <p>HTML 与 Markdown 资料独立阅读</p>
</footer>
```

- [ ] **Step 4: Convert the footer to a responsive centered grid**

Replace the current footer rules in `apps/web/app/assets/css/main.css` with:

```css
.footer {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  gap: 0.5rem 1rem;
  padding-block: 1.1rem;
  border-top: 1px solid var(--line);
}

.footer p {
  margin: 0;
}

.footer > p:last-child {
  justify-self: end;
  text-align: right;
}

.footer__icp {
  min-width: 0;
  justify-self: center;
  color: inherit;
  overflow-wrap: anywhere;
  text-align: center;
  text-underline-offset: 0.2em;
}

.footer__icp:hover {
  color: var(--green);
}
```

At the start of the existing `@media (min-width: 64rem)` block, add:

```css
.footer {
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/app.test.ts
```

Expected: the app test file passes, including the new ICP link test.

- [ ] **Step 6: Run the complete Web check**

Run:

```bash
corepack pnpm --filter @company/web check
```

Expected: lint, typecheck, all Web tests, and production build pass.

- [ ] **Step 7: Verify responsive layout in a browser**

Run the Web dev server and inspect 320x800 and 1280x800 viewports. At 320px, confirm the three footer items form one column, the ICP link is centered, and `document.documentElement.scrollWidth === window.innerWidth`. At 1280px, confirm the footer has three grid columns and the ICP link's center matches the footer container center within one pixel.

- [ ] **Step 8: Commit the implementation**

```bash
git add apps/web/tests/app.test.ts apps/web/app/app.vue apps/web/app/assets/css/main.css
git commit -m "feat: add ICP footer link"
```
