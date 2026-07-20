import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../src/App.vue'
import * as api from '../src/api'
import type { Company, DocumentItem, UploadBatch } from '../src/types'

vi.mock('../src/api', () => ({
  createCompany: vi.fn(),
  deleteDocument: vi.fn(),
  listCompanies: vi.fn(),
  listDocuments: vi.fn(),
  renameDocument: vi.fn(),
  uploadDocuments: vi.fn(),
}))

const companies: Company[] = [
  { id: 'company-1', name: '山河研究', ticker: '600001', market: '上交所' },
  { id: 'company-2', name: '远望科技', ticker: null, market: null },
]

const documents: DocumentItem[] = [
  {
    id: 'document-1',
    company_id: 'company-1',
    title: '年度报告',
    format: 'markdown',
    original_filename: 'annual.md',
    uploaded_at: '2026-07-20T08:00:00Z',
    content_url: '/api/v1/documents/document-1/content',
  },
]

async function mountWorkspace() {
  const wrapper = mount(App)
  await flushPromises()
  return wrapper
}

describe('资料管理工作台', () => {
  beforeEach(() => {
    vi.mocked(api.listCompanies).mockResolvedValue(companies)
    vi.mocked(api.listDocuments).mockResolvedValue(documents)
    vi.mocked(api.createCompany).mockResolvedValue(companies[1]!)
    vi.mocked(api.uploadDocuments).mockResolvedValue({ items: [], errors: [] })
    vi.mocked(api.renameDocument).mockResolvedValue(documents[0]!)
    vi.mocked(api.deleteDocument).mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('loads companies and the selected company document list into an accessible workspace', async () => {
    const wrapper = await mountWorkspace()

    expect(api.listCompanies).toHaveBeenCalledOnce()
    expect(api.listDocuments).toHaveBeenCalledWith('company-1')
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.get('h1').text()).toBe('资料归档台')
    expect(wrapper.get('label[for="company-select"]').text()).toContain('当前公司')
    expect(wrapper.get('input[type="file"]').attributes()).toMatchObject({ accept: '.html,.md', multiple: '' })
    expect(wrapper.get('[aria-live="polite"]').exists()).toBe(true)
    expect(wrapper.get('a[href="/"]').text()).toContain('公开站点')
    expect(wrapper.text()).toContain('仅供本地开发环境使用')
  })

  it('creates a company with optional ticker and market and keeps it selected', async () => {
    const wrapper = await mountWorkspace()

    await wrapper.get('button[name="show-company-form"]').trigger('click')
    await wrapper.get('input[name="company-name"]').setValue('远望科技')
    await wrapper.get('input[name="ticker"]').setValue('09999')
    await wrapper.get('input[name="market"]').setValue('港交所')
    await wrapper.get('form[aria-label="新建公司"]').trigger('submit')
    await flushPromises()

    expect(api.createCompany).toHaveBeenCalledWith({ name: '远望科技', ticker: '09999', market: '港交所' })
    expect(api.listDocuments).toHaveBeenLastCalledWith('company-2')
    expect((wrapper.get('#company-select').element as HTMLSelectElement).value).toBe('company-2')
  })

  it('uploads multiple files, reports each outcome, clears the picker, and refreshes full documents', async () => {
    const batch: UploadBatch = {
      items: [
        {
          id: 'upload-1',
          title: '访谈记录',
          format: 'markdown',
          content_url: '/api/v1/documents/upload-1/content',
        },
      ],
      errors: [{ filename: 'broken.html', message: '文件处理失败' }],
    }
    vi.mocked(api.uploadDocuments).mockResolvedValue(batch)
    const wrapper = await mountWorkspace()
    const input = wrapper.get('input[type="file"]')
    const files = [new File(['# Notes'], 'notes.md'), new File(['<h1>Bad</h1>'], 'broken.html')]
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })

    await input.trigger('change')
    await wrapper.get('form[aria-label="上传资料"]').trigger('submit')
    await flushPromises()

    expect(api.uploadDocuments).toHaveBeenCalledWith('company-1', files)
    expect(wrapper.get('[aria-live="polite"]').text()).toContain('访谈记录')
    expect(wrapper.get('[aria-live="polite"]').text()).toContain('broken.html')
    expect(wrapper.get('[aria-live="polite"]').text()).toContain('文件处理失败')
    expect(api.listDocuments).toHaveBeenCalledTimes(2)
    expect((input.element as HTMLInputElement).value).toBe('')
  })

  it('keeps company selection fixed while an upload is in flight', async () => {
    let finishUpload: ((batch: UploadBatch) => void) | undefined
    vi.mocked(api.uploadDocuments).mockImplementation(
      () => new Promise((resolve) => (finishUpload = resolve)),
    )
    const wrapper = await mountWorkspace()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['# Notes'], 'notes.md')],
    })

    await input.trigger('change')
    await wrapper.get('form[aria-label="上传资料"]').trigger('submit')

    expect(wrapper.get('#company-select').attributes('disabled')).toBeDefined()
    finishUpload?.({ items: [], errors: [] })
    await flushPromises()
  })

  it('renames a document and refreshes the selected company', async () => {
    const wrapper = await mountWorkspace()
    const titleInput = wrapper.get('input[aria-label="重命名 年度报告"]')

    await titleInput.setValue('年度复盘')
    await titleInput.trigger('keydown.enter')
    await flushPromises()

    expect(api.renameDocument).toHaveBeenCalledWith('document-1', '年度复盘')
    expect(api.listDocuments).toHaveBeenCalledTimes(2)
    expect((wrapper.get('#company-select').element as HTMLSelectElement).value).toBe('company-1')
  })

  it('asks for confirmation before deleting a document and refreshes after confirmation', async () => {
    const confirmSpy = vi.fn().mockReturnValue(false)
    vi.stubGlobal('confirm', confirmSpy)
    const wrapper = await mountWorkspace()
    const deleteButton = wrapper.get('button[aria-label="删除 年度报告"]')

    await deleteButton.trigger('click')
    expect(confirmSpy).toHaveBeenCalledWith('确认删除《年度报告》？此操作无法撤销。')
    expect(api.deleteDocument).not.toHaveBeenCalled()

    confirmSpy.mockReturnValue(true)
    await deleteButton.trigger('click')
    await flushPromises()

    expect(api.deleteDocument).toHaveBeenCalledWith('document-1')
    expect(api.listDocuments).toHaveBeenCalledTimes(2)
  })
})
