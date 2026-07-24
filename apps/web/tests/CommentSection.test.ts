import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import CommentSection from '../app/components/CommentSection.vue'
import * as community from '../app/api/community'
import type { Comment, CommentPage, User } from '../app/types/community'

vi.mock('../app/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../app/api/community')>()
  return {
    ...actual,
    listDocumentComments: vi.fn(),
    getCommentThread: vi.fn(),
    createComment: vi.fn(),
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
    reportComment: vi.fn(),
  }
})

const USER: User = {
  id: 'user-1',
  email: 'reader@example.com',
  username: '研究员',
  email_verified_at: '2026-07-24T08:00:00Z',
  first_comment_approved_at: null,
  reply_email_enabled: true,
}

function comment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: 'comment-1',
    document_id: 'document-1',
    parent_id: null,
    body: '第一条评论',
    status: 'published',
    author: { id: 'other', username: '读者' },
    created_at: '2026-07-24T08:00:00Z',
    edited_at: null,
    replies: [],
    can_edit: false,
    can_delete: false,
    can_report: true,
    ...overrides,
  }
}

function page(overrides: Partial<CommentPage> = {}): CommentPage {
  return { items: [comment()], viewer_pending: [], next_cursor: null, total_count: 1, ...overrides }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function mountSection(props: Record<string, unknown> = {}) {
  return mount(CommentSection, {
    props: { documentId: 'document-1', currentUser: USER, targetCommentId: null, ...props },
  })
}

async function submitReport(
  wrapper: ReturnType<typeof mountSection>,
  commentId: string,
  reason = 'spam',
  details = '',
) {
  await wrapper.get(`button[name="report-${commentId}"]`).trigger('click')
  await wrapper.get(`select[name="report-reason-${commentId}"]`).setValue(reason)
  if (details) {
    await wrapper.get(`textarea[name="report-details-${commentId}"]`).setValue(details)
  }
  await wrapper.get(`form[data-report-comment-id="${commentId}"]`).trigger('submit')
}

afterEach(() => vi.resetAllMocks())

describe('CommentSection', () => {
  it('shows loading, error/retry, and logged-out prompts', async () => {
    vi.mocked(community.listDocumentComments).mockImplementation(() => new Promise(() => undefined))
    const loading = mountSection()
    expect(loading.get('[role="status"]').text()).toContain('正在加载评论')
    loading.unmount()

    vi.mocked(community.listDocumentComments).mockReset()
    vi.mocked(community.listDocumentComments).mockRejectedValueOnce(new Error('网络错误')).mockResolvedValueOnce(page())
    const failed = mountSection()
    await flushPromises()
    expect(failed.get('[role="alert"]').text()).toContain('网络错误')
    await failed.get('button[name="retry-comments"]').trigger('click')
    await flushPromises()
    expect(community.listDocumentComments).toHaveBeenCalledTimes(2)

    const signedOut = mountSection({ currentUser: null })
    await flushPromises()
    await signedOut.get('button[name="login-to-comment"]').trigger('click')
    expect(signedOut.emitted('login-required')).toHaveLength(1)
  })

  it('keeps a 2,000-character counter and shows private pending previews', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(
      page({ viewer_pending: [comment({ id: 'pending-root', status: 'pending', body: '我的待审核评论' })] }),
    )
    const wrapper = mountSection()
    await flushPromises()
    const textarea = wrapper.get('textarea[name="comment-body"]')
    await textarea.setValue('x'.repeat(2001))

    expect(wrapper.text()).toContain('2,000')
    expect(wrapper.get('button[name="publish-comment"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('仅你可见')
    expect(wrapper.text()).toContain('我的待审核评论')
  })

  it('orders newest roots first, oldest replies first, and permits only one reply level', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(
      page({
        items: [
          comment({ id: 'old', created_at: '2026-07-20T08:00:00Z' }),
          comment({
            id: 'new',
            created_at: '2026-07-24T08:00:00Z',
            replies: [
              comment({ id: 'newer-reply', parent_id: 'new', created_at: '2026-07-23T08:00:00Z' }),
              comment({ id: 'older-reply', parent_id: 'new', created_at: '2026-07-22T08:00:00Z' }),
            ],
          }),
        ],
      }),
    )
    const wrapper = mountSection()
    await flushPromises()
    expect(wrapper.findAll('[data-comment-id]').map((node) => node.attributes('data-comment-id'))).toEqual([
      'new',
      'older-reply',
      'newer-reply',
      'old',
    ])
    await wrapper.get('button[name="reply-new"]').trigger('click')
    expect(wrapper.get('textarea[name="reply-body-new"]').exists()).toBe(true)
  })

  it('submits a reply to a reply through the one-level thread UI', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(
      page({
        items: [
          comment({
            id: 'root',
            replies: [comment({ id: 'direct-reply', parent_id: 'root' })],
          }),
        ],
        total_count: 2,
      }),
    )
    vi.mocked(community.createComment).mockResolvedValue(
      comment({ id: 'flattened-reply', parent_id: 'root', body: '回复一级回复' }),
    )
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('button[name="reply-direct-reply"]').trigger('click')
    await wrapper.get('textarea[name="reply-body-direct-reply"]').setValue('回复一级回复')
    await wrapper.get('form.comment-section__reply').trigger('submit')
    await flushPromises()

    expect(community.createComment).toHaveBeenCalledWith('document-1', {
      body: '回复一级回复',
      parent_id: 'direct-reply',
    })
    expect(wrapper.find('[data-comment-id="flattened-reply"]').exists()).toBe(true)
    expect(wrapper.get('[data-comment-id="root"]').find('ol ol').exists()).toBe(false)
  })

  it('ignores stale list responses when its document changes', async () => {
    const first = deferred<CommentPage>()
    const second = deferred<CommentPage>()
    vi.mocked(community.listDocumentComments).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountSection()
    await wrapper.setProps({ documentId: 'document-2' })
    second.resolve(page({ items: [comment({ id: 'document-2-comment', document_id: 'document-2' })] }))
    await flushPromises()
    first.resolve(page({ items: [comment({ id: 'stale' })] }))
    await flushPromises()
    expect(wrapper.find('[data-comment-id="document-2-comment"]').exists()).toBe(true)
    expect(wrapper.find('[data-comment-id="stale"]').exists()).toBe(false)
  })

  it('loads additional roots from the cursor and keeps drafts through login challenges', async () => {
    vi.mocked(community.listDocumentComments)
      .mockResolvedValueOnce(page({ next_cursor: 'next' }))
      .mockResolvedValueOnce(page({ items: [comment({ id: 'later' })] }))
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('button[name="load-more-comments"]').trigger('click')
    await flushPromises()
    expect(community.listDocumentComments).toHaveBeenLastCalledWith('document-1', 'next')

    const body = wrapper.get('textarea[name="comment-body"]')
    await body.setValue('保留的草稿')
    vi.mocked(community.createComment).mockRejectedValueOnce(new community.UserAuthenticationRequiredError('请登录'))
    const publish = wrapper.get('button[name="publish-comment"]')
    expect(publish.attributes('disabled')).toBeUndefined()
    await wrapper.get('form.comment-section__composer').trigger('submit')
    await flushPromises()
    expect(community.createComment).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('login-required')).toHaveLength(1)
    expect((body.element as HTMLTextAreaElement).value).toBe('保留的草稿')
  })

  it('reloads viewer-specific comments on logout and login without losing its draft', async () => {
    const authenticated = deferred<CommentPage>()
    const signedOut = deferred<CommentPage>()
    const signedInAgain = deferred<CommentPage>()
    vi.mocked(community.listDocumentComments)
      .mockReturnValueOnce(authenticated.promise)
      .mockReturnValueOnce(signedOut.promise)
      .mockReturnValueOnce(signedInAgain.promise)
    const wrapper = mountSection()
    await wrapper.get('textarea[name="comment-body"]').setValue('保留的会话草稿')

    await wrapper.setProps({ currentUser: null })
    expect(community.listDocumentComments).toHaveBeenCalledTimes(2)
    authenticated.resolve(page({ viewer_pending: [comment({ id: 'stale-private', status: 'pending' })] }))
    signedOut.resolve(page())
    await flushPromises()
    expect(wrapper.find('[data-comment-id="stale-private"]').exists()).toBe(false)

    await wrapper.setProps({ currentUser: USER })
    expect(community.listDocumentComments).toHaveBeenCalledTimes(3)
    signedInAgain.resolve(page({ viewer_pending: [comment({ id: 'private-again', status: 'pending' })] }))
    await flushPromises()
    expect(wrapper.find('[data-comment-id="private-again"]').exists()).toBe(true)
    expect((wrapper.get('textarea[name="comment-body"]').element as HTMLTextAreaElement).value).toBe('保留的会话草稿')
  })

  it('removes private rows and capabilities before the signed-out reload resolves', async () => {
    const signedOut = deferred<CommentPage>()
    vi.mocked(community.listDocumentComments)
      .mockResolvedValueOnce(page({ items: [comment({ can_edit: true, can_delete: true })], viewer_pending: [comment({ id: 'private', status: 'pending' })] }))
      .mockReturnValueOnce(signedOut.promise)
    const wrapper = mountSection()
    await flushPromises()
    expect(wrapper.get('button[name="edit-comment-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-comment-id="private"]').exists()).toBe(true)

    await wrapper.setProps({ currentUser: null })
    expect(wrapper.find('button[name="edit-comment-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-comment-id="private"]').exists()).toBe(false)
    signedOut.resolve(page())
    await flushPromises()
  })

  it('keeps separate in-memory drafts for each document', async () => {
    vi.mocked(community.listDocumentComments).mockReset().mockResolvedValue(page())
    const wrapper = mountSection()
    await flushPromises()
    await wrapper.get('textarea[name="comment-body"]').setValue('资料一草稿')
    await wrapper.setProps({ documentId: 'document-2' })
    await flushPromises()
    await wrapper.get('textarea[name="comment-body"]').setValue('资料二草稿')
    await wrapper.setProps({ documentId: 'document-1' })
    await flushPromises()

    expect((wrapper.get('textarea[name="comment-body"]').element as HTMLTextAreaElement).value).toBe('资料一草稿')
  })

  it('isolates overlapping publishes when the selected document changes', async () => {
    const firstCreate = deferred<Comment>()
    const secondCreate = deferred<Comment>()
    vi.mocked(community.listDocumentComments)
      .mockResolvedValueOnce(page({ items: [], total_count: 0 }))
      .mockResolvedValueOnce(page({ items: [], total_count: 0 }))
    vi.mocked(community.createComment)
      .mockReturnValueOnce(firstCreate.promise)
      .mockReturnValueOnce(secondCreate.promise)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('textarea[name="comment-body"]').setValue('资料一发布中')
    await wrapper.get('form.comment-section__composer').trigger('submit')
    expect(community.createComment).toHaveBeenLastCalledWith('document-1', {
      body: '资料一发布中',
      parent_id: null,
    })

    await wrapper.setProps({ documentId: 'document-2' })
    await flushPromises()
    await wrapper.get('textarea[name="comment-body"]').setValue('资料二发布中')
    expect(wrapper.get('button[name="publish-comment"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('form.comment-section__composer').trigger('submit')
    expect(community.createComment).toHaveBeenLastCalledWith('document-2', {
      body: '资料二发布中',
      parent_id: null,
    })

    firstCreate.resolve(comment({ id: 'stale-created', body: '资料一发布中' }))
    await flushPromises()
    expect(wrapper.find('[data-comment-id="stale-created"]').exists()).toBe(false)
    expect((wrapper.get('textarea[name="comment-body"]').element as HTMLTextAreaElement).value).toBe('资料二发布中')
    expect(wrapper.get('button[name="publish-comment"]').attributes('disabled')).toBeDefined()

    secondCreate.resolve(
      comment({ id: 'current-created', document_id: 'document-2', body: '资料二发布中' }),
    )
    await flushPromises()
    expect(wrapper.find('[data-comment-id="current-created"]').exists()).toBe(true)
    expect((wrapper.get('textarea[name="comment-body"]').element as HTMLTextAreaElement).value).toBe('')
  })

  it('does not let an old edit completion clear the current document edit draft', async () => {
    const firstUpdate = deferred<Comment>()
    vi.mocked(community.listDocumentComments)
      .mockResolvedValueOnce(
        page({ items: [comment({ id: 'first-edit', can_edit: true, can_delete: true })] }),
      )
      .mockResolvedValueOnce(
        page({
          items: [
            comment({
              id: 'second-edit',
              document_id: 'document-2',
              body: '资料二原文',
              can_edit: true,
              can_delete: true,
            }),
          ],
        }),
      )
    vi.mocked(community.updateComment).mockReturnValueOnce(firstUpdate.promise)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('button[name="edit-first-edit"]').trigger('click')
    await wrapper.get('textarea[name="edit-body-first-edit"]').setValue('资料一编辑')
    await wrapper.get('form.comment-item__edit').trigger('submit')
    await wrapper.setProps({ documentId: 'document-2' })
    await flushPromises()
    await wrapper.get('button[name="edit-second-edit"]').trigger('click')
    await wrapper.get('textarea[name="edit-body-second-edit"]').setValue('资料二编辑')

    firstUpdate.resolve(
      comment({ id: 'first-edit', body: '资料一编辑', can_edit: true, can_delete: true }),
    )
    await flushPromises()

    expect(wrapper.find('textarea[name="edit-body-second-edit"]').exists()).toBe(true)
    expect((wrapper.get('textarea[name="edit-body-second-edit"]').element as HTMLTextAreaElement).value).toBe('资料二编辑')
    expect(wrapper.text()).not.toContain('资料一编辑')
  })

  it('does not apply an old delete completion to the current document', async () => {
    const firstDelete = deferred<Comment>()
    vi.mocked(community.listDocumentComments)
      .mockResolvedValueOnce(
        page({ items: [comment({ id: 'shared-delete', can_delete: true })], total_count: 1 }),
      )
      .mockResolvedValueOnce(
        page({
          items: [
            comment({
              id: 'shared-delete',
              document_id: 'document-2',
              body: '资料二评论',
              can_delete: true,
            }),
          ],
          total_count: 1,
        }),
      )
    vi.mocked(community.deleteComment).mockReturnValueOnce(firstDelete.promise)
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('button[name="delete-shared-delete"]').trigger('click')
    await wrapper.get('button[name="confirm-delete-shared-delete"]').trigger('click')
    await wrapper.setProps({ documentId: 'document-2' })
    await flushPromises()
    firstDelete.resolve(
      comment({ id: 'shared-delete', status: 'deleted', body: null, can_delete: true }),
    )
    await flushPromises()

    expect(wrapper.get('[data-comment-id="shared-delete"]').text()).toContain('资料二评论')
    expect(wrapper.get('[data-comment-id="shared-delete"]').text()).not.toContain('此评论已删除')
    expect(wrapper.get('.comment-section__header > span').text()).toBe('1 条')
  })

  it('isolates overlapping reports when the selected document changes', async () => {
    const firstReport = deferred<undefined>()
    const secondReport = deferred<undefined>()
    vi.mocked(community.listDocumentComments)
      .mockResolvedValueOnce(page({ items: [comment({ id: 'shared-report' })] }))
      .mockResolvedValueOnce(
        page({ items: [comment({ id: 'shared-report', document_id: 'document-2' })] }),
      )
    vi.mocked(community.reportComment)
      .mockReturnValueOnce(firstReport.promise)
      .mockReturnValueOnce(secondReport.promise)
    const wrapper = mountSection()
    await flushPromises()

    await submitReport(wrapper, 'shared-report')
    await wrapper.setProps({ documentId: 'document-2' })
    await flushPromises()
    expect(wrapper.get('button[name="report-shared-report"]').attributes('disabled')).toBeUndefined()
    await submitReport(wrapper, 'shared-report', 'illegal')
    expect(community.reportComment).toHaveBeenCalledTimes(2)

    firstReport.resolve()
    await flushPromises()
    expect(wrapper.get('button[name="report-shared-report"]').text()).toContain('正在举报')

    secondReport.resolve()
    await flushPromises()
    expect(wrapper.get('button[name="report-shared-report"]').text()).toContain('已举报')
  })

  it('merges a private pending reply below its public parent', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(
      page({
        items: [comment({ id: 'public-root' })],
        viewer_pending: [comment({ id: 'pending-reply', parent_id: 'public-root', status: 'pending' })],
      }),
    )
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.findAll('[data-comment-id]').map((node) => node.attributes('data-comment-id'))).toEqual([
      'public-root',
      'pending-reply',
    ])
    expect(wrapper.get('[data-comment-id="public-root"] ol').exists()).toBe(true)
  })

  it('increments the published total after creating a published reply', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(
      page({
        items: [
          comment({
            id: 'count-root',
            replies: [comment({ id: 'count-reply', parent_id: 'count-root' })],
          }),
        ],
        total_count: 2,
      }),
    )
    vi.mocked(community.createComment).mockResolvedValue(
      comment({ id: 'second-count-reply', parent_id: 'count-root' }),
    )
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('button[name="reply-count-root"]').trigger('click')
    await wrapper.get('textarea[name="reply-body-count-root"]').setValue('新增公开回复')
    await wrapper.get('form.comment-section__reply').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.comment-section__header > span').text()).toBe('3 条')
  })

  it('decrements the published total only when deleting a published comment', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(
      page({
        items: [
          comment({
            id: 'delete-root',
            replies: [
              comment({
                id: 'published-reply',
                parent_id: 'delete-root',
                can_delete: true,
              }),
            ],
          }),
        ],
        viewer_pending: [
          comment({ id: 'pending-delete', status: 'pending', can_delete: true, can_report: false }),
        ],
        total_count: 2,
      }),
    )
    vi.mocked(community.deleteComment)
      .mockResolvedValueOnce(
        comment({
          id: 'published-reply',
          parent_id: 'delete-root',
          status: 'deleted',
          body: null,
          can_delete: true,
        }),
      )
      .mockResolvedValueOnce(
        comment({
          id: 'pending-delete',
          status: 'deleted',
          body: null,
          can_delete: true,
          can_report: false,
        }),
      )
    const wrapper = mountSection()
    await flushPromises()

    await wrapper.get('button[name="delete-published-reply"]').trigger('click')
    await wrapper.get('button[name="confirm-delete-published-reply"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.comment-section__header > span').text()).toBe('1 条')

    await wrapper.get('button[name="delete-pending-delete"]').trigger('click')
    await wrapper.get('button[name="confirm-delete-pending-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.comment-section__header > span').text()).toBe('1 条')
  })

  it('edits, deletes, and reports a comment only once', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(page({ items: [comment({ can_edit: true, can_delete: true })] }))
    vi.mocked(community.updateComment).mockResolvedValue(comment({ body: '编辑后', edited_at: '2026-07-24T10:00:00Z', can_edit: true, can_delete: true }))
    vi.mocked(community.deleteComment).mockResolvedValue(comment({ status: 'deleted', body: null, can_edit: true, can_delete: true }))
    vi.mocked(community.reportComment).mockResolvedValue()
    const wrapper = mountSection()
    await flushPromises()

    await submitReport(wrapper, 'comment-1', 'other', '与文章无关的引战内容')
    await flushPromises()
    expect(community.reportComment).toHaveBeenCalledWith('comment-1', {
      reason: 'other',
      details: '与文章无关的引战内容',
    })
    expect(wrapper.get('button[name="report-comment-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('form.comment-item__report').exists()).toBe(false)

    await wrapper.get('button[name="edit-comment-1"]').trigger('click')
    await wrapper.get('textarea[name="edit-body-comment-1"]').setValue('编辑后')
    await wrapper.get('form.comment-item__edit').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('编辑后')

    await wrapper.get('button[name="delete-comment-1"]').trigger('click')
    await wrapper.get('button[name="confirm-delete-comment-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('此评论已删除')
  })

  it('disables reporting immediately, preserves failed input, and allows a retry', async () => {
    const pendingReport = deferred<undefined>()
    vi.mocked(community.listDocumentComments).mockResolvedValue(page())
    vi.mocked(community.reportComment)
      .mockReturnValueOnce(pendingReport.promise)
      .mockRejectedValueOnce(new Error('举报失败'))
    const wrapper = mountSection()
    await flushPromises()

    await submitReport(wrapper, 'comment-1', 'harassment', '请核查上下文')
    await wrapper.get('form.comment-item__report').trigger('submit')
    expect(community.reportComment).toHaveBeenCalledTimes(1)
    expect(wrapper.get('button[name="confirm-report-comment-1"]').attributes('disabled')).toBeDefined()

    pendingReport.resolve()
    await flushPromises()
    expect(wrapper.get('button[name="report-comment-1"]').text()).toContain('已举报')
    expect(wrapper.find('form.comment-item__report').exists()).toBe(false)

    const retry = mountSection()
    await flushPromises()
    await submitReport(retry, 'comment-1', 'illegal', '疑似违法信息')
    await flushPromises()
    expect(retry.get('[role="alert"]').text()).toContain('举报失败')
    expect(retry.get('select[name="report-reason-comment-1"]').element.value).toBe('illegal')
    expect(retry.get('textarea[name="report-details-comment-1"]').element.value).toBe('疑似违法信息')
    expect(retry.get('button[name="report-comment-1"]').attributes('disabled')).toBeUndefined()
  })

  it('loads a requested target thread and marks the target as resolved', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(page())
    vi.mocked(community.updateComment).mockResolvedValue(comment({ body: '编辑后' }))
    vi.mocked(community.deleteComment).mockResolvedValue(comment({ status: 'deleted', body: null }))
    vi.mocked(community.reportComment).mockResolvedValue()
    vi.mocked(community.getCommentThread).mockResolvedValue({
      root: comment({ id: 'thread-root' }),
      target_comment_id: 'target',
      viewer_pending: [],
    })
    const wrapper = mountSection({ targetCommentId: 'target' })
    await flushPromises()
    expect(wrapper.find('[data-comment-id="thread-root"]').exists()).toBe(true)
    expect(wrapper.emitted('target-resolved')).toEqual([['target']])
  })

  it('waits for the regular list to reveal a thread before resolving its target', async () => {
    const list = deferred<CommentPage>()
    vi.mocked(community.listDocumentComments).mockReturnValueOnce(list.promise)
    vi.mocked(community.getCommentThread).mockResolvedValueOnce({
      root: comment({ id: 'target' }),
      target_comment_id: 'target',
      viewer_pending: [],
    })
    const wrapper = mountSection({ targetCommentId: 'target' })
    await flushPromises()
    expect(wrapper.emitted('target-resolved')).toBeUndefined()
    expect(wrapper.find('[data-comment-id="target"]').exists()).toBe(false)

    list.resolve(page())
    await flushPromises()
    expect(wrapper.find('[data-comment-id="target"]').exists()).toBe(true)
    expect(wrapper.emitted('target-resolved')).toEqual([['target']])
  })

  it('reports a missing requested target without failing the regular comment list', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(page())
    vi.mocked(community.getCommentThread).mockRejectedValueOnce(new Error('评论不存在'))
    const wrapper = mountSection({ targetCommentId: 'missing' })
    await flushPromises()

    expect(wrapper.emitted('target-missing')).toEqual([['missing']])
    expect(wrapper.find('[data-comment-id="comment-1"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('rejects a requested thread that belongs to another document', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(page())
    vi.mocked(community.getCommentThread).mockResolvedValueOnce({
      root: comment({ id: 'foreign-root', document_id: 'document-2' }),
      target_comment_id: 'foreign-target',
      viewer_pending: [],
    })
    const wrapper = mountSection({ targetCommentId: 'foreign-target' })
    await flushPromises()

    expect(wrapper.emitted('target-missing')).toEqual([['foreign-target']])
    expect(wrapper.emitted('target-resolved')).toBeUndefined()
    expect(wrapper.find('[data-comment-id="foreign-root"]').exists()).toBe(false)
  })

  it('keeps mutations to an off-page target thread visible', async () => {
    vi.mocked(community.listDocumentComments).mockResolvedValue(page({ items: [comment({ id: 'paged-root' })] }))
    vi.mocked(community.getCommentThread).mockResolvedValue({
      root: comment({ id: 'thread-root', can_edit: true, can_delete: true }),
      target_comment_id: 'target',
      viewer_pending: [],
    })
    vi.mocked(community.createComment).mockResolvedValue(
      comment({ id: 'thread-reply', parent_id: 'thread-root', body: '深链回复' }),
    )
    vi.mocked(community.updateComment).mockResolvedValue(
      comment({ id: 'thread-root', body: '深链编辑', can_edit: true, can_delete: true }),
    )
    vi.mocked(community.deleteComment).mockResolvedValue(
      comment({ id: 'thread-root', status: 'deleted', body: null, can_edit: true, can_delete: true }),
    )
    const wrapper = mountSection({ targetCommentId: 'target' })
    await flushPromises()

    await wrapper.get('button[name="reply-thread-root"]').trigger('click')
    await wrapper.get('textarea[name="reply-body-thread-root"]').setValue('深链回复')
    await wrapper.get('form.comment-section__reply').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-comment-id="thread-reply"]').exists()).toBe(true)

    await wrapper.get('button[name="edit-thread-root"]').trigger('click')
    await wrapper.get('textarea[name="edit-body-thread-root"]').setValue('深链编辑')
    await wrapper.get('form.comment-item__edit').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('深链编辑')

    await wrapper.get('button[name="delete-thread-root"]').trigger('click')
    await wrapper.get('button[name="confirm-delete-thread-root"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-comment-id="thread-root"]').text()).toContain('此评论已删除')
  })

  it('drops an obsolete target request when the target is cleared', async () => {
    const target = deferred<{ root: Comment; target_comment_id: string; viewer_pending: Comment[] }>()
    vi.mocked(community.listDocumentComments).mockResolvedValue(page())
    vi.mocked(community.getCommentThread).mockReturnValueOnce(target.promise)
    const wrapper = mountSection({ targetCommentId: 'target' })
    await wrapper.setProps({ targetCommentId: null })
    target.resolve({ root: comment({ id: 'obsolete-thread' }), target_comment_id: 'target', viewer_pending: [] })
    await flushPromises()

    expect(wrapper.find('[data-comment-id="obsolete-thread"]').exists()).toBe(false)
    expect(wrapper.emitted('target-resolved')).toBeUndefined()
  })
})
