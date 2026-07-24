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
  suspendUser: vi.fn(),
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
    vi.mocked(api.suspendUser).mockReset().mockResolvedValue({ id: comment.author_id, status: 'suspended' })
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
    expect(wrapper.get('.moderation-notice').text()).toContain('内容已由其他操作处理，列表已刷新')
  })

  it('only renders transitions valid for each comment status', async () => {
    vi.mocked(api.listModerationComments)
      .mockResolvedValueOnce({ items: [comment], next_cursor: null })
      .mockResolvedValueOnce({
        items: [
          comment,
          { ...comment, id: 'published', status: 'published' },
          { ...comment, id: 'rejected', status: 'rejected' },
          { ...comment, id: 'deleted', status: 'deleted' },
        ],
        next_cursor: null,
      })
    const wrapper = await mountWorkspace()
    await wrapper.get('#moderation-tab-all').trigger('click')
    await flushPromises()
    const rows = wrapper.findAll('.moderation-row')

    expect(rows[0]!.text()).toContain('通过')
    expect(rows[0]!.text()).toContain('驳回')
    expect(rows[0]!.text()).toContain('停用用户')
    expect(rows[1]!.text()).toContain('移除')
    expect(rows[1]!.text()).toContain('停用用户')
    expect(rows[2]!.find('.moderation-actions').exists()).toBe(false)
    expect(rows[3]!.find('.moderation-actions').exists()).toBe(false)
  })

  it('suspends an eligible comment author and refreshes the active list', async () => {
    const confirmSpy = vi.fn().mockReturnValue(false)
    vi.stubGlobal('confirm', confirmSpy)
    const wrapper = await mountWorkspace()
    await wrapper.get('button[aria-label="停用用户 reader（待审评论）"]').trigger('click')
    expect(confirmSpy).toHaveBeenCalledWith('确认停用用户 reader？其现有登录会话将立即失效。')
    expect(api.suspendUser).not.toHaveBeenCalled()
    confirmSpy.mockReturnValue(true)
    await wrapper.get('button[aria-label="停用用户 reader（待审评论）"]').trigger('click')
    await flushPromises()
    expect(api.suspendUser).toHaveBeenCalledWith('user-1')
    expect(api.listModerationComments).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.moderation-success').text()).toContain('已停用用户 reader')
    expect(wrapper.get('button[aria-label="已停用用户 reader"]').attributes('disabled')).toBeDefined()
  })

  it('keeps the author suspension action available when the request fails', async () => {
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))
    vi.mocked(api.suspendUser).mockRejectedValue(new Error('用户操作失败'))
    const wrapper = await mountWorkspace()
    await wrapper.get('button[aria-label="停用用户 reader（待审评论）"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.moderation-error').text()).toContain('用户操作失败')
    expect(wrapper.get('button[aria-label="停用用户 reader（待审评论）"]').exists()).toBe(true)
  })

  it('clears pending rows before an all-comments request fails', async () => {
    vi.mocked(api.listModerationComments)
      .mockResolvedValueOnce({ items: [comment], next_cursor: null })
      .mockRejectedValueOnce(new Error('全部评论暂不可用'))
    const wrapper = await mountWorkspace()
    await wrapper.get('#moderation-tab-all').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain(comment.body)
    expect(wrapper.get('.moderation-error').text()).toContain('全部评论暂不可用')
    expect(wrapper.get('button[name="retry-moderation"]').exists()).toBe(true)
  })

  it('clears report rows when a report revisit fails', async () => {
    vi.mocked(api.listCommentReports)
      .mockResolvedValueOnce({ items: [report], next_cursor: null })
      .mockRejectedValueOnce(new Error('举报队列暂不可用'))
    const wrapper = await mountWorkspace()
    await wrapper.get('#moderation-tab-reports').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('重复广告')
    await wrapper.get('#moderation-tab-pending').trigger('click')
    await flushPromises()
    await wrapper.get('#moderation-tab-reports').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('重复广告')
    expect(wrapper.get('.moderation-error').text()).toContain('举报队列暂不可用')
  })

  it('keeps a conflict notice visible when the refreshed report list succeeds', async () => {
    vi.mocked(api.isModerationConflict).mockReturnValue(true)
    vi.mocked(api.resolveCommentReport).mockRejectedValue(new Error('内容状态已被其他操作修改'))
    const wrapper = await mountWorkspace()
    await wrapper.get('#moderation-tab-reports').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="保留被举报评论"]').trigger('click')
    await flushPromises()
    expect(api.listCommentReports).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.moderation-notice').text()).toContain('内容已由其他操作处理，列表已刷新')
  })

  it('offers a direct retry after the initial list request fails', async () => {
    vi.mocked(api.listModerationComments)
      .mockRejectedValueOnce(new Error('队列暂不可用'))
      .mockResolvedValueOnce({ items: [comment], next_cursor: null })
    const wrapper = await mountWorkspace()
    expect(wrapper.get('.moderation-error').text()).toContain('队列暂不可用')
    await wrapper.get('button[name="retry-moderation"]').trigger('click')
    await flushPromises()
    expect(api.listModerationComments).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain(comment.body)
  })

  it('supports roving keyboard navigation and focuses the rejection reason after reveal', async () => {
    const wrapper = mount(CommentModeration, { attachTo: document.body })
    await flushPromises()
    const pendingTab = wrapper.get('#moderation-tab-pending')
    await pendingTab.trigger('keydown', { key: 'End' })
    await flushPromises()
    expect(wrapper.get('#moderation-tab-all').element).toBe(document.activeElement)
    expect(wrapper.get('#moderation-tab-all').attributes('aria-controls')).toBe('moderation-panel')

    await wrapper.get('#moderation-tab-pending').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="驳回 评论 reader"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('textarea[name="rejection-reason"]').element).toBe(document.activeElement)
  })

  it('keeps the controlled panel mounted while the list is loading or shows an error', async () => {
    let reject!: (error: Error) => void
    vi.mocked(api.listModerationComments).mockReturnValueOnce(new Promise((_, fail) => { reject = fail }))
    const wrapper = mount(CommentModeration, { attachTo: document.body })
    await flushPromises()
    for (const tab of wrapper.findAll('[role="tab"]')) {
      expect(document.getElementById(tab.attributes('aria-controls') ?? '')).not.toBeNull()
    }
    reject(new Error('队列暂不可用'))
    await flushPromises()
    expect(wrapper.get('#moderation-panel').exists()).toBe(true)
  })

  it('emits an authentication boundary when the administrator session expires', async () => {
    vi.mocked(api.isAuthenticationRequired).mockReturnValue(true)
    vi.mocked(api.listModerationComments).mockRejectedValue(new Error('管理员会话已失效'))
    const wrapper = await mountWorkspace()
    expect(wrapper.emitted('authenticationRequired')).toHaveLength(1)
  })
})
