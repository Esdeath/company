import { describe, expect, it, vi } from 'vitest'

import {
  createCompany,
  deleteDocument,
  listCompanies,
  listDocuments,
  renameDocument,
  uploadDocuments,
} from '../src/api'

describe('management API client', () => {
  it('lists companies from the versioned API', async () => {
    const companies = [{ id: 'company-1', name: '山河研究', ticker: null, market: null }]
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(companies)))

    await expect(listCompanies(fetchMock)).resolves.toEqual(companies)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/companies', expect.objectContaining({ method: 'GET' }))
  })

  it('creates a company with optional market identity fields', async () => {
    const company = { id: 'company-1', name: '山河研究', ticker: '600001', market: '上交所' }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(company), { status: 201, headers: { 'Content-Type': 'application/json' } }),
    )

    await createCompany({ name: '山河研究', ticker: '600001', market: '上交所' }, fetchMock)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/companies',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: '山河研究', ticker: '600001', market: '上交所' }),
      }),
    )
  })

  it('uploads all selected files under one company', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], errors: [] })))
    const files = [new File(['# Talk'], 'talk.md'), new File(['<title>Page</title>'], 'page.html')]

    await uploadDocuments('company-1', files, fetchMock)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/companies/company-1/documents')
    expect(init.method).toBe('POST')
    expect([...(init.body as FormData).getAll('files')]).toEqual(files)
  })

  it('uses full document routes for refresh, rename, and delete', async () => {
    const document = {
      id: 'document-1',
      company_id: 'company-1',
      title: '年度报告',
      format: 'markdown',
      original_filename: 'annual.md',
      uploaded_at: '2026-07-20T08:00:00Z',
      content_url: '/api/v1/documents/document-1/content',
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([document])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...document, title: '年度复盘' })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await listDocuments('company-1', fetchMock)
    await renameDocument('document-1', '年度复盘', fetchMock)
    await deleteDocument('document-1', fetchMock)

    expect(fetchMock.mock.calls).toEqual([
      ['/api/v1/companies/company-1/documents', expect.objectContaining({ method: 'GET' })],
      [
        '/api/v1/documents/document-1',
        expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ title: '年度复盘' }) }),
      ],
      ['/api/v1/documents/document-1', expect.objectContaining({ method: 'DELETE' })],
    ])
  })

  it('surfaces a useful API error message', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: '公司不存在' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(listDocuments('missing', fetchMock)).rejects.toThrow('公司不存在')
  })

  it('keeps the status fallback for FastAPI validation detail arrays', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            {
              type: 'missing',
              loc: ['body', 'name'],
              msg: 'Field required',
              input: {},
            },
          ],
        }),
        { status: 422, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    await expect(listCompanies(fetchMock)).rejects.toThrow('请求失败（422）')
  })
})
