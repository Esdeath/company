import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as community from '../app/api/community'
import NotificationMenu from '../app/components/NotificationMenu.vue'
import type { Notification } from '../app/types/community'

vi.mock('../app/api/community', () => ({
  listNotifications: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 'notification-1',
    type: 'reply',
    company_id: 'company-1',
    document_id: 'document-1',
    comment_id: 'comment-1',
    actor_username: '研究读者',
    excerpt: '这是一条回复',
    message: '研究读者回复了你的评论',
    created_at: '2026-07-24T08:00:00Z',
    read_at: null,
    ...overrides,
  }
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('NotificationMenu', () => {
  it('shows unread count, links to the target, and marks one notification read', async () => {
    const navigate = vi.spyOn(window.location, 'assign').mockImplementation(() => undefined)
    vi.mocked(community.listNotifications).mockResolvedValue({
      items: [notification()],
      unread_count: 1,
    })
    vi.mocked(community.markNotificationRead).mockResolvedValue(
      notification({ read_at: '2026-07-24T09:00:00Z' }),
    )
    const wrapper = mount(NotificationMenu)
    await flushPromises()

    expect(wrapper.get('button[aria-label="通知，1 条未读"]').text()).toContain('1')
    await wrapper.get('button[aria-label="通知，1 条未读"]').trigger('click')
    const link = wrapper.get('a[data-notification-id="notification-1"]')
    expect(link.attributes('href')).toBe('/?company=company-1&document=document-1&comment=comment-1')
    await link.trigger('click')
    await flushPromises()

    expect(community.markNotificationRead).toHaveBeenCalledWith('notification-1')
    expect(wrapper.emitted('unread-count-changed')?.at(-1)).toEqual([0])
    expect(navigate).toHaveBeenCalledWith('/?company=company-1&document=document-1&comment=comment-1')
    navigate.mockRestore()
  })

  it('marks every notification read and renders empty and retryable error states', async () => {
    vi.mocked(community.listNotifications)
      .mockResolvedValueOnce({ items: [notification(), notification({ id: 'notification-2' })], unread_count: 2 })
      .mockRejectedValueOnce(new Error('通知暂不可用'))
      .mockResolvedValueOnce({ items: [], unread_count: 0 })
    vi.mocked(community.markAllNotificationsRead).mockResolvedValue()
    const wrapper = mount(NotificationMenu)
    await flushPromises()
    await wrapper.get('button[aria-label="通知，2 条未读"]').trigger('click')
    await wrapper.get('button[name="mark-all-notifications-read"]').trigger('click')
    await flushPromises()
    expect(community.markAllNotificationsRead).toHaveBeenCalledOnce()
    expect(wrapper.emitted('unread-count-changed')?.at(-1)).toEqual([0])

    await wrapper.get('button[name="refresh-notifications"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('通知暂不可用')
    await wrapper.get('button[name="retry-notifications"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('还没有通知')
  })

  it('returns focus to its Bell button after Escape closes the menu', async () => {
    vi.mocked(community.listNotifications).mockResolvedValue({ items: [], unread_count: 0 })
    const wrapper = mount(NotificationMenu, { attachTo: document.body })
    await flushPromises()
    const trigger = wrapper.get('button[aria-label="通知"]')
    await trigger.trigger('click')
    expect(wrapper.get('[role="menu"]').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
  })
})
