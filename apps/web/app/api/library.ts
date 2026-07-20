import type { Company, DocumentItem } from '../types/content'

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

async function request<T>(url: string, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(url, { method: 'GET' })

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string' && body.detail.trim()) message = body.detail
    } catch {
      // Keep the status fallback when the upstream body is not JSON.
    }
    throw new Error(message)
  }

  return (await response.json()) as T
}

export function listCompanies(fetcher: Fetcher = fetch): Promise<Company[]> {
  return request('/api/v1/companies', fetcher)
}

export function listDocuments(companyId: string, fetcher: Fetcher = fetch): Promise<DocumentItem[]> {
  return request(`/api/v1/companies/${companyId}/documents`, fetcher)
}
