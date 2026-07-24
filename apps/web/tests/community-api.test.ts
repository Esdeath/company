import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ConflictError,
  RateLimitedError,
  UserAuthenticationRequiredError,
  createComment,
  getUserSession,
  loginUser,
  logoutUser,
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
      .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await getUserSession(fetchMock)
    await loginUser({ email: 'reader@example.com', password: 'password123' }, fetchMock)
    await logoutUser(fetchMock)

    const sessionInit = fetchMock.mock.calls[0]?.[1] as RequestInit
    const loginInit = fetchMock.mock.calls[1]?.[1] as RequestInit
    const logoutInit = fetchMock.mock.calls[2]?.[1] as RequestInit

    expect(sessionInit).toEqual(expect.objectContaining({ credentials: 'same-origin', method: 'GET' }))
    expect(new Headers(loginInit.headers).get('X-CSRF-Token')).toBe('anonymous-challenge')
    expect(new Headers(logoutInit.headers).get('X-CSRF-Token')).toBe('session-csrf')
    expect(logoutInit).toEqual(expect.objectContaining({ credentials: 'same-origin', method: 'POST' }))
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
