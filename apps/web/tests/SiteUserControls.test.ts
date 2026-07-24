import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

import AccountDialog from '../app/components/AccountDialog.vue'
import AuthDialog from '../app/components/AuthDialog.vue'
import SiteUserControls from '../app/components/SiteUserControls.vue'
import type { UserAuthState } from '../app/types/community'

const state = ref<UserAuthState | null>(null)
const logout = vi.fn()
const replaceState = vi.fn((next: UserAuthState) => {
  state.value = next
  return next
})

vi.mock('../app/composables/useUserSession', () => ({
  useUserSession: () => ({
    state,
    user: computed(() => state.value?.user ?? null),
    authenticated: computed(() => state.value?.authenticated === true),
    logout,
    replaceState,
  }),
}))

beforeEach(() => {
  state.value = {
    authenticated: false,
    user: null,
    csrf_token: null,
    expires_at: null,
    registration_enabled: true,
  }
})

afterEach(() => {
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

describe('SiteUserControls', () => {
  it('offers an accessible Lucide login entry to anonymous readers', async () => {
    const wrapper = mount(SiteUserControls)
    const login = wrapper.get('button[aria-label="登录"]')
    expect(login.find('svg.lucide-log-in').exists()).toBe(true)
    await login.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('读者账户')
  })

  it('shows Bell, UserRound, Settings, and LogOut controls and logs out', async () => {
    state.value = {
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
    }
    const wrapper = mount(SiteUserControls, {
      global: {
        stubs: {
          NotificationMenu: { template: '<button aria-label="通知"><svg class="lucide-bell" /></button>' },
        },
      },
    })
    expect(wrapper.find('svg.lucide-bell').exists()).toBe(true)
    const account = wrapper.get('button[aria-label="账户：价值读者"]')
    expect(account.find('svg.lucide-user-round').exists()).toBe(true)
    await account.trigger('click')
    expect(wrapper.get('button[name="open-account-settings"]').find('svg.lucide-settings').exists()).toBe(true)
    expect(wrapper.get('button[name="logout-user"]').find('svg.lucide-log-out').exists()).toBe(true)
    await wrapper.get('button[name="logout-user"]').trigger('click')
    await flushPromises()
    expect(logout).toHaveBeenCalledOnce()
  })

  it('returns focus to the user button after Escape closes its menu', async () => {
    state.value = {
      authenticated: true,
      user: {
        id: 'user-1', email: 'reader@example.com', username: '价值读者',
        email_verified_at: null, first_comment_approved_at: null, reply_email_enabled: true,
      },
      csrf_token: 'csrf', expires_at: null, registration_enabled: true,
    }
    const wrapper = mount(SiteUserControls, { attachTo: document.body })
    const account = wrapper.get('button[aria-label="账户：价值读者"]')
    await account.trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(account.element)
  })

  it('focuses the replacement account button after successful login', async () => {
    const wrapper = mount(SiteUserControls, { attachTo: document.body })
    await wrapper.get('button[aria-label="登录"]').trigger('click')
    wrapper.getComponent(AuthDialog).vm.$emit('authenticated', {
      authenticated: true,
      user: {
        id: 'user-1', email: 'reader@example.com', username: '价值读者',
        email_verified_at: null, first_comment_approved_at: null, reply_email_enabled: true,
      },
      csrf_token: 'csrf', expires_at: null, registration_enabled: true,
    })
    await flushPromises()

    const account = wrapper.get('button[aria-label="账户：价值读者"]')
    expect(document.activeElement).toBe(account.element)
  })

  it('focuses the replacement login button after account deletion', async () => {
    state.value = {
      authenticated: true,
      user: {
        id: 'user-1', email: 'reader@example.com', username: '价值读者',
        email_verified_at: null, first_comment_approved_at: null, reply_email_enabled: true,
      },
      csrf_token: 'csrf', expires_at: null, registration_enabled: true,
    }
    const wrapper = mount(SiteUserControls, { attachTo: document.body })
    await wrapper.get('button[aria-label="账户：价值读者"]').trigger('click')
    await wrapper.get('button[name="open-account-settings"]').trigger('click')
    state.value = { ...state.value, authenticated: false, user: null, csrf_token: null, expires_at: null }
    wrapper.getComponent(AccountDialog).vm.$emit('deleted')
    await flushPromises()

    const login = wrapper.get('button[aria-label="登录"]')
    expect(document.activeElement).toBe(login.element)
  })
})
