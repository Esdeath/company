import { afterEach, describe, expect, it, vi } from 'vitest'

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

const newerSession = {
  ...authenticatedSession,
  user: { ...authenticatedSession.user, username: 'newer-reader' },
  csrf_token: 'newer-csrf',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

async function freshSession() {
  vi.resetModules()
  return import('../app/composables/useUserSession')
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('useUserSession', () => {
  it('deduplicates concurrent restores and exposes the restored user', async () => {
    let resolveResponse!: (response: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () => new Promise<Response>((resolve) => {
          resolveResponse = resolve
        }),
      ),
    )
    const { useUserSession } = await freshSession()
    const session = useUserSession()

    const first = session.restore()
    const second = session.restore()
    resolveResponse(new Response(JSON.stringify(authenticatedSession)))

    await expect(Promise.all([first, second])).resolves.toEqual([authenticatedSession, authenticatedSession])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(session.state.value).toEqual(authenticatedSession)
    expect(session.loading.value).toBe(false)
    await expect(session.requireLogin()).resolves.toBe(true)
  })

  it('does not let a slow restore overwrite a newer login', async () => {
    const slowRestore = deferred<Response>()
    const anonymousChallenge = {
      authenticated: false,
      user: null,
      csrf_token: 'challenge-csrf',
      expires_at: null,
      registration_enabled: true,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockReturnValueOnce(slowRestore.promise)
        .mockResolvedValueOnce(new Response(JSON.stringify(anonymousChallenge)))
        .mockResolvedValueOnce(new Response(JSON.stringify(newerSession))),
    )
    const { useUserSession } = await freshSession()
    const session = useUserSession()

    const restoring = session.restore()
    await expect(session.login({ email: 'reader@example.com', password: 'password-123' })).resolves.toEqual(newerSession)
    slowRestore.resolve(new Response(JSON.stringify(authenticatedSession)))

    await expect(restoring).resolves.toEqual(newerSession)
    expect(session.state.value).toEqual(newerSession)
  })

  it('does not let a slow restore overwrite a newer account mutation', async () => {
    const slowRestore = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(slowRestore.promise))
    const { useUserSession } = await freshSession()
    const session = useUserSession()
    session.replaceState(authenticatedSession)

    const restoring = session.restore()
    session.replaceUser(newerSession.user)
    slowRestore.resolve(new Response(JSON.stringify(authenticatedSession)))

    await expect(restoring).resolves.toMatchObject({ user: newerSession.user })
    expect(session.state.value?.user).toEqual(newerSession.user)
  })

  it('clears the user on a 401 without retaining any caller-owned draft state', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
        .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '会话失效' }), { status: 401 })),
    )
    const { useUserSession } = await freshSession()
    const session = useUserSession()
    const draft = { body: '不要清除这条草稿' }

    await session.restore()
    await expect(session.logout()).rejects.toMatchObject({ name: 'UserAuthenticationRequiredError' })

    expect(session.state.value?.user).toBeNull()
    expect(session.state.value?.authenticated).toBe(false)
    expect(draft.body).toBe('不要清除这条草稿')
  })

  it.each([
    ['a network error', () => Promise.reject(new Error('network unavailable'))],
    ['a server error', () => Promise.resolve(new Response(JSON.stringify({ detail: '服务暂不可用' }), { status: 503 }))],
  ])('keeps the authenticated user when logout fails with %s', async (_label, failedLogout) => {
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
        .mockImplementationOnce(failedLogout),
    )
    const { useUserSession } = await freshSession()
    const session = useUserSession()

    await session.restore()
    await expect(session.logout()).rejects.toThrow()

    expect(session.state.value).toEqual(authenticatedSession)
    expect(session.authenticated.value).toBe(true)
  })

  it('clears shared session state when a direct comment request receives a 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
        .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '用户会话已失效，请重新登录' }), { status: 401 })),
    )
    const { useUserSession } = await freshSession()
    const { createComment } = await import('../app/api/community')
    const session = useUserSession()

    await session.restore()
    await expect(createComment('document-1', { body: '保留在调用方的草稿' })).rejects.toMatchObject({
      name: 'UserAuthenticationRequiredError',
    })

    expect(session.state.value?.authenticated).toBe(false)
    expect(session.state.value?.user).toBeNull()
    await expect(session.requireLogin()).resolves.toBe(false)
  })

  it('keeps the user and CSRF when a current-password action returns 422', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify(authenticatedSession)))
        .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '当前密码错误' }), { status: 422 }))
        .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'comment-1' }), { status: 201 })),
    )
    const { useUserSession } = await freshSession()
    const { createComment, deleteAccount } = await import('../app/api/community')
    const session = useUserSession()

    await session.restore()
    await expect(deleteAccount({ password: 'wrong-password' })).rejects.toThrow('当前密码错误')
    await createComment('document-1', { body: '会话仍有效' })

    expect(session.state.value).toEqual(authenticatedSession)
    expect(new Headers((fetch.mock.calls[2]?.[1] as RequestInit).headers).get('X-CSRF-Token')).toBe('session-csrf')
  })
})
