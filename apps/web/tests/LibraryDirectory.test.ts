import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import LibraryDirectory from '../app/components/LibraryDirectory.vue'
import type { Company, DocumentItem } from '../app/types/content'

const companies: Company[] = [
  { id: 'company-1', name: '泡泡玛特', ticker: '09992', market: 'HK', sort_order: 0, created_at: '2026-07-19T08:00:00Z' },
  { id: 'company-2', name: '贵州茅台', ticker: '600519', market: 'A股', sort_order: 1, created_at: '2026-07-20T08:00:00Z' },
]

const documents: DocumentItem[] = [
  {
    id: 'document-1',
    company_id: 'company-2',
    title: '贵州茅台财报',
    format: 'html',
    original_filename: 'moutai.html',
    sort_order: 0,
    uploaded_at: '2026-06-18T08:00:00Z',
    content_url: '/api/v1/documents/document-1/content',
  },
  {
    id: 'document-2',
    company_id: 'company-2',
    title: '管理层访谈',
    format: 'markdown',
    original_filename: 'interview.md',
    sort_order: 1,
    uploaded_at: '2026-07-21T08:00:00Z',
    content_url: '/api/v1/documents/document-2/content',
  },
]

type Unmountable = { unmount: () => void }

let changeListener: ((event: MediaQueryListEvent) => void) | undefined
const mountedWrappers: Unmountable[] = []

function stubMediaQuery(matches: boolean) {
  const addEventListener = vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
    changeListener = listener
  })
  const removeEventListener = vi.fn()
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches, addEventListener, removeEventListener }))
  return { addEventListener, removeEventListener }
}

function mountDirectory(matches = false) {
  stubMediaQuery(matches)
  const wrapper = mount(LibraryDirectory, {
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
  mountedWrappers.push(wrapper)
  return wrapper
}

function unmountTracked(wrapper: Unmountable) {
  wrapper.unmount()
  const index = mountedWrappers.indexOf(wrapper)
  if (index >= 0) mountedWrappers.splice(index, 1)
}

describe('LibraryDirectory', () => {
  beforeEach(() => {
    changeListener = undefined
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0).reverse()) wrapper.unmount()
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

  it('keeps the API document order even when upload timestamps disagree', () => {
    expectTypeOf<DocumentItem>().toHaveProperty('sort_order')
    const wrapper = mountDirectory(true)

    expect(documents.map((document) => document.sort_order)).toEqual([0, 1])
    expect(
      wrapper.findAll('[data-document-id]').map((entry) => entry.attributes('data-document-id')),
    ).toEqual(['document-1', 'document-2'])
  })

  it('renders document entries as title-only buttons', () => {
    const wrapper = mountDirectory(true)
    const entry = wrapper.get('[data-document-id="document-1"]')

    expect(entry.text()).toBe('贵州茅台财报')
    expect(entry.find('.document-entry__meta').exists()).toBe(false)
    expect(entry.find('time').exists()).toBe(false)
  })

  it('keeps document titles on one truncated line', () => {
    const stylesheet = readFileSync(resolve(process.cwd(), 'app/assets/css/main.css'), 'utf8')
    const titleRule = stylesheet.match(/\.document-entry__title\s*\{([^}]*)\}/)?.[1]

    expect(titleRule).toContain('white-space: nowrap')
    expect(titleRule).toContain('overflow: hidden')
    expect(titleRule).toContain('text-overflow: ellipsis')
  })

  it('formats company labels as name(ticker) and exposes a single-line truncation target', () => {
    const wrapper = mountDirectory(true)
    const labels = wrapper.findAll('.company-entry__label')

    expect(labels.map((label) => label.text())).toEqual(['泡泡玛特(09992)', '贵州茅台(600519)'])
    expect(wrapper.find('.company-entry small').exists()).toBe(false)
  })

  it('keeps company labels on one truncated line', () => {
    const stylesheet = readFileSync(resolve(process.cwd(), 'app/assets/css/main.css'), 'utf8')
    const labelRule = stylesheet.match(/\.company-entry__label\s*\{([^}]*)\}/)?.[1]

    expect(labelRule).toContain('white-space: nowrap')
    expect(labelRule).toContain('overflow: hidden')
    expect(labelRule).toContain('text-overflow: ellipsis')
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

  it('leaves unrelated body overflow untouched when unmounted without owning the lock', () => {
    document.body.style.overflow = 'clip'
    const wrapper = mountDirectory()

    unmountTracked(wrapper)

    expect(document.body.style.overflow).toBe('clip')
  })

  it('restores the previous body overflow when closed or unmounted after opening', async () => {
    document.body.style.overflow = 'clip'
    const closedWrapper = mountDirectory()

    await closedWrapper.get('button[name="open-library-directory"]').trigger('click')
    expect(document.body.style.overflow).toBe('hidden')
    await closedWrapper.get('button[name="close-library-directory"]').trigger('click')
    expect(document.body.style.overflow).toBe('clip')
    unmountTracked(closedWrapper)
    expect(document.body.style.overflow).toBe('clip')

    document.body.style.overflow = 'auto'
    const unmountedWrapper = mountDirectory()
    await unmountedWrapper.get('button[name="open-library-directory"]').trigger('click')
    unmountTracked(unmountedWrapper)

    expect(document.body.style.overflow).toBe('auto')
  })

  it('does not overwrite the saved body overflow on repeated open requests', async () => {
    document.body.style.overflow = 'scroll'
    const wrapper = mountDirectory()
    const trigger = wrapper.get('button[name="open-library-directory"]')

    await trigger.trigger('click')
    await trigger.trigger('click')
    await wrapper.get('button[name="close-library-directory"]').trigger('click')

    expect(document.body.style.overflow).toBe('scroll')
  })

  it('closes by Escape, backdrop, and close button while restoring the prior body overflow', async () => {
    document.body.style.overflow = 'clip'
    const wrapper = mountDirectory()
    const trigger = wrapper.get<HTMLButtonElement>('button[name="open-library-directory"]')

    await trigger.trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    expect(document.body.style.overflow).toBe('clip')

    await trigger.trigger('click')
    await wrapper.get('.library-backdrop').trigger('click')
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    await trigger.trigger('click')
    await wrapper.get('button[name="close-library-directory"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('closes and releases the body lock when the desktop breakpoint becomes active', async () => {
    const wrapper = mountDirectory()
    await wrapper.get('button[name="open-library-directory"]').trigger('click')
    changeListener?.({ matches: true } as MediaQueryListEvent)
    await nextTick()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.body.style.overflow).toBe('')
  })

  it('removes its global keydown and media-query listeners on unmount', () => {
    const addWindowListener = vi.spyOn(window, 'addEventListener')
    const removeWindowListener = vi.spyOn(window, 'removeEventListener')
    const media = stubMediaQuery(false)
    const wrapper = mount(LibraryDirectory, {
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
    mountedWrappers.push(wrapper)
    const keydownListener = addWindowListener.mock.calls.find(([type]) => type === 'keydown')?.[1]
    const mediaListener = media.addEventListener.mock.calls[0]?.[1]

    unmountTracked(wrapper)

    expect(keydownListener).toBeDefined()
    expect(removeWindowListener).toHaveBeenCalledWith('keydown', keydownListener)
    expect(mediaListener).toBeDefined()
    expect(media.removeEventListener).toHaveBeenCalledWith('change', mediaListener)
  })
})
