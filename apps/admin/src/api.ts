import type {
  AuthState,
  Company,
  CompanyInput,
  DocumentItem,
  LoginInput,
  UploadBatch,
} from './types'

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

let csrfToken = ''

export class AuthenticationRequiredError extends Error {}

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

export function deleteDocument(documentId: string, fetcher: Fetcher = fetch): Promise<void> {
  return request(`/api/v1/documents/${documentId}`, { method: 'DELETE' }, fetcher)
}
