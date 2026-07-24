import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'

import App from '../app/app.vue'
import * as community from '../app/api/community'
import * as library from '../app/api/library'
import AuthDialog from '../app/components/AuthDialog.vue'
import CommentSection from '../app/components/CommentSection.vue'
import SiteUserControls from '../app/components/SiteUserControls.vue'
import type { Comment, UserAuthState, VerifyEmailInput } from '../app/types/community'
import type { Company, DocumentItem } from '../app/types/content'

vi.mock('../app/api/library', () => ({
  listCompanies: vi.fn(),
  listDocuments: vi.fn(),
}))

const sessionState = ref<UserAuthState | null>(null)
const restoreSession = vi.fn()
const logoutSession = vi.fn()
const replaceSessionState = vi.fn((next: UserAuthState) => {
  sessionState.value = next
  return next
})
const verifySessionEmail = vi.fn(async (input: VerifyEmailInput) => {
  const next = await community.verifyEmail(input)
  sessionState.value = next
  return next
})

vi.mock('../app/composables/useUserSession', () => ({
  useUserSession: () => ({
    state: sessionState,
    user: computed(() => sessionState.value?.user ?? null),
    authenticated: computed(() => sessionState.value?.authenticated === true),
    loading: ref(false),
    restore: restoreSession,
    logout: logoutSession,
    replaceState: replaceSessionState,
    verifyEmail: verifySessionEmail,
  }),
}))

vi.mock('../app/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../app/api/community')>()
  return {
    ...actual,
    getCommentThread: vi.fn(),
    listDocumentComments: vi.fn(),
    listNotifications: vi.fn(),
    unsubscribeEmail: vi.fn(),
    verifyEmail: vi.fn(),
  }
})

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
    uploaded_at: '2026-07-20T08:00:00Z',
    content_url: '/api/v1/documents/document-1/content',
  },
  {
    id: 'document-2',
    company_id: 'company-1',
    title: '管理层访谈',
    format: 'html',
    original_filename: 'interview.html',
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
    uploaded_at: '2026-07-18T08:00:00Z',
    content_url: '/api/v1/documents/document-3/content',
  },
]

function comment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: 'thread-root',
    document_id: 'document-3',
    parent_id: null,
    body: '深链评论',
    status: 'published',
    author: { id: 'user-2', username: '研究读者' },
    created_at: '2026-07-24T08:00:00Z',
    edited_at: null,
    replies: [],
    can_edit: false,
    can_delete: false,
    can_report: true,
    ...overrides,
  }
}

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
    sessionState.value = {
      authenticated: false,
      user: null,
      csrf_token: null,
      expires_at: null,
      registration_enabled: true,
    }
    restoreSession.mockReset().mockResolvedValue(sessionState.value)
    logoutSession.mockReset().mockResolvedValue(undefined)
    vi.mocked(community.listDocumentComments).mockReset().mockResolvedValue({
      items: [],
      viewer_pending: [],
      next_cursor: null,
      total_count: 0,
    })
    vi.mocked(community.getCommentThread).mockReset()
    vi.mocked(community.listNotifications).mockReset().mockResolvedValue({ items: [], unread_count: 0 })
    vi.mocked(community.unsubscribeEmail).mockReset().mockResolvedValue({
      message: '已停止接收评论回复邮件',
    })
    vi.mocked(community.verifyEmail).mockReset().mockResolvedValue({
      authenticated: true,
      user: {
        id: 'user-1',
        email: 'reader@example.com',
        username: '价值读者',
        email_verified_at: '2026-07-24T08:00:00Z',
        first_comment_approved_at: null,
        reply_email_enabled: true,
      },
      csrf_token: 'verified-csrf',
      expires_at: '2026-08-24T08:00:00Z',
      registration_enabled: true,
    })
    window.history.replaceState({}, '', '/')
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0).reverse()) wrapper.unmount()
    document.body.innerHTML = ''
    document.body.style.overflow = ''
    window.history.replaceState({}, '', '/')
    delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('starts session restoration in parallel with the company request', async () => {
    const sessionRequest = deferred<UserAuthState>()
    const companyRequest = deferred<Company[]>()
    restoreSession.mockReturnValueOnce(sessionRequest.promise)
    vi.mocked(library.listCompanies).mockReturnValueOnce(companyRequest.promise)

    const wrapper = track(mount(App))
    await nextTick()
    expect(restoreSession).toHaveBeenCalledOnce()
    expect(library.listCompanies).toHaveBeenCalledOnce()

    sessionRequest.resolve(sessionState.value!)
    companyRequest.resolve(companies)
    await flushPromises()
    expect(wrapper.get('[data-company-id="company-1"]').exists()).toBe(true)
  })

  it('consumes an email-verification fragment before submitting the token', async () => {
    window.history.replaceState({}, '', '/#verify-email=verification-token')
    vi.mocked(community.verifyEmail).mockImplementationOnce(async (input) => {
      expect(window.location.hash).toBe('')
      expect(input).toEqual({ token: 'verification-token' })
      return {
        authenticated: true,
        user: {
          id: 'user-1', email: 'reader@example.com', username: '价值读者',
          email_verified_at: '2026-07-24T08:00:00Z', first_comment_approved_at: null,
          reply_email_enabled: true,
        },
        csrf_token: 'verified-csrf', expires_at: null, registration_enabled: true,
      }
    })

    const wrapper = await mountWorkspace()

    expect(community.verifyEmail).toHaveBeenCalledOnce()
    expect(window.location.href).not.toContain('verification-token')
    expect(wrapper.get('button[aria-label="账户：价值读者"]').exists()).toBe(true)
  })

  it('opens password reset from a fragment and clears it before user input', async () => {
    window.history.replaceState({}, '', '/?company=company-1#password-reset=reset-token')

    const wrapper = await mountWorkspace()

    const controls = wrapper.getComponent(SiteUserControls)
    expect(controls.props('resetToken')).toBe('reset-token')
    expect(controls.getComponent(AuthDialog).props('resetToken')).toBe('reset-token')
    expect(wrapper.get('[role="dialog"]').text()).toContain('重设密码')
    expect(window.location.pathname + window.location.search + window.location.hash).toBe('/?company=company-1')
  })

  it('unsubscribes from a fragment only after removing the token from the address', async () => {
    window.history.replaceState({}, '', '/#unsubscribe=unsubscribe-token')
    vi.mocked(community.unsubscribeEmail).mockImplementationOnce(async (token) => {
      expect(window.location.hash).toBe('')
      expect(token).toBe('unsubscribe-token')
      return { message: '已停止接收评论回复邮件' }
    })

    const wrapper = await mountWorkspace()

    expect(community.unsubscribeEmail).toHaveBeenCalledOnce()
    expect(window.location.href).not.toContain('unsubscribe-token')
    expect(wrapper.get('[role="status"]').text()).toContain('已停止接收评论回复邮件')
  })

  it('preserves unrelated page fragments', async () => {
    window.history.replaceState({}, '', '/#research-notes')

    await mountWorkspace()

    expect(window.location.hash).toBe('#research-notes')
    expect(community.unsubscribeEmail).not.toHaveBeenCalled()
    expect(community.verifyEmail).not.toHaveBeenCalled()
  })

  it('restores a deep-linked document and scrolls an off-page target before cleaning the URL target', async () => {
    window.history.replaceState({}, '', '/?company=company-2&document=document-3&comment=target-comment')
    vi.mocked(community.getCommentThread).mockResolvedValue({
      root: comment({
        replies: [comment({ id: 'target-comment', parent_id: 'thread-root' })],
      }),
      target_comment_id: 'target-comment',
      viewer_pending: [],
    })
    const wrapper = await mountWorkspace()

    expect(library.listDocuments).toHaveBeenCalledWith('company-2')
    expect(wrapper.get('[data-document-id="document-3"]').attributes('aria-current')).toBe('true')
    expect(community.getCommentThread).toHaveBeenCalledWith('target-comment')
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith({ block: 'center' })
    expect(wrapper.get('[data-comment-id="target-comment"]').classes()).toContain('comment-target')
    expect(window.location.search).toBe('?company=company-2&document=document-3')
  })

  it('reports a missing deep-link target without replacing the article', async () => {
    window.history.replaceState({}, '', '/?company=company-1&document=document-1&comment=missing-comment')
    vi.mocked(community.getCommentThread).mockRejectedValueOnce(new Error('评论不存在'))
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('这条评论已不存在或暂时无法查看')
    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-1/content')
  })

  it('retires the deep-link target after the reader deliberately changes company', async () => {
    window.history.replaceState({}, '', '/?company=company-2&document=document-3&comment=target-comment')
    vi.mocked(community.getCommentThread).mockResolvedValue({
      root: comment({ id: 'target-comment' }),
      target_comment_id: 'target-comment',
      viewer_pending: [],
    })
    const wrapper = await mountWorkspace()
    expect(wrapper.getComponent(CommentSection).props('targetCommentId')).toBe('target-comment')

    await wrapper.get('[data-company-id="company-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.getComponent(CommentSection).props('targetCommentId')).toBeNull()
  })

  it('keeps the article available when comments fail to load', async () => {
    vi.mocked(community.listDocumentComments).mockRejectedValueOnce(new Error('评论服务暂不可用'))
    const wrapper = await mountWorkspace()

    expect(wrapper.get('iframe').attributes('src')).toBe('/api/v1/documents/document-1/content')
    expect(wrapper.get('.comment-section [role="alert"]').text()).toContain('评论服务暂不可用')
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
