# Article Flow Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each article expand to its real rendered height so the page reaches comments only after the complete article body.

**Architecture:** Keep content inside the existing iframe, add only `allow-same-origin`, and let `DocumentReader` synchronize the iframe element height from the loaded document. Restore natural outer-page flow so the article, comments, and footer form one vertical scroll sequence while the company directory remains viewport-bounded and sticky.

**Tech Stack:** Nuxt 4, Vue 3, TypeScript, Vitest, Vue Test Utils, CSS, Playwright for final browser verification.

## Global Constraints

- The iframe sandbox must be exactly `allow-same-origin`; do not add scripts, forms, popups, downloads, or navigation permissions.
- The parent may read layout dimensions only; it must not copy, rewrite, or render article HTML outside the iframe.
- HTML and Markdown continue to use the same `DocumentReader` component.
- A measurement failure must retain a usable fallback reader height.
- Switching documents, retrying, or unmounting must disconnect observers and prevent stale measurements.
- Comments remain rendered by the Nuxt parent after `DocumentReader`; comment APIs and behavior are unchanged.
- Desktop and 320px mobile layouts must have one page-level vertical reading flow and no horizontal overflow.

---

### Task 1: Isolate and Test Frame Height Measurement

**Files:**
- Create: `apps/web/app/utils/frameHeight.ts`
- Create: `apps/web/tests/frameHeight.test.ts`

**Interfaces:**
- Produces: `FRAME_FALLBACK_HEIGHT: string`
- Produces: `readFrameContentHeight(frame: HTMLIFrameElement): number | null`
- `readFrameContentHeight` returns the positive, finite ceiling of the largest root/body `scrollHeight` or `offsetHeight`; it returns `null` when access fails or no positive size exists.

- [ ] **Step 1: Write the failing measurement tests**

```ts
import { describe, expect, it } from 'vitest'

import {
  FRAME_FALLBACK_HEIGHT,
  readFrameContentHeight,
} from '../app/utils/frameHeight'

function frameWith(root: Partial<HTMLElement>, body: Partial<HTMLElement> | null) {
  return {
    contentDocument: {
      documentElement: root,
      body,
    },
  } as unknown as HTMLIFrameElement
}

describe('iframe content height', () => {
  it('uses the largest root or body layout extent and rounds upward', () => {
    const frame = frameWith(
      { scrollHeight: 1400, offsetHeight: 1390 },
      { scrollHeight: 1450.2, offsetHeight: 1420 },
    )

    expect(readFrameContentHeight(frame)).toBe(1451)
    expect(FRAME_FALLBACK_HEIGHT).toBe('clamp(32rem, 72svh, 58rem)')
  })

  it('returns null for inaccessible or invalid documents', () => {
    const inaccessible = {} as HTMLIFrameElement
    Object.defineProperty(inaccessible, 'contentDocument', {
      get: () => { throw new DOMException('blocked') },
    })

    expect(readFrameContentHeight(inaccessible)).toBeNull()
    expect(readFrameContentHeight(frameWith({ scrollHeight: 0, offsetHeight: 0 }, null))).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test and verify the missing module failure**

Run: `corepack pnpm --filter @company/web exec vitest run tests/frameHeight.test.ts`

Expected: FAIL because `../app/utils/frameHeight` does not exist.

- [ ] **Step 3: Implement the pure measurement helper**

```ts
export const FRAME_FALLBACK_HEIGHT = 'clamp(32rem, 72svh, 58rem)'

export function readFrameContentHeight(frame: HTMLIFrameElement): number | null {
  try {
    const frameDocument = frame.contentDocument
    const root = frameDocument?.documentElement
    if (!root) return null
    const body = frameDocument.body
    const values = [
      root.scrollHeight,
      root.offsetHeight,
      body?.scrollHeight ?? 0,
      body?.offsetHeight ?? 0,
    ]
    const height = Math.max(...values)
    return Number.isFinite(height) && height > 0 ? Math.ceil(height) : null
  } catch {
    return null
  }
}
```

- [ ] **Step 4: Run the focused test**

Run: `corepack pnpm --filter @company/web exec vitest run tests/frameHeight.test.ts`

Expected: 1 file and 2 tests pass.

- [ ] **Step 5: Commit the tested helper**

```bash
git add apps/web/app/utils/frameHeight.ts apps/web/tests/frameHeight.test.ts
git commit -m "test(web): define article frame height measurement"
```

---

### Task 2: Synchronize DocumentReader With Article Height

**Files:**
- Modify: `apps/web/app/components/DocumentReader.vue`
- Modify: `apps/web/tests/DocumentReader.test.ts`

**Interfaces:**
- Consumes: `FRAME_FALLBACK_HEIGHT` and `readFrameContentHeight(frame)` from Task 1.
- Produces: iframe inline `height` that begins at `FRAME_FALLBACK_HEIGHT` and updates to `${measuredHeight}px`.
- Produces: one `ResizeObserver` bound to the current iframe document root/body and disconnected on every lifecycle boundary.

- [ ] **Step 1: Change the component test to require the new sandbox and initial height**

Replace the existing sandbox assertion and add the height assertion:

```ts
expect(frame.attributes('sandbox')).toBe('allow-same-origin')
expect(frame.attributes('style')).toContain('height: clamp(32rem, 72svh, 58rem)')
```

- [ ] **Step 2: Add a failing observer-driven height test**

Add a test-local observer fake that records its callback, observed nodes, and `disconnect` calls. Stub `ResizeObserver` and `requestAnimationFrame`, then mount the reader, define the iframe `contentDocument` with root/body heights, and trigger `load`:

```ts
it('fits the frame to its document and follows later size changes', async () => {
  const callbacks: ResizeObserverCallback[] = []
  const disconnect = vi.fn()
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) { callbacks.push(callback) }
    observe = vi.fn()
    disconnect = disconnect
  })
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', vi.fn())
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))

  const wrapper = mount(DocumentReader, {
    props: { document: DOCUMENT, loading: false, error: null },
  })
  await flushPromises()
  const frame = wrapper.get('iframe')
  const root = { scrollHeight: 1800, offsetHeight: 1750 }
  const body = { scrollHeight: 1900, offsetHeight: 1850 }
  Object.defineProperty(frame.element, 'contentDocument', {
    configurable: true,
    value: { documentElement: root, body },
  })

  await frame.trigger('load')
  expect(frame.attributes('style')).toContain('height: 1900px')

  body.scrollHeight = 2400
  callbacks[0]?.([], {} as ResizeObserver)
  await wrapper.vm.$nextTick()
  expect(frame.attributes('style')).toContain('height: 2400px')

  await wrapper.setProps({ document: SECOND_DOCUMENT })
  expect(disconnect).toHaveBeenCalledOnce()
})
```

- [ ] **Step 3: Run DocumentReader tests and verify failure**

Run: `corepack pnpm --filter @company/web exec vitest run tests/DocumentReader.test.ts`

Expected: FAIL because sandbox is still empty and no height observer updates the iframe.

- [ ] **Step 4: Implement generation-safe frame measurement**

Import `nextTick`, `FRAME_FALLBACK_HEIGHT`, and `readFrameContentHeight`, then add this lifecycle-owned state:

```ts
const frameHeight = ref(FRAME_FALLBACK_HEIGHT)
let frameResizeObserver: ResizeObserver | null = null
let frameMeasureRequest: number | null = null

function clearFrameMeasurement() {
  frameResizeObserver?.disconnect()
  frameResizeObserver = null
  if (frameMeasureRequest !== null) cancelAnimationFrame(frameMeasureRequest)
  frameMeasureRequest = null
  frameHeight.value = FRAME_FALLBACK_HEIGHT
}

function scheduleFrameMeasurement(frame: HTMLIFrameElement, generation: number) {
  if (frameMeasureRequest !== null) cancelAnimationFrame(frameMeasureRequest)
  frameMeasureRequest = requestAnimationFrame(() => {
    frameMeasureRequest = null
    if (generation !== requestGeneration || !frame.isConnected) return
    const measuredHeight = readFrameContentHeight(frame)
    if (measuredHeight !== null) frameHeight.value = `${measuredHeight}px`
  })
}

function observeFrameSize(frame: HTMLIFrameElement, generation: number) {
  const frameDocument = frame.contentDocument
  if (!frameDocument?.documentElement) return
  const Observer = frame.contentWindow?.ResizeObserver ?? globalThis.ResizeObserver
  frameResizeObserver = new Observer(() => scheduleFrameMeasurement(frame, generation))
  frameResizeObserver.observe(frameDocument.documentElement)
  if (frameDocument.body) frameResizeObserver.observe(frameDocument.body)
  scheduleFrameMeasurement(frame, generation)
}
```

Call `clearFrameMeasurement()` at the start of `probeContent`, in `handleFrameError`, and in `onBeforeUnmount`. Replace `handleFrameLoad` with an async handler that validates the generation before and after rendering:

```ts
async function handleFrameLoad(event: Event) {
  const frame = event.currentTarget as HTMLIFrameElement
  const generation = iframeEventGeneration(event)
  if (generation !== requestGeneration || contentState.value !== 'frame-loading') return

  contentState.value = 'ready'
  await nextTick()
  if (generation !== requestGeneration || !frame.isConnected) return
  observeFrameSize(frame, generation)
}
```

Bind `:style="{ height: frameHeight }"` and set `sandbox="allow-same-origin"` on the iframe.

- [ ] **Step 5: Run focused tests and type checking**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/frameHeight.test.ts tests/DocumentReader.test.ts
corepack pnpm --filter @company/web typecheck
```

Expected: both test files pass and Nuxt typecheck exits 0.

- [ ] **Step 6: Commit the reader behavior**

```bash
git add apps/web/app/components/DocumentReader.vue apps/web/tests/DocumentReader.test.ts
git commit -m "feat(web): expand reader to full article height"
```

---

### Task 3: Restore Natural Page Flow and Update Contracts

**Files:**
- Modify: `apps/web/app/assets/css/main.css`
- Modify: `apps/web/tests/layout.test.ts`
- Modify: `tests/docs.test.mjs`
- Modify: `doc/PRODUCT_UI.md`
- Modify: `doc/BACKEND.md`
- Modify: `doc/DEVELOPMENT.md`

**Interfaces:**
- Consumes: the measured iframe height from Task 2.
- Produces: one outer document scroll flow ordered as full article, comments, then footer.
- Produces: documentation and contract tests that specify `sandbox="allow-same-origin"` with all other permissions absent.

- [ ] **Step 1: Write failing layout expectations**

Update the first layout test to require natural page height:

```ts
expect(rule('.site-shell')).toContain('min-height: 100svh')
expect(rule('.site-shell')).not.toMatch(/(?:^|\n)\s*height:\s*100svh/)
expect(rule('.library-workspace')).not.toContain('height: 100%')
expect(rule('.document-reader')).toContain('min-height: clamp(32rem, 72svh, 58rem)')
expect(rule('.document-reader')).not.toMatch(/(?:^|\n)\s*height:\s*100%/)
expect(app).toMatch(/class="reading-column"[\s\S]*<DocumentReader[\s\S]*<CommentSection/)
```

Change the directory expectation to:

```ts
expect(rule('.library-directory')).toContain('max-height: calc(100svh - 3rem)')
```

- [ ] **Step 2: Update documentation contract tests before prose**

In `tests/docs.test.mjs`, require:

```js
assert.match(productUi, /<iframe sandbox="allow-same-origin"><\/iframe>/);
assert.match(productUi, /allow-same-origin[^。]+不允许[^。]+脚本/);
```

Replace the implemented behavior phrase `空 \`sandbox\` iframe` with `仅允许同源测量的 \`sandbox\` iframe`.

- [ ] **Step 3: Run tests and verify the old layout/docs fail**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/layout.test.ts
node --test tests/docs.test.mjs
```

Expected: layout assertions fail on fixed viewport CSS and docs assertions fail on the empty sandbox wording.

- [ ] **Step 4: Implement natural page flow CSS**

Apply these layout rules while retaining existing colors, typography, comment styles, and footer grid:

```css
.site-shell {
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-height: 100svh;
}

.library-main {
  min-width: 0;
  padding-block: clamp(1.75rem, 5vw, 3.5rem) 2.5rem;
}

.library-workspace {
  display: grid;
  min-width: 0;
  gap: 1.5rem;
  align-items: start;
}

.document-reader {
  position: relative;
  min-height: clamp(32rem, 72svh, 58rem);
  overflow: hidden;
  border-top: 0.18rem solid var(--red);
  background: var(--paper);
}

.document-frame {
  display: block;
  width: 100%;
  min-height: clamp(32rem, 72svh, 58rem);
  border: 0;
  background: var(--paper);
}
```

For desktop restore `.library-directory { top: 1.5rem; max-height: calc(100svh - 3rem); }` and remove fixed-row/min-height rules that belonged to the viewport-filling workspace.

- [ ] **Step 5: Update current documentation**

Document these exact behaviors:

- `doc/PRODUCT_UI.md`: iframe automatically matches the rendered article height; comments follow the complete article; sandbox is `allow-same-origin` only and the parent reads dimensions only.
- `doc/BACKEND.md`: the public reader uses `allow-same-origin` solely for same-origin height measurement; content delivery and storage do not change.
- `doc/DEVELOPMENT.md`: replace the empty-sandbox project boundary with the new restricted same-origin measurement boundary.

- [ ] **Step 6: Run focused and complete repository checks**

Run:

```bash
corepack pnpm --filter @company/web check
node --test tests/docs.test.mjs tests/prototype.test.mjs tests/scaffold.test.mjs
make check
```

Expected: Web lint/typecheck/tests/build pass, root contract tests pass, and the final full check exits 0.

- [ ] **Step 7: Verify real scrolling in two browser viewports**

Start Web with mocked API responses or the local stack, and use a long same-origin article in Playwright at `320x800` and `1280x900`. Assert:

```ts
const metrics = await page.evaluate(() => {
  const frame = document.querySelector('.document-frame')!.getBoundingClientRect()
  const comments = document.querySelector('.comment-section')!.getBoundingClientRect()
  return {
    frameBottom: frame.bottom + scrollY,
    commentTop: comments.top + scrollY,
    viewportHeight: innerHeight,
    hasHorizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  }
})

expect(metrics.commentTop).toBeGreaterThan(metrics.viewportHeight)
expect(metrics.frameBottom).toBeLessThanOrEqual(metrics.commentTop + 1)
expect(metrics.hasHorizontalOverflow).toBe(false)
await page.locator('.comment-section').scrollIntoViewIfNeeded()
await expect(page.locator('.comment-section')).toBeInViewport()
```

Before scrolling, require `commentTop > window.innerHeight`; after `commentSection.scrollIntoViewIfNeeded()`, require the comment section to be in the viewport and the footer to remain below it. Capture one mobile and one desktop full-page screenshot and inspect both for nested vertical scrollbars, overlap, and blank stretching.

- [ ] **Step 8: Commit layout and documentation**

```bash
git add apps/web/app/assets/css/main.css apps/web/tests/layout.test.ts tests/docs.test.mjs doc/PRODUCT_UI.md doc/BACKEND.md doc/DEVELOPMENT.md
git commit -m "fix(web): place comments after complete article"
```

---

### Task 4: Final Diff and Security Review

**Files:**
- Review only: all files changed in Tasks 1-3

**Interfaces:**
- Consumes: the complete implementation.
- Produces: evidence that the iframe gained no capability beyond same-origin measurement and that all lifecycle cleanup is complete.

- [ ] **Step 1: Inspect the complete diff**

Run:

```bash
git diff HEAD~3 -- apps/web/app apps/web/tests tests/docs.test.mjs doc/PRODUCT_UI.md doc/BACKEND.md doc/DEVELOPMENT.md
rg -n 'sandbox=' apps/web doc tests
```

Expected: the public iframe contains only `allow-same-origin`; no `allow-scripts`, `allow-forms`, `allow-popups`, `allow-top-navigation`, or HTML-copying path appears.

- [ ] **Step 2: Re-run final verification from a clean process state**

Run:

```bash
make check
git diff --check
git status --short
```

Expected: all checks pass; `git diff --check` prints nothing; status contains no uncommitted implementation files.
