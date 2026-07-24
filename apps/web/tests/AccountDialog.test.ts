import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import * as community from '../app/api/community'
import AccountDialog from '../app/components/AccountDialog.vue'
import type { UserAuthState } from '../app/types/community'

const state = ref<UserAuthState>({
  authenticated: true,
  user: {
    id: 'user-1',
    email: 'reader@example.com',
    username: '价值读者',
    email_verified_at: '2026-07-23T08:00:00Z',
    first_comment_approved_at: null,
    reply_email_enabled: true,
  },
  csrf_token: 'csrf',
  expires_at: '2026-08-23T08:00:00Z',
  registration_enabled: true,
})

vi.mock('../app/composables/useUserSession', () => ({
  useUserSession: () => ({
    state,
    replaceState: (next: UserAuthState) => {
      state.value = next
      return next
    },
    replaceUser: (user: NonNullable<UserAuthState['user']>) => {
      state.value = { ...state.value!, authenticated: true, user }
      return state.value
    },
  }),
}))

vi.mock('../app/api/community', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../app/api/community')>()),
  deleteAccount: vi.fn(),
  updatePassword: vi.fn(),
  updatePreferences: vi.fn(),
  updateProfile: vi.fn(),
}))

beforeEach(() => {
  state.value = {
    ...state.value,
    authenticated: true,
    user: {
      id: 'user-1',
      email: 'reader@example.com',
      username: '价值读者',
      email_verified_at: '2026-07-23T08:00:00Z',
      first_comment_approved_at: null,
      reply_email_enabled: true,
    },
  }
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('AccountDialog', () => {
  it('updates username and displays a cooldown error without closing', async () => {
    vi.mocked(community.updateProfile)
      .mockResolvedValueOnce({ ...state.value.user!, username: '长期读者' })
      .mockRejectedValueOnce(new community.RateLimitedError('用户名每 30 天只能修改一次'))
    const wrapper = mount(AccountDialog, { props: { open: true } })
    await wrapper.get('input[name="username"]').setValue('长期读者')
    await wrapper.get('form[data-account-section="profile"]').trigger('submit')
    await flushPromises()
    expect(community.updateProfile).toHaveBeenCalledWith({ username: '长期读者' })
    expect(state.value.user?.username).toBe('长期读者')

    await wrapper.get('input[name="username"]').setValue('再次改名')
    await wrapper.get('form[data-account-section="profile"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('每 30 天只能修改一次')
    expect(wrapper.get('[role="dialog"]').exists()).toBe(true)
  })

  it('updates password and reply-email preference', async () => {
    const refreshed = { ...state.value, csrf_token: 'new-csrf' }
    vi.mocked(community.updatePassword).mockResolvedValue(refreshed)
    vi.mocked(community.updatePreferences).mockResolvedValue({
      ...state.value.user!,
      reply_email_enabled: false,
    })
    const wrapper = mount(AccountDialog, { props: { open: true } })

    await wrapper.get('input[name="current-password"]').setValue('old-password')
    await wrapper.get('input[name="new-password"]').setValue('new-password')
    await wrapper.get('form[data-account-section="password"]').trigger('submit')
    await flushPromises()
    expect(community.updatePassword).toHaveBeenCalledWith({
      current_password: 'old-password',
      password: 'new-password',
    })
    expect(state.value.csrf_token).toBe('new-csrf')

    await wrapper.get('input[name="reply-email-enabled"]').setValue(false)
    await flushPromises()
    expect(community.updatePreferences).toHaveBeenCalledWith({ reply_email_enabled: false })
    expect(state.value.user?.reply_email_enabled).toBe(false)
  })

  it('restores the reply-email toggle when saving the preference fails', async () => {
    vi.mocked(community.updatePreferences).mockRejectedValueOnce(new Error('偏好保存失败'))
    const wrapper = mount(AccountDialog, { props: { open: true } })
    const toggle = wrapper.get('input[name="reply-email-enabled"]')
    expect((toggle.element as HTMLInputElement).checked).toBe(true)

    await toggle.setValue(false)
    await flushPromises()
    expect(community.updatePreferences).toHaveBeenCalledWith({ reply_email_enabled: false })
    expect((toggle.element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('偏好保存失败')
  })

  it('requires password confirmation before deleting the account', async () => {
    vi.mocked(community.deleteAccount).mockResolvedValue()
    const wrapper = mount(AccountDialog, { props: { open: true } })
    expect(wrapper.get('button[name="delete-account"]').attributes('disabled')).toBeDefined()
    await wrapper.get('input[name="delete-password"]').setValue('confirm-password')
    await wrapper.get('form[data-account-section="delete"]').trigger('submit')
    await flushPromises()

    expect(community.deleteAccount).toHaveBeenCalledWith({ password: 'confirm-password' })
    expect(state.value.authenticated).toBe(false)
    expect(state.value.user).toBeNull()
    expect(wrapper.emitted('deleted')).toHaveLength(1)
  })

  it('returns focus to the opener after Escape closes the dialog', async () => {
    const opener = document.createElement('button')
    document.body.append(opener)
    opener.focus()
    const wrapper = mount(AccountDialog, { props: { open: false }, attachTo: document.body })
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('input[name="username"]').element)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.setProps({ open: false })
    await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(document.activeElement).toBe(opener)
  })
})
