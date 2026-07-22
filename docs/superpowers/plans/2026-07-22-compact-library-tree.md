# Compact Library Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the separate company and document directories with one accessible two-level library tree that leaves more desktop width for the reader and uses one coherent mobile drawer flow.

**Architecture:** A new presentational `LibraryDirectory.vue` owns tree rendering and drawer accessibility while `app.vue` continues to own API requests, request-generation guards, selected IDs, errors, and the reader. The directory consumes the current company's document array, emits company/document selections, and renders only the selected company's second level, so the existing one-company-at-a-time data flow remains unchanged.

**Tech Stack:** Nuxt 4.4.8, Vue 3.5.40, TypeScript 5.9.3, Vitest 4.1.10, Vue Test Utils 2.4.11, CSS Grid

## Global Constraints

- Node is `24.18.0`, pnpm is `10.34.5`, and pnpm commands use `corepack pnpm`.
- Only the current company may be expanded.
- On mobile, selecting a company keeps the drawer open; selecting a document closes it and restores focus to the trigger.
- Keep request-generation guards, error retries, and the empty `sandbox` iframe behavior unchanged.
- Use native buttons and nested lists; do not implement an ARIA tree widget.
- At `64rem` and above use a two-column directory/reader layout with an approximately `17rem` sticky directory.
- Below `64rem`, use the existing accessible drawer pattern and do not reserve a permanent directory column.
- Do not change API routes, content types, Admin UI, or document rendering.
- Do not include the currently uncommitted `apps/web/Dockerfile` and `tests/scaffold.test.mjs` icon-delivery fix in these task commits.

---

### Task 1: Build the unified library directory component

**Files:**
- Create: `apps/web/app/components/LibraryDirectory.vue`
- Create: `apps/web/tests/LibraryDirectory.test.ts`

**Interfaces:**
- Consumes props `companies: Company[]`, `documents: DocumentItem[]`, `selectedCompanyId: string | null`, `selectedDocumentId: string | null`, `companiesLoading: boolean`, and `documentsLoading: boolean`.
- Produces events `select-company: [companyId: string]` and `select-document: [documentId: string]`.
- Exposes stable selectors `button[name="open-library-directory"]`, `button[name="close-library-directory"]`, `[data-company-id]`, and `[data-document-id]` for integration tests.

- [ ] **Step 1: Write focused component tests first**

Create `apps/web/tests/LibraryDirectory.test.ts` with real props and a controllable `matchMedia` stub:

```ts
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import LibraryDirectory from '../app/components/LibraryDirectory.vue'
import type { Company, DocumentItem } from '../app/types/content'

const companies: Company[] = [
  { id: 'company-1', name: '泡泡玛特', ticker: '09992', market: 'HK', created_at: '2026-07-19T08:00:00Z' },
  { id: 'company-2', name: '贵州茅台', ticker: '600519', market: 'A股', created_at: '2026-07-20T08:00:00Z' },
]

const documents: DocumentItem[] = [
  {
    id: 'document-1',
    company_id: 'company-2',
    title: '贵州茅台财报',
    format: 'html',
    original_filename: 'moutai.html',
    uploaded_at: '2026-07-21T08:00:00Z',
    content_url: '/api/v1/documents/document-1/content',
  },
  {
    id: 'document-2',
    company_id: 'company-2',
    title: '管理层访谈',
    format: 'markdown',
    original_filename: 'interview.md',
    uploaded_at: '2026-06-18T08:00:00Z',
    content_url: '/api/v1/documents/document-2/content',
  },
]

let changeListener: ((event: MediaQueryListEvent) => void) | undefined

function stubMediaQuery(matches: boolean) {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
    matches,
    addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      changeListener = listener
    }),
    removeEventListener: vi.fn(),
  }))
}

function mountDirectory(matches = false) {
  stubMediaQuery(matches)
  return mount(LibraryDirectory, {
    attachTo: document.body,
    props: {
      companies,
      documents,
      selectedCompanyId: 'company-2',
      selectedDocumentId: 'document-1',
      companiesLoading: false,
      documentsLoading: false,
    },
  })
}

describe('LibraryDirectory', () => {
  beforeEach(() => {
    changeListener = undefined
  })

  afterEach(() => {
    document.body.innerHTML = ''
    document.body.style.overflow = ''
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders one expanded company with a nested current document', () => {
    const wrapper = mountDirectory(true)
    const first = wrapper.get('[data-company-id="company-1"]')
    const second = wrapper.get('[data-company-id="company-2"]')

    expect(first.attributes('aria-expanded')).toBe('false')
    expect(second.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('.document-branch')).toHaveLength(1)
    expect(wrapper.get('[data-document-id="document-1"]').attributes('aria-current')).toBe('true')
    expect(wrapper.text()).toContain('贵州茅台财报')
  })

  it('keeps the mobile drawer open after selecting a company', async () => {
    const wrapper = mountDirectory()
    await wrapper.get('button[name="open-library-directory"]').trigger('click')
    await wrapper.get('[data-company-id="company-1"]').trigger('click')

    expect(wrapper.emitted('select-company')).toEqual([['company-1']])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(document.body.style.overflow).toBe('hidden')
  })

  it('closes the mobile drawer after selecting a document and restores focus', async () => {
    const wrapper = mountDirectory()
    const trigger = wrapper.get<HTMLButtonElement>('button[name="open-library-directory"]')
    await trigger.trigger('click')
    await wrapper.get('[data-document-id="document-2"]').trigger('click')
    await nextTick()

    expect(wrapper.emitted('select-document')).toEqual([['document-2']])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    expect(document.body.style.overflow).toBe('')
  })

  it('keeps close, company, and document buttons inside the mobile focus loop', async () => {
    const wrapper = mountDirectory()
    await wrapper.get('button[name="open-library-directory"]').trigger('click')
    const close = wrapper.get<HTMLButtonElement>('button[name="close-library-directory"]')
    const last = wrapper.get<HTMLButtonElement>('[data-document-id="document-2"]')

    close.element.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true }))
    expect(document.activeElement).toBe(last.element)

    last.element.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', cancelable: true }))
    expect(document.activeElement).toBe(close.element)
  })

  it('shows loading and empty document states under the selected company', async () => {
    const wrapper = mountDirectory(true)
    await wrapper.setProps({ documentsLoading: true, documents: [] })
    expect(wrapper.get('.document-branch').text()).toContain('资料目录读取中')

    await wrapper.setProps({ documentsLoading: false })
    expect(wrapper.get('.document-branch').text()).toContain('暂无资料')
  })
})
```

- [ ] **Step 2: Run the test and verify the component is missing**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts
```

Expected: FAIL because `../app/components/LibraryDirectory.vue` does not exist.

- [ ] **Step 3: Implement `LibraryDirectory.vue`**

Create `apps/web/app/components/LibraryDirectory.vue`. Reuse the body-lock, focus-loop, breakpoint, and date-formatting behavior from the two existing components, but use the following public contract and selection behavior:

```vue
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import type { Company, DocumentItem } from '../types/content'

const props = defineProps<{
  companies: Company[]
  documents: DocumentItem[]
  selectedCompanyId: string | null
  selectedDocumentId: string | null
  companiesLoading: boolean
  documentsLoading: boolean
}>()

const emit = defineEmits<{
  'select-company': [companyId: string]
  'select-document': [documentId: string]
}>()

const drawerOpen = ref(false)
const isDesktop = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const directory = ref<HTMLElement | null>(null)
let mediaQuery: MediaQueryList | null = null
let previousBodyOverflow = ''
let ownsBodyLock = false

const selectedCompany = computed(
  () => props.companies.find((company) => company.id === props.selectedCompanyId) ?? null,
)
const selectedDocument = computed(
  () => props.documents.find((document) => document.id === props.selectedDocumentId) ?? null,
)
const navigationVisible = computed(() => isDesktop.value || drawerOpen.value)
const triggerLabel = computed(() =>
  [selectedCompany.value?.name, selectedDocument.value?.title].filter(Boolean).join(' · ') || '浏览目录',
)

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
})

function formattedDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : dateFormatter.format(date)
}

function acquireBodyLock() {
  if (typeof document === 'undefined' || ownsBodyLock) return
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  ownsBodyLock = true
}

function releaseBodyLock() {
  if (typeof document === 'undefined' || !ownsBodyLock) return
  document.body.style.overflow = previousBodyOverflow
  ownsBodyLock = false
}

async function openDrawer() {
  drawerOpen.value = true
  if (!isDesktop.value) acquireBodyLock()
  await nextTick()
  closeButton.value?.focus()
}

async function closeDrawer(restoreFocus = true) {
  const wasOpen = drawerOpen.value
  drawerOpen.value = false
  releaseBodyLock()
  if (restoreFocus && wasOpen) {
    await nextTick()
    trigger.value?.focus()
  }
}

function selectCompany(companyId: string) {
  emit('select-company', companyId)
}

function selectDocument(documentId: string) {
  emit('select-document', documentId)
  void closeDrawer()
}

function focusableElements(): HTMLElement[] {
  if (!directory.value) return []
  return Array.from(directory.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => !element.hidden)
}

function handleKeydown(event: KeyboardEvent) {
  if (!drawerOpen.value || isDesktop.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    void closeDrawer()
    return
  }
  if (event.key !== 'Tab') return
  const focusable = focusableElements()
  const first = focusable[0]
  const last = focusable.at(-1)
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function handleBreakpoint(event: MediaQueryListEvent | MediaQueryList) {
  isDesktop.value = event.matches
  if (event.matches) void closeDrawer(false)
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  if (typeof window.matchMedia === 'function') {
    mediaQuery = window.matchMedia('(min-width: 64rem)')
    handleBreakpoint(mediaQuery)
    mediaQuery.addEventListener('change', handleBreakpoint)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  mediaQuery?.removeEventListener('change', handleBreakpoint)
  releaseBodyLock()
})
</script>
```

Use this template structure after the script:

```vue
<template>
  <section class="library-directory-shell">
    <button ref="trigger" class="library-drawer-trigger" name="open-library-directory"
      type="button" aria-haspopup="dialog" :aria-expanded="drawerOpen" @click="openDrawer">
      <span>浏览目录</span><strong>{{ triggerLabel }}</strong><span aria-hidden="true">→</span>
    </button>
    <div v-if="drawerOpen && !isDesktop" class="library-backdrop" aria-hidden="true"
      @click="closeDrawer()" />
    <aside v-show="navigationVisible" ref="directory" class="library-directory"
      :class="{ 'library-directory--drawer': drawerOpen && !isDesktop }"
      aria-label="公司与资料" :role="drawerOpen && !isDesktop ? 'dialog' : undefined"
      :aria-modal="drawerOpen && !isDesktop ? 'true' : undefined"
      aria-labelledby="library-directory-title" :inert="!navigationVisible">
      <header class="directory-heading">
        <div><p>Research library</p><h2 id="library-directory-title">公司与资料</h2></div>
        <button ref="closeButton" class="drawer-close" name="close-library-directory"
          type="button" aria-label="关闭公司与资料目录" @click="closeDrawer()">
          <span aria-hidden="true">×</span>
        </button>
      </header>
      <p v-if="companiesLoading" class="directory-note">正在读取公司目录…</p>
      <p v-else-if="companies.length === 0" class="directory-note">暂无公司</p>
      <nav v-else aria-label="选择公司与资料">
        <ul class="library-tree">
          <li v-for="company in companies" :key="company.id">
            <button class="company-entry"
              :class="{ 'company-entry--active': company.id === selectedCompanyId }"
              type="button" :data-company-id="company.id"
              :aria-expanded="company.id === selectedCompanyId"
              @click="selectCompany(company.id)">
              <span class="company-entry__toggle" aria-hidden="true">
                {{ company.id === selectedCompanyId ? '⌄' : '›' }}
              </span>
              <span class="company-entry__copy"><strong>{{ company.name }}</strong><small>
                {{ [company.ticker, company.market].filter(Boolean).join(' · ') || '公司研究' }}
              </small></span>
            </button>
            <div v-if="company.id === selectedCompanyId" class="document-branch">
              <p v-if="documentsLoading" class="directory-note">资料目录读取中…</p>
              <p v-else-if="documents.length === 0" class="directory-note">暂无资料</p>
              <ul v-else class="document-list">
                <li v-for="document in documents" :key="document.id">
                  <button class="document-entry"
                    :class="{ 'document-entry--active': document.id === selectedDocumentId }"
                    type="button" :data-document-id="document.id"
                    :aria-current="document.id === selectedDocumentId ? 'true' : undefined"
                    @click="selectDocument(document.id)">
                    <span class="document-entry__title">{{ document.title }}</span>
                    <span class="document-entry__meta"><span class="format-badge">
                      {{ document.format === 'markdown' ? 'MD' : 'HTML' }}
                    </span><time :datetime="document.uploaded_at">{{ formattedDate(document.uploaded_at) }}</time></span>
                  </button>
                </li>
              </ul>
            </div>
          </li>
        </ul>
      </nav>
    </aside>
  </section>
</template>
```

- [ ] **Step 4: Run the component tests and make them pass**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts
```

Expected: five tests pass with no warnings.

- [ ] **Step 5: Commit the isolated component**

```bash
git add apps/web/app/components/LibraryDirectory.vue apps/web/tests/LibraryDirectory.test.ts
git commit -m "feat: add unified library directory"
```

### Task 2: Integrate the tree and replace the three-column layout

**Files:**
- Modify: `apps/web/app/app.vue`
- Modify: `apps/web/app/assets/css/main.css`
- Modify: `apps/web/tests/app.test.ts`
- Delete: `apps/web/app/components/CompanyDirectory.vue`
- Delete: `apps/web/app/components/DocumentDirectory.vue`
- Delete: `apps/web/tests/CompanyDirectory.test.ts`

**Interfaces:**
- Consumes `LibraryDirectory` and its `select-company` / `select-document` events from Task 1.
- Preserves `selectCompany(companyId: string)` refresh behavior and direct assignment of `selectedDocumentId`.
- Produces a two-column desktop workspace and one mobile directory trigger.

- [ ] **Step 1: Change app integration tests first**

Update `apps/web/tests/app.test.ts` so all company/document selectors continue to use `[data-company-id]` and `[data-document-id]`, then replace the old mobile drawer expectations with:

```ts
it('keeps the unified drawer open for company selection and closes after document selection', async () => {
  vi.mocked(library.listDocuments)
    .mockResolvedValueOnce(companyOneDocuments)
    .mockResolvedValueOnce(companyTwoDocuments)
  const wrapper = await mountWorkspace(true)
  const trigger = wrapper.get('button[name="open-library-directory"]')

  await trigger.trigger('click')
  await wrapper.get('[data-company-id="company-2"]').trigger('click')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

  await flushPromises()
  await wrapper.get('[data-document-id="document-3"]').trigger('click')
  await nextTick()

  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(document.activeElement).toBe(trigger.element)
  expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-3/content')
})
```

Add a structural assertion to the immediate-reading test:

```ts
expect(wrapper.find('.library-directory').exists()).toBe(true)
expect(wrapper.find('.company-directory').exists()).toBe(false)
expect(wrapper.find('.document-directory').exists()).toBe(false)
expect(wrapper.findAll('.document-branch')).toHaveLength(1)
```

- [ ] **Step 2: Run app tests and verify the old integration fails**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/app.test.ts
```

Expected: FAIL because `app.vue` still renders separate directories and lacks `open-library-directory`.

- [ ] **Step 3: Replace the old component imports and template**

In `apps/web/app/app.vue`, replace the two old imports with:

```ts
import LibraryDirectory from './components/LibraryDirectory.vue'
```

Replace the two old directory components inside `.library-workspace` with:

```vue
<LibraryDirectory
  :companies="companies"
  :documents="documents"
  :selected-company-id="selectedCompanyId"
  :selected-document-id="selectedDocumentId"
  :companies-loading="companiesLoading"
  :documents-loading="documentsLoading"
  @select-company="selectCompany"
  @select-document="selectedDocumentId = $event"
/>
```

Do not change `refreshCompanies`, `refreshDocuments`, the selected-company watcher, request-generation checks, `retryReader`, or `DocumentReader` props.

- [ ] **Step 4: Replace directory CSS with one tree and two-column layout**

In `apps/web/app/assets/css/main.css`:

1. Rename the mobile shell/trigger/backdrop/directory selectors to `library-*`.
2. Keep stable trigger dimensions and change its middle copy to one ellipsized `strong` value.
3. Add `.library-tree`, `.company-entry__toggle`, `.company-entry__copy`, and `.document-branch` rules.
4. Scope the red active marker to `.document-entry--active::after`; the selected company uses green text only.
5. Remove `.document-directory`, `.document-directory__heading`, and `.directory-count` rules.
6. At `64rem`, use exactly two tracks:

```css
.library-workspace {
  grid-template-columns: minmax(15rem, 17rem) minmax(0, 1fr);
  gap: clamp(1.5rem, 3vw, 2.75rem);
}

.library-directory-shell {
  grid-column: 1;
}

.library-directory {
  position: sticky;
  top: 1.5rem;
  width: auto;
  max-height: calc(100svh - 3rem);
  padding: 0;
  overflow-y: auto;
  border-right: 0;
  background: transparent;
  box-shadow: none;
}

.document-reader {
  grid-column: 2;
}
```

Use these hierarchy rules as the baseline:

```css
.library-tree,
.document-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.company-entry {
  grid-template-columns: 0.85rem minmax(0, 1fr);
  align-items: center;
}

.company-entry__copy {
  display: grid;
  min-width: 0;
  gap: 0.35rem;
}

.company-entry__copy strong {
  font-family: var(--font-display);
  font-size: 0.98rem;
}

.document-branch {
  margin-inline-start: 0.85rem;
  padding-inline-start: 0.8rem;
  border-left: 1px solid #9eb0a6;
}

.document-branch .document-entry {
  padding-block: 0.85rem;
}
```

Delete the obsolete `@media (min-width: 48rem)` two-column intermediate directory layout. Below `64rem`, `.library-directory-shell` spans the available workspace width and the reader remains underneath the trigger.

- [ ] **Step 5: Delete old components and obsolete unit test**

Delete exactly:

```text
apps/web/app/components/CompanyDirectory.vue
apps/web/app/components/DocumentDirectory.vue
apps/web/tests/CompanyDirectory.test.ts
```

- [ ] **Step 6: Run focused and full Web checks**

Run:

```bash
corepack pnpm --filter @company/web exec vitest run tests/LibraryDirectory.test.ts tests/app.test.ts
corepack pnpm --filter @company/web check
```

Expected: all focused tests pass; lint, typecheck, all Vitest tests, and the production build exit 0.

- [ ] **Step 7: Verify all four responsive widths in a browser**

Start:

```bash
corepack pnpm --filter @company/web dev
```

Verify `http://127.0.0.1:3000/` at 320x800, 768x900, 1024x800, and 1280x800:

- 320 and 768 show one stable directory trigger above the reader, with no horizontal overflow.
- 1024 and 1280 show one approximately 17rem tree rail and one reader column.
- Only the selected company has a visible `.document-branch`.
- Selecting a company keeps the mobile drawer open; selecting a document closes it.
- The reader iframe remains sandboxed and gains width compared with the old 13.5rem + 16.5rem + reader layout.

- [ ] **Step 8: Commit the integration**

```bash
git add apps/web/app/app.vue apps/web/app/assets/css/main.css apps/web/tests/app.test.ts apps/web/app/components/CompanyDirectory.vue apps/web/app/components/DocumentDirectory.vue apps/web/tests/CompanyDirectory.test.ts
git commit -m "feat: merge company and document navigation"
```
