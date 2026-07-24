import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommentModeration from '../src/components/CommentModeration.vue'
import * as api from '../src/api'
import type { ModerationComment, ModerationReport } from '../src/types'

vi.mock('../src/api', () => ({
  approveComment: vi.fn(),
  isAuthenticationRequired: vi.fn(() => false),
  isModerationConflict: vi.fn(() => false),
  listCommentReports: vi.fn(),
  listModerationComments: vi.fn(),
  rejectComment: vi.fn(),
  removeComment: vi.fn(),
  resolveCommentReport: vi.fn(),
}))

const comment: ModerationComment = {
  id: 'comment-1', document_id: 'document-1', document_title: '年度报告', author_id: 'user-1',
  author_username: 'reader', parent_id: null, body: '请补充现金流数据。', status: 'pending',
  created_at: '2026-07-21T20:00:00Z', edited_at: null, moderated_at: null, deleted_at: null,
  moderation_reason: null, moderated_by: null,
}

const report: ModerationReport = {
  id: 'report-1', comment_id: comment.id, reporter_id: 'user-2', reporter_username: 'reporter',
  reason: 'spam', details: '重复广告', status: 'open', created_at: '2026-07-21T21:00:00Z',
  resolved_at: null, resolved_by: null, comment,
}

async function mountWorkspace() {
  const wrapper = mount(CommentModeration)
  await flushPromises()
  return wrapper
}

describe('评论审核工作台', () => {
  beforeEach(() => {
    vi.mocked(api.listModerationComments).mockReset().mockResolvedValue({ items: [comment], next_cursor: 'more' })
    vi.mocked(api.listCommentReports).mockReset().mockResolvedValue({ items: [report], next_cursor: null })
    vi.mocked(api.approveComment).mockReset().mockResolvedValue({ ...comment, status: 'published' })
    vi.mocked(api.rejectComment).mockReset().mockResolvedValue({ ...comment, status: 'rejected' })
    vi.mocked(api.removeComment).mockReset().mockResolvedValue({ ...comment, status: 'deleted' })
    vi.mocked(api.resolveCommentReport).mockReset().mockResolvedValue({ ...report, status: 'kept' })
    vi.mocked(api.isAuthenticationRequired).mockReset().mockReturnValue(false)
    vi.mocked(api.isModerationConflict).mockReset().mockReturnValue(false)
  })

  it('starts in pending comments and shows the current page count', async () => {
    const wrapper = await mountWorkspace()
    expect(api.listModerationComments).toHaveBeenCalledWith('pending', undefined)
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toContain('待审')
    expect(wrapper.get('.moderation-count').text()).toContain('1 条')
  })

  it('approves a pending comment and removes it from the current list', async () => {
    const wrapper = await mountWorkspace()
    await wrapper.get('button[aria-label="通过 评论 reader"]').trigger('click')
    await flushPromises()
    expect(api.approveComment).toHaveBeenCalledWith(comment.id)
    expect(wrapper.text()).not.toContain(comment.body)
  })

  it('uses the returned cursor when loading more pending comments', async () => {
    const wrapper = await mountWorkspace()
    await wrapper.get('.moderation-more').trigger('click')
    await flushPromises()
    expect(api.listModerationComments).toHaveBeenLastCalledWith('pending', 'more')
  })

  it('requires a reason before rejecting a comment', async () => {
    const wrapper = await mountWorkspace()
    await wrapper.get('button[aria-label="驳回 评论 reader"]').trigger('click')
    await wrapper.get('form[aria-label="驳回评论"]').trigger('submit')
    expect(api.rejectComment).not.toHaveBeenCalled()
    expect(wrapper.get('.moderation-error').text()).toContain('请填写驳回原因')
    await wrapper.get('textarea[name="rejection-reason"]').setValue('偏离文章主题')
    await wrapper.get('form[aria-label="驳回评论"]').trigger('submit')
    await flushPromises()
    expect(api.rejectComment).toHaveBeenCalledWith(comment.id, '偏离文章主题')
  })

  it('switches to reports and resolves a report as kept', async () => {
    const wrapper = await mountWorkspace()
    await wrapper.get('button[role="tab"][name="report-filter"]').trigger('click')
    await flushPromises()
    expect(api.listCommentReports).toHaveBeenCalledWith('open', undefined)
    await wrapper.get('button[aria-label="保留被举报评论"]').trigger('click')
    await flushPromises()
    expect(api.resolveCommentReport).toHaveBeenCalledWith(report.id, 'kept')

    vi.mocked(api.listCommentReports).mockResolvedValueOnce({ items: [report], next_cursor: null })
    await wrapper.findAll('[role="tab"]')[2]!.trigger('click')
    await flushPromises()
    await wrapper.findAll('[role="tab"]')[1]!.trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="移除被举报评论"]').trigger('click')
    await flushPromises()
    expect(api.resolveCommentReport).toHaveBeenCalledWith(report.id, 'removed')
  })

  it('refreshes active rows after a 409 conflict', async () => {
    vi.mocked(api.isModerationConflict).mockReturnValue(true)
    vi.mocked(api.approveComment).mockRejectedValue(new Error('内容状态已被其他操作修改'))
    const wrapper = await mountWorkspace()
    await wrapper.get('button[aria-label="通过 评论 reader"]').trigger('click')
    await flushPromises()
    expect(api.listModerationComments).toHaveBeenCalledTimes(2)
  })

  it('emits an authentication boundary when the administrator session expires', async () => {
    vi.mocked(api.isAuthenticationRequired).mockReturnValue(true)
    vi.mocked(api.listModerationComments).mockRejectedValue(new Error('管理员会话已失效'))
    const wrapper = await mountWorkspace()
    expect(wrapper.emitted('authenticationRequired')).toHaveLength(1)
  })
})
