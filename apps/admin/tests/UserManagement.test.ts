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
})
