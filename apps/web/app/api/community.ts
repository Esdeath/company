import type {
  AccountDeleteInput,
  Comment,
  CommentCreateInput,
  CommentPage,
  CommentReportInput,
  CommentThread,
  CommentUpdateInput,
  Identifier,
  LoginInput,
  MessageResponse,
  Notification,
  NotificationPage,
  PasswordResetConfirmInput,
  PasswordResetRequestInput,
  PasswordUpdateInput,
  PreferencesUpdateInput,
  ProfileUpdateInput,
  RegisterInput,
  User,
  UserAuthState,
  VerifyEmailInput,
} from '../types/community'

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

let csrfToken = ''

export class UserAuthenticationRequiredError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'UserAuthenticationRequiredError'
  }
}

export class ConflictError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ConflictError'
  }
}

export class RateLimitedError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'RateLimitedError'
  }
}

function isSafeMethod(method: string | undefined): boolean {
  return ['GET', 'HEAD', 'OPTIONS'].includes(method ?? 'GET')
}

function withSession(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers)
  if (csrfToken && !isSafeMethod(init.method)) headers.set('X-CSRF-Token', csrfToken)
  return { ...init, credentials: 'same-origin', headers }
}

async function responseMessage(response: Response): Promise<string> {
  const fallback = `请求失败（${response.status}）`
  try {
    const body = (await response.json()) as { detail?: unknown }
    return typeof body.detail === 'string' && body.detail.trim() ? body.detail : fallback
  } catch {
    return fallback
  }
}

async function request<T>(url: string, init: RequestInit, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(url, withSession(init))

  if (!response.ok) {
    const message = await responseMessage(response)
    if (response.status === 401) {
      csrfToken = ''
      throw new UserAuthenticationRequiredError(message)
    }
    if (response.status === 409) throw new ConflictError(message)
    if (response.status === 429) throw new RateLimitedError(message)
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function rememberState(state: UserAuthState): UserAuthState {
  csrfToken = state.csrf_token ?? ''
  return state
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export function getUserSession(fetcher: Fetcher = fetch): Promise<UserAuthState> {
  return request<UserAuthState>('/api/v1/user-auth/session', { method: 'GET' }, fetcher).then(
    rememberState,
  )
}

export function registerUser(input: RegisterInput, fetcher: Fetcher = fetch): Promise<MessageResponse> {
  return request('/api/v1/user-auth/register', jsonInit('POST', input), fetcher)
}

export function verifyEmail(input: VerifyEmailInput, fetcher: Fetcher = fetch): Promise<UserAuthState> {
  return request<UserAuthState>('/api/v1/user-auth/verify-email', jsonInit('POST', input), fetcher).then(
    rememberState,
  )
}

export function loginUser(input: LoginInput, fetcher: Fetcher = fetch): Promise<UserAuthState> {
  return request<UserAuthState>('/api/v1/user-auth/login', jsonInit('POST', input), fetcher).then(
    rememberState,
  )
}

export async function logoutUser(fetcher: Fetcher = fetch): Promise<void> {
  try {
    await request('/api/v1/user-auth/logout', { method: 'POST' }, fetcher)
  } finally {
    csrfToken = ''
  }
}

export function requestPasswordReset(
  input: PasswordResetRequestInput,
  fetcher: Fetcher = fetch,
): Promise<MessageResponse> {
  return request('/api/v1/user-auth/password-reset/request', jsonInit('POST', input), fetcher)
}

export function confirmPasswordReset(
  input: PasswordResetConfirmInput,
  fetcher: Fetcher = fetch,
): Promise<UserAuthState> {
  return request<UserAuthState>(
    '/api/v1/user-auth/password-reset/confirm',
    jsonInit('POST', input),
    fetcher,
  ).then(rememberState)
}

export function getCurrentUser(fetcher: Fetcher = fetch): Promise<User> {
  return request('/api/v1/users/me', { method: 'GET' }, fetcher)
}

export function updateProfile(input: ProfileUpdateInput, fetcher: Fetcher = fetch): Promise<User> {
  return request('/api/v1/users/me/profile', jsonInit('PATCH', input), fetcher)
}

export function updatePassword(
  input: PasswordUpdateInput,
  fetcher: Fetcher = fetch,
): Promise<UserAuthState> {
  return request<UserAuthState>('/api/v1/users/me/password', jsonInit('PATCH', input), fetcher).then(
    rememberState,
  )
}

export function updatePreferences(
  input: PreferencesUpdateInput,
  fetcher: Fetcher = fetch,
): Promise<User> {
  return request('/api/v1/users/me/preferences', jsonInit('PATCH', input), fetcher)
}

export async function deleteAccount(input: AccountDeleteInput, fetcher: Fetcher = fetch): Promise<void> {
  try {
    await request('/api/v1/users/me', jsonInit('DELETE', input), fetcher)
  } finally {
    csrfToken = ''
  }
}

export function listDocumentComments(
  documentId: Identifier,
  cursor?: string | null,
  fetcher: Fetcher = fetch,
): Promise<CommentPage> {
  const search = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  return request(`/api/v1/documents/${documentId}/comments${search}`, { method: 'GET' }, fetcher)
}

export function createComment(
  documentId: Identifier,
  input: CommentCreateInput,
  fetcher: Fetcher = fetch,
): Promise<Comment> {
  return request(`/api/v1/documents/${documentId}/comments`, jsonInit('POST', input), fetcher)
}

export function getCommentThread(commentId: Identifier, fetcher: Fetcher = fetch): Promise<CommentThread> {
  return request(`/api/v1/comments/${commentId}/thread`, { method: 'GET' }, fetcher)
}

export function updateComment(
  commentId: Identifier,
  input: CommentUpdateInput,
  fetcher: Fetcher = fetch,
): Promise<Comment> {
  return request(`/api/v1/comments/${commentId}`, jsonInit('PATCH', input), fetcher)
}

export function deleteComment(commentId: Identifier, fetcher: Fetcher = fetch): Promise<Comment> {
  return request(`/api/v1/comments/${commentId}`, { method: 'DELETE' }, fetcher)
}

export function reportComment(
  commentId: Identifier,
  input: CommentReportInput,
  fetcher: Fetcher = fetch,
): Promise<void> {
  return request(`/api/v1/comments/${commentId}/reports`, jsonInit('POST', input), fetcher)
}

export function listNotifications(fetcher: Fetcher = fetch): Promise<NotificationPage> {
  return request('/api/v1/users/me/notifications', { method: 'GET' }, fetcher)
}

export function markNotificationRead(
  notificationId: Identifier,
  fetcher: Fetcher = fetch,
): Promise<Notification> {
  return request(`/api/v1/users/me/notifications/${notificationId}`, { method: 'PATCH' }, fetcher)
}

export function markAllNotificationsRead(fetcher: Fetcher = fetch): Promise<void> {
  return request('/api/v1/users/me/notifications/read-all', { method: 'POST' }, fetcher)
}

export function unsubscribeEmail(token: string, fetcher: Fetcher = fetch): Promise<MessageResponse> {
  return request('/api/v1/user-auth/unsubscribe', jsonInit('POST', { token }), fetcher)
}

export function isUserAuthenticationRequired(error: unknown): error is UserAuthenticationRequiredError {
  return error instanceof UserAuthenticationRequiredError
}
