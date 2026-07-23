import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import App from '../app/app.vue'
import * as library from '../app/api/library'
import type { Company, DocumentItem } from '../app/types/content'

vi.mock('../app/api/library', () => ({
  listCompanies: vi.fn(),
  listDocuments: vi.fn(),
}))

const companies: Company[] = [
  {
    id: 'company-1',
    name: '山河研究',
    ticker: '600001',
    market: '上交所',
    created_at: '2026-07-19T08:00:00Z',
  },
  {
    id: 'company-2',
    name: '远望科技',
    ticker: null,
    market: null,
    created_at: '2026-07-20T08:00:00Z',
  },
]

const companyOneDocuments: DocumentItem[] = [
  {
    id: 'document-1',
    company_id: 'company-1',
    title: '年度报告',
    format: 'markdown',
    original_filename: 'annual.md',
    sort_order: 0,
    uploaded_at: '2026-07-20T08:00:00Z',
    content_url: '/api/v1/documents/document-1/content',
  },
  {
    id: 'document-2',
    company_id: 'company-1',
    title: '管理层访谈',
    format: 'html',
    original_filename: 'interview.html',
    sort_order: 1,
    uploaded_at: '2026-07-19T08:00:00Z',
    content_url: '/api/v1/documents/document-2/content',
  },
]

const companyTwoDocuments: DocumentItem[] = [
  {
    id: 'document-3',
    company_id: 'company-2',
    title: '产品札记',
    format: 'html',
    original_filename: 'product.html',
    sort_order: 0,
    uploaded_at: '2026-07-18T08:00:00Z',
    content_url: '/api/v1/documents/document-3/content',
  },
]

type Unmountable = { unmount: () => void }
const mountedWrappers: Unmountable[] = []

function track<T extends Unmountable>(wrapper: T): T {
  mountedWrappers.push(wrapper)
  return wrapper
}

function unmountTracked(wrapper: Unmountable) {
  wrapper.unmount()
  const index = mountedWrappers.indexOf(wrapper)
  if (index >= 0) mountedWrappers.splice(index, 1)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

async function mountWorkspace(attachToDocument = false) {
  const wrapper = track(mount(App, attachToDocument ? { attachTo: document.body } : undefined))
  await flushPromises()
  return wrapper
}

describe('公开资料阅读工作台', () => {
  beforeEach(() => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    vi.mocked(library.listCompanies).mockReset().mockResolvedValue(companies)
    vi.mocked(library.listDocuments).mockReset().mockImplementation(async (companyId) =>
      companyId === 'company-1' ? companyOneDocuments : companyTwoDocuments,
    )
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0).reverse()) wrapper.unmount()
    document.body.innerHTML = ''
    document.body.style.overflow = ''
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('selects the first company and document for immediate reading', async () => {
    const wrapper = await mountWorkspace()

    expect(library.listCompanies).toHaveBeenCalledOnce()
    expect(library.listDocuments).toHaveBeenCalledWith('company-1')
    expect(wrapper.find('.library-intro').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Public research desk')
    expect(wrapper.text()).not.toContain('按公司查找研究资料，在独立阅读页中连续阅读。')
    expect(wrapper.get('[data-company-id="company-1"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-document-id="document-1"]').attributes('aria-current')).toBe('true')
    expect(wrapper.find('.library-directory').exists()).toBe(true)
    expect(wrapper.find('.company-directory').exists()).toBe(false)
    expect(wrapper.find('.document-directory').exists()).toBe(false)
    expect(wrapper.findAll('.document-branch')).toHaveLength(1)
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-1/content')
  })

  it('shows the decorative brand mark inside the existing homepage link', async () => {
    const wrapper = await mountWorkspace()
    const brand = wrapper.get('a.brand')
    const mark = brand.get('img.brand__mark')

    expect(mark.attributes()).toMatchObject({
      src: '/icon.svg',
      alt: '',
      'aria-hidden': 'true',
      width: '32',
      height: '32',
    })
    expect(brand.text()).toContain('企业研究资料库')
  })

  it('clears old documents while changing company and selects the new first document', async () => {
    const nextDocuments = deferred<DocumentItem[]>()
    vi.mocked(library.listDocuments)
      .mockResolvedValueOnce(companyOneDocuments)
      .mockReturnValueOnce(nextDocuments.promise)
    const wrapper = await mountWorkspace()

    await wrapper.get('[data-company-id="company-2"]').trigger('click')

    expect(wrapper.text()).not.toContain('年度报告')
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('正在读取资料目录')

    nextDocuments.resolve(companyTwoDocuments)
    await flushPromises()

    expect(wrapper.get('[data-document-id="document-3"]').attributes('aria-current')).toBe('true')
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-3/content')
  })

  it('changes the active document without copying its body into the shell', async () => {
    const wrapper = await mountWorkspace()

    await wrapper.get('[data-document-id="document-2"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-document-id="document-2"]').attributes('aria-current')).toBe('true')
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-2/content')
    expect(wrapper.get('iframe').attributes('title')).toBe('阅读：管理层访谈')
  })

  it('shows distinct empty states for an empty library and an empty company', async () => {
    vi.mocked(library.listCompanies).mockResolvedValueOnce([])
    const emptyLibrary = await mountWorkspace()

    expect(emptyLibrary.text()).toContain('资料库里还没有公司')
    expect(library.listDocuments).not.toHaveBeenCalled()
    unmountTracked(emptyLibrary)

    vi.mocked(library.listCompanies).mockResolvedValueOnce(companies)
    vi.mocked(library.listDocuments).mockResolvedValueOnce([])
    const emptyCompany = await mountWorkspace()

    expect(emptyCompany.text()).toContain('这家公司还没有可阅读的资料')
  })

  it('recovers from company and document fetch failures with useful retry actions', async () => {
    vi.mocked(library.listCompanies).mockRejectedValueOnce(new Error('公司目录暂不可用'))
    const wrapper = await mountWorkspace()

    expect(wrapper.get('[role="alert"]').text()).toContain('公司目录暂不可用')
    vi.mocked(library.listCompanies).mockResolvedValueOnce(companies)
    await wrapper.get('button[name="retry-companies"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(true)

    vi.mocked(library.listDocuments).mockRejectedValueOnce(new Error('资料目录暂不可用'))
    await wrapper.get('[data-company-id="company-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('资料目录暂不可用')

    vi.mocked(library.listDocuments).mockResolvedValueOnce(companyOneDocuments)
    await wrapper.get('button[name="retry-documents"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-1/content')
  })

  it('ignores a stale company document response after a newer selection resolves', async () => {
    const oldRequest = deferred<DocumentItem[]>()
    const currentRequest = deferred<DocumentItem[]>()
    vi.mocked(library.listDocuments)
      .mockReset()
      .mockReturnValueOnce(oldRequest.promise)
      .mockReturnValueOnce(currentRequest.promise)

    const wrapper = track(mount(App))
    await flushPromises()
    await wrapper.get('[data-company-id="company-2"]').trigger('click')

    currentRequest.resolve(companyTwoDocuments)
    await flushPromises()
    expect(wrapper.text()).toContain('产品札记')

    oldRequest.resolve(companyOneDocuments)
    await flushPromises()
    expect(wrapper.text()).toContain('产品札记')
    expect(wrapper.text()).not.toContain('年度报告')
  })

  it('preserves a valid document selection after refresh and repairs a removed selection', async () => {
    vi.mocked(library.listDocuments)
      .mockResolvedValueOnce(companyOneDocuments)
      .mockResolvedValueOnce([...companyOneDocuments])
      .mockResolvedValueOnce([companyOneDocuments[0]!])
    const wrapper = await mountWorkspace()

    await wrapper.get('[data-document-id="document-2"]').trigger('click')
    await wrapper.get('[data-company-id="company-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-2/content')

    await wrapper.get('[data-company-id="company-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-1/content')
  })

  it('opens one labeled library drawer with initial focus and restores focus on Escape', async () => {
    vi.mocked(library.listDocuments).mockResolvedValueOnce([])
    document.body.style.overflow = 'clip'
    const wrapper = await mountWorkspace(true)
    const trigger = wrapper.get('button[name="open-library-directory"]')

    await trigger.trigger('click')
    await nextTick()

    expect(wrapper.findAll('[aria-label="公司与资料"]')).toHaveLength(1)
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(wrapper.get('button[name="close-library-directory"]').element)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    expect(document.body.style.overflow).toBe('clip')
  })

  it('dismisses the library drawer by backdrop and close button', async () => {
    vi.mocked(library.listDocuments).mockResolvedValueOnce([])
    document.body.style.overflow = 'clip'
    const wrapper = await mountWorkspace(true)
    const trigger = wrapper.get('button[name="open-library-directory"]')

    await trigger.trigger('click')
    await wrapper.get('.library-backdrop').trigger('click')
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    expect(document.body.style.overflow).toBe('clip')

    await trigger.trigger('click')
    await wrapper.get('button[name="close-library-directory"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    expect(document.body.style.overflow).toBe('clip')
  })

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
})
