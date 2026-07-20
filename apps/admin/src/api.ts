import type { Company, CompanyInput, DocumentItem, UploadBatch } from './types'

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

async function request<T>(url: string, init: RequestInit, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(url, init)

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // Keep the status-based fallback when an upstream response is not JSON.
    }
    throw new Error(message)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
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
