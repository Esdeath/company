# Sticky Library Directory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the complete desktop library directory visible while the article and comments scroll normally.

**Architecture:** Move desktop sticky positioning from the directory content to its grid-column shell so the entire sidebar owns viewport positioning. Preserve the directory's internal vertical overflow, and use root-level horizontal clipping that does not create a competing scroll container.

**Tech Stack:** Nuxt 4, Vue 3, CSS, Vitest

## Global Constraints

- Apply sticky sidebar behavior only at the existing `64rem` desktop breakpoint.
- Preserve the existing mobile directory drawer behavior.
- Preserve natural page flow for the article and comments.
- Do not add dependencies or change component markup.

---

### Task 1: Fix Desktop Directory Scrolling

**Files:**
- Modify: `apps/web/tests/layout.test.ts:37`
- Modify: `apps/web/app/assets/css/main.css:34`
- Modify: `apps/web/app/assets/css/main.css:499`

**Interfaces:**
- Consumes: Existing `.library-directory-shell` and `.library-directory` elements rendered by `LibraryDirectory.vue`.
- Produces: Desktop CSS in which the shell is sticky and the directory content scrolls within the available viewport height.

- [ ] **Step 1: Write the failing layout test**

Replace the existing sticky-directory test with assertions that assign sticky positioning and the viewport height bound to the shell:

```ts
it('keeps the desktop directory fixed while the article scrolls', () => {
  expect(rule('html,\nbody')).toContain('overflow-x: clip')
  expect(rule('.library-workspace')).toContain('min-width: 0')
  expect(rule('.reading-column')).toContain('min-width: 0')
  expect(rule('.library-directory-shell')).toContain('position: sticky')
  expect(rule('.library-directory-shell')).toContain('top: 1.5rem')
  expect(rule('.library-directory-shell')).toContain('max-height: calc(100svh - 3rem)')
  expect(rule('.library-directory')).not.toContain('position: sticky')
  expect(rule('.library-directory')).toContain('overflow-y: auto')
  expect(css).not.toMatch(/font-size:\s*[^;]*(vw|svw)/)
  const letterSpacingValues = [...css.matchAll(/letter-spacing:\s*([^;}]+)/g)]
    .map((match) => match[1]?.trim())
  expect(new Set(letterSpacingValues)).toEqual(new Set(['0']))
})
```

- [ ] **Step 2: Run the focused test and verify the red state**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/layout.test.ts
```

Expected: FAIL because the root still uses `overflow-x: hidden`, `.library-directory-shell` is not sticky, and `.library-directory` still owns sticky positioning.

- [ ] **Step 3: Implement the minimal desktop CSS change**

Change the root overflow protection:

```css
html,
body {
  overflow-x: clip;
}
```

At the desktop breakpoint, move the sticky and height rules to the shell:

```css
.library-directory-shell {
  position: sticky;
  top: 1.5rem;
  grid-column: 1;
  max-height: calc(100svh - 3rem);
}

.library-directory {
  position: static;
  z-index: auto;
  inset: auto;
  display: block;
  width: auto;
  max-height: calc(100svh - 3rem);
  padding: 0;
  overflow-y: auto;
  border-right: 0;
  background: transparent;
  box-shadow: none;
}
```

- [ ] **Step 4: Run the focused test and verify the green state**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/layout.test.ts
```

Expected: `5 passed`.

- [ ] **Step 5: Run the complete Web verification**

Run:

```bash
corepack pnpm --filter @company/web check
```

Expected: lint, typecheck, all Vitest files, and the Nuxt production build pass.

- [ ] **Step 6: Verify responsive behavior in a browser**

Start the existing Web development server and confirm at a desktop viewport that the left directory remains at `1.5rem` from the viewport top while scrolling through an article. Confirm below `64rem` that the directory still opens and closes as a drawer.

- [ ] **Step 7: Commit the implementation**

```bash
git add apps/web/tests/layout.test.ts apps/web/app/assets/css/main.css
git commit -m "fix(web): keep library directory visible"
```
