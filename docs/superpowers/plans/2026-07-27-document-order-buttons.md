# Document Order Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace whole-row document dragging with reliable one-position up and down buttons in the Admin document list.

**Architecture:** `DocumentList.vue` owns the local index calculation and emits the existing complete `reorder(documentIds)` event. `App.vue` keeps its current optimistic save, rollback, request-generation guard, and live feedback. No API, database, or Web production code changes.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest, Vue Test Utils, CSS.

## Global Constraints

- First item disables up; last item disables down; a single item disables both.
- Every effective click moves exactly one position and emits the complete document ID order.
- Busy, rename-pending, delete-pending, and reorder-pending states disable ordering.
- Buttons use visible `↑` and `↓` symbols plus document-specific accessible labels.
- Remove pointer dragging, row keyboard shortcuts, drag instructions, and drag-only styles.
- Preserve the existing reorder API, optimistic rollback behavior, Web order, and append-at-bottom upload behavior.
- Do not modify or revert unrelated worktree changes.

---

### Task 1: Replace Drag Events with Move Buttons

**Files:**
- Modify: `apps/admin/src/components/DocumentList.vue`
- Modify: `apps/admin/tests/DocumentList.test.ts`

**Interfaces:**
- Consumes: `documents: DocumentItem[]`, `busy?: boolean`, `pendingIds: string[]`, and `orderFeedback`.
- Produces: existing `reorder: [documentIds: string[]]` event.

- [ ] **Step 1: Replace pointer tests with failing button tests**

Keep the two-document fixture and add a third document. Assert the first row exposes:

```typescript
const firstUp = wrapper.get('button[aria-label="上移 第一份资料"]')
const firstDown = wrapper.get('button[aria-label="下移 第一份资料"]')

expect(firstUp.attributes('disabled')).toBeDefined()
expect(firstDown.attributes('disabled')).toBeUndefined()
```

Click `下移 第一份资料` and expect:

```typescript
expect(wrapper.emitted('reorder')).toEqual([
  [['document-2', 'document-1', 'document-3']],
])
```

Click `上移 第三份资料` and expect `['document-1', 'document-3', 'document-2']`. Add separate assertions for last-down disabled, single-item both disabled, and every ordering button disabled while `busy` is true. Retain the test proving rename and delete controls do not emit `reorder`.

- [ ] **Step 2: Run the focused component test and verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/DocumentList.test.ts
```

Expected: button locators are missing because the component still renders pointer-driven rows.

- [ ] **Step 3: Implement one-position ordering**

Remove `computed`, pointer refs/state, Pointer Event handlers, `moveDocument`, row `tabindex`, row pointer listeners, and the hidden drag instruction. Render documents directly:

```vue
<li v-for="(document, index) in documents" :key="document.id" class="document-row">
  <div class="document-row__heading">
    <span class="document-order-actions">
      <button
        class="document-order-button"
        type="button"
        :aria-label="`上移 ${document.title}`"
        :disabled="busy || index === 0"
        @click="move(document.id, -1)"
      >↑</button>
      <button
        class="document-order-button"
        type="button"
        :aria-label="`下移 ${document.title}`"
        :disabled="busy || index === documents.length - 1"
        @click="move(document.id, 1)"
      >↓</button>
    </span>
```

Implement:

```typescript
function move(documentId: string, offset: -1 | 1) {
  if (props.busy) return
  const currentIndex = props.documents.findIndex((document) => document.id === documentId)
  const nextIndex = currentIndex + offset
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= props.documents.length) return
  const documentIds = props.documents.map((document) => document.id)
  ;[documentIds[currentIndex], documentIds[nextIndex]] = [
    documentIds[nextIndex]!,
    documentIds[currentIndex]!,
  ]
  statusMessage.value = `已移到第 ${nextIndex + 1} 项，正在保存`
  emit('reorder', documentIds)
}
```

Keep the `orderFeedback` watcher and polite status region so `App.vue` can announce success or rollback.

- [ ] **Step 4: Run the component test and verify GREEN**

Run the command from Step 2. Expected: all component ordering tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add apps/admin/src/components/DocumentList.vue apps/admin/tests/DocumentList.test.ts
git commit -m "feat(admin): reorder documents with buttons"
```

### Task 2: Remove Drag Styling and Verify Layout

**Files:**
- Modify: `apps/admin/src/style.css`
- Modify: `apps/admin/tests/style.test.ts`

**Interfaces:**
- Consumes: `.document-order-actions` markup from Task 1.
- Produces: stable compact controls on mobile and desktop without drag cursors or layout shifts.

- [ ] **Step 1: Write failing style contract tests**

Replace the drag-state assertions with:

```typescript
expect(stylesheet).toMatch(/\.document-order-actions[\s\S]*?display:\s*inline-flex/)
expect(stylesheet).toMatch(/\.document-order-button[\s\S]*?inline-size:/)
expect(stylesheet).not.toContain('.document-row--dragging')
expect(stylesheet).not.toContain('cursor: grab')
expect(stylesheet).not.toContain('touch-action: none')
```

- [ ] **Step 2: Run style tests and verify RED**

```bash
corepack pnpm --filter @company/admin exec vitest run tests/style.test.ts
```

Expected: order button selectors are missing and old drag selectors remain.

- [ ] **Step 3: Add compact button styles and delete drag styles**

Delete `.document-row--dragging`, `.document-row--busy`, row focus, grab cursor, `touch-action`, and drag-only action cursor rules. Add stable dimensions:

```css
.document-order-actions {
  display: inline-flex;
  flex: none;
  gap: 0.25rem;
}

.document-order-button {
  display: inline-grid;
  inline-size: 1.75rem;
  block-size: 1.75rem;
  place-items: center;
  padding: 0;
  border: 1px solid #9eb0a6;
  border-radius: 0.15rem;
  color: var(--green);
  background: var(--paper);
  line-height: 1;
}
```

Give enabled buttons a green hover border and keep the existing global focus-visible outline and disabled opacity.

- [ ] **Step 4: Run Admin complete verification**

```bash
corepack pnpm --filter @company/admin check
git diff --check
```

Expected: lint, typecheck, all Admin tests, build, and diff check pass.

- [ ] **Step 5: Verify desktop and mobile layout**

Run the Admin dev server, open the populated management screen, and inspect desktop plus 390px mobile viewports. Confirm the buttons do not overlap the format badge, title, rename input, save, or delete controls. Confirm first/last disabled states and one valid click updates order.

- [ ] **Step 6: Commit Task 2**

```bash
git add apps/admin/src/style.css apps/admin/tests/style.test.ts
git commit -m "style(admin): replace drag feedback with order controls"
```

### Task 3: Final Regression Verification

**Files:**
- Verify only; no planned production changes.

**Interfaces:**
- Confirms existing `App.vue` reorder persistence and all cross-project contracts remain green.

- [ ] **Step 1: Run full project checks**

```bash
make check
```

Expected: root contracts, Web check, Admin check, API lint/format/mypy/pytest all exit zero.

- [ ] **Step 2: Review final diff and history**

```bash
git diff --check
git status --short
git log --oneline -5
```

Expected: no uncommitted implementation files and only the intended Admin interaction replacement commits follow the approved design.
