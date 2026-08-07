import type {
  AuthState,
  CommentStatus,
  Company,
  CompanyInput,
  DocumentItem,
  LoginInput,
  ModerationComment,
  ModerationCommentPage,
  ModerationReport,
  ModerationReportPage,
  ModerationUser,
  ModerationUserPage,
  ReportStatus,
  UploadBatch,
} from './types'

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

let csrfToken = ''

export class AuthenticationRequiredError extends Error {}

export class ModerationConflictError extends Error {}

function authenticatedInit(init: RequestInit): RequestInit {
  const headers = new Headers(init.headers)
  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(init.method ?? 'GET')) {
    headers.set('X-CSRF-Token', csrfToken)
  }
  return { ...init, credentials: 'same-origin', headers }
}

async function request<T>(url: string, init: RequestInit, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(url, authenticatedInit(init))

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string' && body.detail.trim()) message = body.detail
    } catch {
      // Keep the status-based fallback when an upstream response is not JSON.
    }
    if (response.status === 401) throw new AuthenticationRequiredError(message)
    if (response.status === 409) throw new ModerationConflictError(message)
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function rememberAuth(state: AuthState): AuthState {
  csrfToken = state.csrf_token
  return state
}

export async function getSession(fetcher: Fetcher = fetch): Promise<AuthState> {
  const state = await request<AuthState>('/api/v1/auth/session', { method: 'GET' }, fetcher)
  return rememberAuth(state)
}

export async function login(input: LoginInput, fetcher: Fetcher = fetch): Promise<AuthState> {
  const state = await request<AuthState>(
    '/api/v1/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    fetcher,
  )
  return rememberAuth(state)
}

export async function logout(fetcher: Fetcher = fetch): Promise<void> {
  try {
    await request('/api/v1/auth/logout', { method: 'POST' }, fetcher)
  } finally {
    csrfToken = ''
  }
}

export function isAuthenticationRequired(error: unknown): boolean {
  return error instanceof AuthenticationRequiredError
}

export function isModerationConflict(error: unknown): boolean {
  return error instanceof ModerationConflictError
}

export function listCompanies(fetcher: Fetcher = fetch): Promise<Company[]> {
  return request('/api/v1/companies', { method: 'GET' }, fetcher)
}

export function createCompany(input: CompanyInput, fetcher: Fetcher = fetch): Promise<Company> {
  return request(
    '/api/v1/companies',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    fetcher,
  )
}

export function reorderCompanies(
  companyIds: string[],
  fetcher: Fetcher = fetch,
): Promise<Company[]> {
  return request(
    '/api/v1/companies/order',
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_ids: companyIds }),
    },
    fetcher,
  )
}

export function listDocuments(companyId: string, fetcher: Fetcher = fetch): Promise<DocumentItem[]> {
  return request(`/api/v1/companies/${companyId}/documents`, { method: 'GET' }, fetcher)
}

export function uploadDocuments(
  companyId: string,
  files: File[],
  fetcher: Fetcher = fetch,
): Promise<UploadBatch> {
  const body = new FormData()
  for (const file of files) body.append('files', file)

  return request(
    `/api/v1/companies/${companyId}/documents`,
    { method: 'POST', body },
    fetcher,
  )
}

export function renameDocument(
  documentId: string,
  title: string,
  fetcher: Fetcher = fetch,
): Promise<DocumentItem> {
  return request(
    `/api/v1/documents/${documentId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    },
    fetcher,
  )
}

export function reorderDocuments(
  companyId: string,
  documentIds: string[],
  fetcher: Fetcher = fetch,
): Promise<DocumentItem[]> {
  return request(
    `/api/v1/companies/${companyId}/documents/order`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_ids: documentIds }),
    },
    fetcher,
  )
}

export function deleteDocument(documentId: string, fetcher: Fetcher = fetch): Promise<void> {
  return request(`/api/v1/documents/${documentId}`, { method: 'DELETE' }, fetcher)
}

function moderationQuery(values: Record<string, string | undefined>): string {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(values)) {
    if (value) params.set(name, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export function listModerationComments(
  status: CommentStatus | undefined,
  cursor: string | undefined,
  fetcher: Fetcher = fetch,
): Promise<ModerationCommentPage> {
  return request(
    `/api/v1/admin/comments${moderationQuery({ status, cursor })}`,
    { method: 'GET' },
    fetcher,
  )
}

export function approveComment(commentId: string, fetcher: Fetcher = fetch): Promise<ModerationComment> {
  return request(`/api/v1/admin/comments/${commentId}/approve`, { method: 'POST' }, fetcher)
}

export function rejectComment(
  commentId: string,
  reason: string,
  fetcher: Fetcher = fetch,
): Promise<ModerationComment> {
  return request(
    `/api/v1/admin/comments/${commentId}/reject`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason }) },
    fetcher,
  )
}

export function removeComment(commentId: string, fetcher: Fetcher = fetch): Promise<ModerationComment> {
  return request(`/api/v1/admin/comments/${commentId}/remove`, { method: 'POST' }, fetcher)
}

export function listCommentReports(
  status: ReportStatus | undefined,
  cursor: string | undefined,
  fetcher: Fetcher = fetch,
): Promise<ModerationReportPage> {
  return request(
    `/api/v1/admin/comment-reports${moderationQuery({ status, cursor })}`,
    { method: 'GET' },
    fetcher,
  )
}

export function resolveCommentReport(
  reportId: string,
  resolution: Extract<ReportStatus, 'kept' | 'removed'>,
  fetcher: Fetcher = fetch,
): Promise<ModerationReport> {
  return request(
    `/api/v1/admin/comment-reports/${reportId}/resolve`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resolution }) },
    fetcher,
  )
}

export function listModerationUsers(
  query: string,
  cursor: string | undefined,
  fetcher: Fetcher = fetch,
): Promise<ModerationUserPage> {
  return request(`/api/v1/admin/users${moderationQuery({ q: query, cursor })}`, { method: 'GET' }, fetcher)
}

export function suspendUser(userId: string, fetcher: Fetcher = fetch): Promise<ModerationUser> {
  return request(`/api/v1/admin/users/${userId}/suspend`, { method: 'POST' }, fetcher)
}

export function restoreUser(userId: string, fetcher: Fetcher = fetch): Promise<ModerationUser> {
  return request(`/api/v1/admin/users/${userId}/restore`, { method: 'POST' }, fetcher)
}
