import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UserManagement from '../src/components/UserManagement.vue'
import * as api from '../src/api'
import type { ModerationUser } from '../src/types'

vi.mock('../src/api', () => ({
  isAuthenticationRequired: vi.fn(() => false), isModerationConflict: vi.fn(() => false),
  listModerationUsers: vi.fn(), restoreUser: vi.fn(), suspendUser: vi.fn(),
}))

const user: ModerationUser = {
  id: 'user-1', email: 'reader@example.com', username: 'reader', status: 'active',
  email_verified_at: '2026-07-20T20:00:00Z', first_comment_approved_at: null,
  created_at: '2026-07-19T20:00:00Z', comment_count: 3,
}

const pendingVerificationUser: ModerationUser = {
  ...user,
  id: 'user-pending',
  status: 'pending_verification',
  email_verified_at: null,
}

describe('用户管理工作台', () => {
  beforeEach(() => {
    vi.mocked(api.listModerationUsers).mockReset().mockResolvedValue({ items: [user], next_cursor: null })
    vi.mocked(api.suspendUser).mockReset().mockResolvedValue({ ...user, status: 'suspended' })
    vi.mocked(api.restoreUser).mockReset().mockResolvedValue({ ...user, status: 'active' })
    vi.mocked(api.isAuthenticationRequired).mockReset().mockReturnValue(false)
    vi.mocked(api.isModerationConflict).mockReset().mockReturnValue(false)
  })

  it('searches users before showing matching rows', async () => {
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    expect(api.listModerationUsers).toHaveBeenCalledWith('reader', undefined)
    expect(wrapper.text()).toContain('reader@example.com')
  })

  it('uses the returned cursor when loading more user results', async () => {
    vi.mocked(api.listModerationUsers)
      .mockResolvedValueOnce({ items: [user], next_cursor: 'more-users' })
      .mockResolvedValueOnce({ items: [], next_cursor: null })
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    await wrapper.get('.moderation-more').trigger('click')
    await flushPromises()
    expect(api.listModerationUsers).toHaveBeenLastCalledWith('reader', 'more-users')
  })

  it('confirms suspension before changing a user state', async () => {
    const confirmSpy = vi.fn().mockReturnValue(false)
    vi.stubGlobal('confirm', confirmSpy)
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    await wrapper.get('button[aria-label="停用用户 reader"]').trigger('click')
    expect(confirmSpy).toHaveBeenCalledWith('确认停用用户 reader？其现有登录会话将立即失效。')
    expect(api.suspendUser).not.toHaveBeenCalled()
    confirmSpy.mockReturnValue(true)
    await wrapper.get('button[aria-label="停用用户 reader"]').trigger('click')
    await flushPromises()
    expect(api.suspendUser).toHaveBeenCalledWith(user.id)
    expect(wrapper.text()).toContain('已停用')
  })

  it('restores a suspended user', async () => {
    vi.mocked(api.listModerationUsers).mockResolvedValueOnce({ items: [{ ...user, status: 'suspended' }], next_cursor: null })
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    await wrapper.get('button[aria-label="恢复用户 reader"]').trigger('click')
    await flushPromises()
    expect(api.restoreUser).toHaveBeenCalledWith(user.id)
    expect(wrapper.text()).toContain('正常')
  })

  it('shows verification and approval details and omits actions for unverified users', async () => {
    vi.mocked(api.listModerationUsers).mockResolvedValueOnce({
      items: [{ ...user, first_comment_approved_at: '2026-07-22T10:00:00Z' }, pendingVerificationUser],
      next_cursor: null,
    })
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    const rows = wrapper.findAll('.user-row')
    expect(rows[0]!.text()).toContain('邮箱已验证')
    expect(rows[0]!.text()).toContain('首条评论已通过')
    expect(rows[0]!.text()).toContain('2026-07-22T10:00:00Z')
    expect(rows[1]!.text()).toContain('待验证')
    expect(rows[1]!.find('.moderation-actions').exists()).toBe(false)
  })

  it('refreshes users and keeps a conflict notice visible after a typed 409', async () => {
    vi.mocked(api.listModerationUsers).mockResolvedValueOnce({
      items: [{ ...user, status: 'suspended' }],
      next_cursor: null,
    })
    vi.mocked(api.restoreUser).mockRejectedValue(new Error('内容状态已被其他操作修改'))
    vi.mocked(api.isModerationConflict).mockReturnValue(true)
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    await wrapper.get('button[aria-label="恢复用户 reader"]').trigger('click')
    await flushPromises()
    expect(api.listModerationUsers).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.moderation-notice').text()).toContain('内容已由其他操作处理，列表已刷新')
  })

  it('invalidates an in-flight load-more request when the search is cleared', async () => {
    let resolveMore!: (page: { items: ModerationUser[]; next_cursor: string | null }) => void
    const moreRequest = new Promise<{ items: ModerationUser[]; next_cursor: string | null }>((resolve) => {
      resolveMore = resolve
    })
    vi.mocked(api.listModerationUsers)
      .mockResolvedValueOnce({ items: [user], next_cursor: 'more-users' })
      .mockReturnValueOnce(moreRequest)
    const wrapper = mount(UserManagement)
    await wrapper.get('input[name="user-search"]').setValue('reader')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    await flushPromises()
    await wrapper.get('.moderation-more').trigger('click')
    await wrapper.get('input[name="user-search"]').setValue('')
    await wrapper.get('form[aria-label="搜索用户"]').trigger('submit')
    resolveMore({ items: [user], next_cursor: null })
    await flushPromises()
    expect(wrapper.text()).not.toContain('reader@example.com')
    expect(wrapper.find('.moderation-more').exists()).toBe(false)
  })
})
