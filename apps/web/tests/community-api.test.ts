import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ConflictError,
  RateLimitedError,
  UserAuthenticationRequiredError,
  createComment,
  deleteAccount,
  getUserSession,
  loginUser,
  logoutUser,
  unsubscribeEmail,
  verifyEmail,
} from '../app/api/community'

const anonymousSession = {
  authenticated: false,
  user: null,
  csrf_token: 'anonymous-challenge',
  expires_at: null,
  registration_enabled: true,
}

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

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('community API client', () => {
  it('uses same-origin credentials and moves from an anonymous challenge to session CSRF', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(anonymousSession)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...anonymousSession, csrf_token: 'login-challenge' })))
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await getUserSession(fetchMock)
    await loginUser({ email: 'reader@example.com', password: 'password123' }, fetchMock)
    await logoutUser(fetchMock)

    const sessionInit = fetchMock.mock.calls[0]?.[1] as RequestInit
    const loginInit = fetchMock.mock.calls[2]?.[1] as RequestInit
    const logoutInit = fetchMock.mock.calls[3]?.[1] as RequestInit

    expect(sessionInit).toEqual(expect.objectContaining({ credentials: 'same-origin', method: 'GET' }))
    expect(new Headers(loginInit.headers).get('X-CSRF-Token')).toBe('login-challenge')
    expect(new Headers(logoutInit.headers).get('X-CSRF-Token')).toBe('session-csrf')
    expect(logoutInit).toEqual(expect.objectContaining({ credentials: 'same-origin', method: 'POST' }))
  })

  it('gets a fresh anonymous challenge before a first login and every retry', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...anonymousSession, csrf_token: 'challenge-one' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '邮箱或密码错误' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...anonymousSession, csrf_token: 'challenge-two' })))
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))

    await expect(loginUser({ email: 'reader@example.com', password: 'password123' }, fetchMock)).rejects.toBeInstanceOf(UserAuthenticationRequiredError)
    await loginUser({ email: 'reader@example.com', password: 'password123' }, fetchMock)

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/user-auth/session',
      '/api/v1/user-auth/login',
      '/api/v1/user-auth/session',
      '/api/v1/user-auth/login',
    ])
    expect(new Headers((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('challenge-one')
    expect(new Headers((fetchMock.mock.calls[3]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('challenge-two')
  })

  it('refreshes a consumed anonymous challenge before retrying email verification', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...anonymousSession, csrf_token: 'verify-one' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '链接无效或已过期' }), { status: 422 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...anonymousSession, csrf_token: 'verify-two' })))
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))

    await expect(verifyEmail({ token: 'verify-token' }, fetchMock)).rejects.toThrow('链接无效或已过期')
    await verifyEmail({ token: 'verify-token' }, fetchMock)

    expect(new Headers((fetchMock.mock.calls[1]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('verify-one')
    expect(new Headers((fetchMock.mock.calls[3]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('verify-two')
  })

  it('handles 204 responses and clears CSRF even when logout fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '会话失效' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'comment-1' }), { status: 201 }))

    await getUserSession(fetchMock)
    await expect(logoutUser(fetchMock)).rejects.toBeInstanceOf(UserAuthenticationRequiredError)
    await createComment('document-1', { body: '一条评论', parent_id: null }, fetchMock)

    const commentInit = fetchMock.mock.calls[2]?.[1] as RequestInit
    expect(new Headers(commentInit.headers).get('X-CSRF-Token')).toBeNull()
  })

  it('raises typed authentication, conflict, and rate-limit errors', async () => {
    const authentication = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '请登录' }), { status: 401 }),
    )
    const conflict = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '用户名已被使用' }), { status: 409 }),
    )
    const rateLimited = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '请稍后重试' }), { status: 429 }),
    )

    await expect(getUserSession(authentication)).rejects.toBeInstanceOf(UserAuthenticationRequiredError)
    await expect(getUserSession(conflict)).rejects.toBeInstanceOf(ConflictError)
    await expect(getUserSession(rateLimited)).rejects.toBeInstanceOf(RateLimitedError)
  })

  it('retains a valid session CSRF token when account deletion fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '密码错误' }), { status: 422 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'comment-1' }), { status: 201 }))

    await getUserSession(fetchMock)
    await expect(deleteAccount({ password: 'wrong-password' }, fetchMock)).rejects.toThrow('密码错误')
    await createComment('document-1', { body: '仍在登录', parent_id: null }, fetchMock)

    expect(new Headers((fetchMock.mock.calls[2]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('session-csrf')
  })

  it('retains a valid session CSRF token when account deletion cannot reach the server', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'comment-1' }), { status: 201 }))

    await getUserSession(fetchMock)
    await expect(deleteAccount({ password: 'correct-password' }, fetchMock)).rejects.toThrow('network unavailable')
    await createComment('document-1', { body: '会话仍有效', parent_id: null }, fetchMock)

    expect(new Headers((fetchMock.mock.calls[2]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('session-csrf')
  })

  it('unsubscribes with a fresh anonymous challenge or an authenticated session CSRF', async () => {
    const anonymousFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(anonymousSession)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: '已停止接收评论回复邮件' })))
    const authenticatedFetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: '已停止接收评论回复邮件' })))

    await unsubscribeEmail('anonymous-token', anonymousFetch)
    await unsubscribeEmail('session-token', authenticatedFetch)

    expect(new Headers((anonymousFetch.mock.calls[1]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('anonymous-challenge')
    expect(new Headers((authenticatedFetch.mock.calls[1]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('session-csrf')
  })

  it('never reaches browser storage for CSRF or passwords', async () => {
    const localGet = vi.spyOn(Storage.prototype, 'getItem')
    const localSet = vi.spyOn(Storage.prototype, 'setItem')
    const sessionGet = vi.spyOn(Storage.prototype, 'getItem')
    const sessionSet = vi.spyOn(Storage.prototype, 'setItem')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(anonymousSession)))

    await getUserSession(fetchMock)

    expect(localGet).not.toHaveBeenCalled()
    expect(localSet).not.toHaveBeenCalled()
    expect(sessionGet).not.toHaveBeenCalled()
    expect(sessionSet).not.toHaveBeenCalled()
  })
})
