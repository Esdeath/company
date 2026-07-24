import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AuthDialog from '../app/components/AuthDialog.vue'

const authenticatedSession = {
  authenticated: true,
  user: {
    id: 'user-1',
    email: 'reader@example.com',
    username: 'reader',
    email_verified_at: '2026-07-23T08:00:00Z',
    first_comment_approved_at: null,
    reply_email_enabled: true,
  },
  csrf_token: 'session-csrf',
  expires_at: '2026-08-23T08:00:00Z',
  registration_enabled: true,
}

const session = vi.hoisted(() => ({
  state: {
    value: {
      authenticated: false,
      user: null,
      csrf_token: 'challenge',
      expires_at: null,
      registration_enabled: true,
    },
  },
  loading: { value: false },
  register: vi.fn(),
  verifyEmail: vi.fn(),
  login: vi.fn(),
  requestReset: vi.fn(),
  confirmReset: vi.fn(),
}))

vi.mock('../app/composables/useUserSession', () => ({
  useUserSession: () => session,
}))

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(AuthDialog, {
    attachTo: document.body,
    props: { open: true, ...props },
  })
}

afterEach(() => {
  document.body.innerHTML = ''
  session.state.value = { ...authenticatedSession, authenticated: false, user: null, csrf_token: 'challenge' }
  for (const callback of Object.values(session)) {
    if (typeof callback === 'function' && 'mockReset' in callback) callback.mockReset()
  }
  vi.restoreAllMocks()
})

describe('AuthDialog', () => {
  it('logs in with labeled native inputs and emits the authenticated session', async () => {
    session.login.mockResolvedValue(authenticatedSession)
    const wrapper = mountDialog()

    await wrapper.get('input[name="email"]').setValue('reader@example.com')
    await wrapper.get('input[name="password"]').setValue('password123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(session.login).toHaveBeenCalledWith({ email: 'reader@example.com', password: 'password123' })
    expect(wrapper.emitted('authenticated')).toEqual([[authenticatedSession]])
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('shows registration-disabled copy or a verification-sent state after registration', async () => {
    session.state.value = { ...session.state.value, registration_enabled: false }
    const disabled = mountDialog()
    expect(disabled.text()).toContain('注册暂未开放')
    expect(disabled.find('button[name="show-register"]').exists()).toBe(false)
    disabled.unmount()

    session.state.value = { ...session.state.value, registration_enabled: true }
    session.register.mockResolvedValue({ message: '请检查邮箱以完成注册' })
    const wrapper = mountDialog()
    await wrapper.get('button[name="show-register"]').trigger('click')
    await wrapper.get('input[name="email"]').setValue('reader@example.com')
    await wrapper.get('input[name="username"]').setValue('reader')
    await wrapper.get('input[name="password"]').setValue('password123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('请检查邮箱以完成注册')
  })

  it('requests a reset and confirms a password-reset token without retaining the password', async () => {
    session.requestReset.mockResolvedValue({ message: '如果该邮箱已注册，我们已发送密码重置邮件' })
    const request = mountDialog()
    await request.get('button[name="show-password-reset"]').trigger('click')
    await request.get('input[name="email"]').setValue('reader@example.com')
    await request.get('form').trigger('submit')
    await flushPromises()
    expect(request.text()).toContain('我们已发送密码重置邮件')
    request.unmount()

    session.confirmReset.mockResolvedValue(authenticatedSession)
    const confirm = mountDialog({ resetToken: 'reset-token' })
    await confirm.get('input[name="password"]').setValue('new-password123')
    await confirm.get('input[name="confirm-password"]').setValue('new-password123')
    await confirm.get('form').trigger('submit')
    await flushPromises()

    expect(session.confirmReset).toHaveBeenCalledWith({ token: 'reset-token', password: 'new-password123' })
    expect(confirm.emitted('authenticated')).toEqual([[authenticatedSession]])
  })

  it('shows field errors and busy state, then closes with Escape and restores focus', async () => {
    const trigger = document.createElement('button')
    document.body.append(trigger)
    trigger.focus()
    session.login.mockRejectedValue(new Error('邮箱或密码错误'))
    const wrapper = mountDialog()

    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('input[name="email"]').element)
    await wrapper.get('input[name="email"]').setValue('reader@example.com')
    await wrapper.get('input[name="password"]').setValue('password123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('邮箱或密码错误')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(document.activeElement).toBe(trigger)
  })
})
