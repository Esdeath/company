import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../src/App.vue'
import * as api from '../src/api'
import DocumentUpload from '../src/components/DocumentUpload.vue'
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

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

async function mountWorkspace() {
  const wrapper = mount(App)
  await flushPromises()
  return wrapper
}

describe('资料管理工作台', () => {
  beforeEach(() => {
    vi.mocked(api.listCompanies).mockReset().mockResolvedValue(companies)
    vi.mocked(api.listDocuments).mockReset().mockResolvedValue(documents)
    vi.mocked(api.createCompany).mockReset().mockResolvedValue(companies[1]!)
    vi.mocked(api.uploadDocuments).mockReset().mockResolvedValue({ items: [], errors: [] })
    vi.mocked(api.renameDocument).mockReset().mockResolvedValue(documents[0]!)
    vi.mocked(api.deleteDocument).mockReset().mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
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

  it('keeps uploaded content out of unsandboxed top-level navigation', async () => {
    const wrapper = await mountWorkspace()

    const documentRow = wrapper.get('.document-row')
    expect(documentRow.get('.document-title').text()).toBe('年度报告')
    expect(documentRow.find(`a[href="${documents[0]!.content_url}"]`).exists()).toBe(false)
    expect(documentRow.find('[target="_blank"]').exists()).toBe(false)
    expect(documentRow.get('input[aria-label="重命名 年度报告"]').exists()).toBe(true)
    expect(documentRow.get('button[aria-label="删除 年度报告"]').exists()).toBe(true)
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
    expect(wrapper.find('form[aria-label="新建公司"]').exists()).toBe(false)
  })

  it('submits blank optional company fields as null', async () => {
    const newCompany = { id: 'company-3', name: '新岸资本', ticker: null, market: null }
    vi.mocked(api.createCompany).mockResolvedValue(newCompany)
    vi.mocked(api.listCompanies).mockResolvedValue([...companies, newCompany])
    const wrapper = await mountWorkspace()

    await wrapper.get('button[name="show-company-form"]').trigger('click')
    await wrapper.get('input[name="company-name"]').setValue('新岸资本')
    await wrapper.get('form[aria-label="新建公司"]').trigger('submit')
    await flushPromises()

    expect(api.createCompany).toHaveBeenCalledWith({ name: '新岸资本', ticker: null, market: null })
  })

  it('preserves the company draft and blocks duplicate creates while the request is pending', async () => {
    const createRequest = deferred<Company>()
    vi.mocked(api.createCompany).mockReturnValue(createRequest.promise)
    const wrapper = await mountWorkspace()

    await wrapper.get('button[name="show-company-form"]').trigger('click')
    await wrapper.get('input[name="company-name"]').setValue('留存研究')
    await wrapper.get('input[name="ticker"]').setValue('01234')
    await wrapper.get('input[name="market"]').setValue('港交所')
    const form = wrapper.get('form[aria-label="新建公司"]')
    await form.trigger('submit')
    await form.trigger('submit')

    expect(api.createCompany).toHaveBeenCalledOnce()
    expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('input[name="company-name"]').attributes('disabled')).toBeDefined()

    createRequest.reject(new Error('公司保存失败'))
    await flushPromises()

    expect(wrapper.find('form[aria-label="新建公司"]').exists()).toBe(true)
    expect((wrapper.get('input[name="company-name"]').element as HTMLInputElement).value).toBe('留存研究')
    expect((wrapper.get('input[name="ticker"]').element as HTMLInputElement).value).toBe('01234')
    expect((wrapper.get('input[name="market"]').element as HTMLInputElement).value).toBe('港交所')
    expect(wrapper.get('.page-error').text()).toContain('公司保存失败')
  })

  it('keeps a successful company create when the following company refresh fails', async () => {
    const newCompany = { id: 'company-3', name: '新岸资本', ticker: null, market: null }
    vi.mocked(api.createCompany).mockResolvedValue(newCompany)
    const wrapper = await mountWorkspace()
    vi.mocked(api.listCompanies).mockRejectedValueOnce(new Error('公司列表暂不可用'))

    await wrapper.get('button[name="show-company-form"]').trigger('click')
    await wrapper.get('input[name="company-name"]').setValue('新岸资本')
    await wrapper.get('form[aria-label="新建公司"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('form[aria-label="新建公司"]').exists()).toBe(false)
    expect(wrapper.get('.company-heading').text()).toContain('新岸资本')
    expect(wrapper.get('.refresh-warning').text()).toContain('公司列表暂不可用')
    expect(wrapper.find('.page-error').exists()).toBe(false)
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

  it('keeps the real upload result when the following document refresh fails', async () => {
    const batch: UploadBatch = {
      items: [
        {
          id: 'upload-1',
          title: '访谈记录',
          format: 'markdown',
          content_url: '/api/v1/documents/upload-1/content',
        },
      ],
      errors: [],
    }
    vi.mocked(api.uploadDocuments).mockResolvedValue(batch)
    const wrapper = await mountWorkspace()
    vi.mocked(api.listDocuments).mockRejectedValueOnce(new Error('目录刷新失败'))
    const input = wrapper.get('input[type="file"]')
    const files = [new File(['# Notes'], 'notes.md')]
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })

    await input.trigger('change')
    await wrapper.get('form[aria-label="上传资料"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.upload-results[aria-live="polite"]').text()).toContain('访谈记录')
    expect(wrapper.get('.upload-results[aria-live="polite"]').text()).not.toContain('notes.md：目录刷新失败')
    expect(wrapper.get('.refresh-warning').text()).toContain('目录刷新失败')
    expect(wrapper.find('.page-error').exists()).toBe(false)
  })

  it('ignores an older company fetch that resolves after an upload refresh', async () => {
    const oldSelection = deferred<DocumentItem[]>()
    const uploadRefresh = deferred<DocumentItem[]>()
    const refreshedDocument = { ...documents[0]!, id: 'document-new', company_id: 'company-2', title: '新目录' }
    const staleDocument = { ...documents[0]!, id: 'document-old', company_id: 'company-2', title: '旧目录' }
    const wrapper = await mountWorkspace()
    vi.mocked(api.listDocuments)
      .mockReset()
      .mockReturnValueOnce(oldSelection.promise)
      .mockReturnValueOnce(uploadRefresh.promise)

    await wrapper.get('#company-select').setValue('company-2')
    expect(wrapper.text()).not.toContain('年度报告')
    expect(wrapper.find('button[aria-label="删除 年度报告"]').exists()).toBe(false)

    wrapper.findComponent(DocumentUpload).vm.$emit('upload', [new File(['# Notes'], 'notes.md')])
    await flushPromises()

    uploadRefresh.resolve([refreshedDocument])
    await flushPromises()
    expect(wrapper.text()).toContain('新目录')

    oldSelection.resolve([staleDocument])
    await flushPromises()
    expect(wrapper.text()).toContain('新目录')
    expect(wrapper.text()).not.toContain('旧目录')
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

  it('blocks duplicate rename requests and disables document actions through the refresh', async () => {
    const renameRequest = deferred<DocumentItem>()
    const refreshRequest = deferred<DocumentItem[]>()
    vi.mocked(api.renameDocument).mockReturnValue(renameRequest.promise)
    const wrapper = await mountWorkspace()
    vi.mocked(api.listDocuments).mockReturnValueOnce(refreshRequest.promise)
    const titleInput = wrapper.get('input[aria-label="重命名 年度报告"]')

    await titleInput.setValue('年度复盘')
    await titleInput.trigger('keydown.enter')
    await titleInput.trigger('keydown.enter')
    expect(api.renameDocument).toHaveBeenCalledOnce()
    expect(titleInput.attributes('disabled')).toBeDefined()

    renameRequest.resolve({ ...documents[0]!, title: '年度复盘' })
    await flushPromises()
    expect(wrapper.get('button[aria-label="删除 年度复盘"]').attributes('disabled')).toBeDefined()

    refreshRequest.resolve([{ ...documents[0]!, title: '年度复盘' }])
    await flushPromises()
  })

  it('keeps a successful rename when the following document refresh fails', async () => {
    vi.mocked(api.renameDocument).mockResolvedValue({ ...documents[0]!, title: '年度复盘' })
    const wrapper = await mountWorkspace()
    vi.mocked(api.listDocuments).mockRejectedValueOnce(new Error('目录刷新失败'))
    const titleInput = wrapper.get('input[aria-label="重命名 年度报告"]')

    await titleInput.setValue('年度复盘')
    await titleInput.trigger('keydown.enter')
    await flushPromises()

    expect(wrapper.get('.document-row__heading').text()).toContain('年度复盘')
    expect(wrapper.get('.refresh-warning').text()).toContain('目录刷新失败')
    expect(wrapper.find('.page-error').exists()).toBe(false)
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

  it('blocks duplicate deletes while the request is pending', async () => {
    const deleteRequest = deferred<void>()
    const confirmSpy = vi.fn().mockReturnValue(true)
    vi.stubGlobal('confirm', confirmSpy)
    vi.mocked(api.deleteDocument).mockReturnValue(deleteRequest.promise)
    const wrapper = await mountWorkspace()
    const deleteButton = wrapper.get('button[aria-label="删除 年度报告"]')

    await deleteButton.trigger('click')
    await deleteButton.trigger('click')

    expect(api.deleteDocument).toHaveBeenCalledOnce()
    expect(confirmSpy).toHaveBeenCalledOnce()
    expect(deleteButton.attributes('disabled')).toBeDefined()

    deleteRequest.resolve()
    await flushPromises()
  })

  it('keeps a successful delete when the following document refresh fails', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    const wrapper = await mountWorkspace()
    vi.mocked(api.listDocuments).mockRejectedValueOnce(new Error('目录刷新失败'))

    await wrapper.get('button[aria-label="删除 年度报告"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('年度报告')
    expect(wrapper.get('.refresh-warning').text()).toContain('目录刷新失败')
    expect(wrapper.find('.page-error').exists()).toBe(false)
  })
})
