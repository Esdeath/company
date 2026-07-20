import { describe, expect, it, vi } from 'vitest'

import { listCompanies, listDocuments } from '../app/api/library'

describe('public library API client', () => {
  it('uses the versioned relative company and document routes', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(JSON.stringify([])))

    await listCompanies(fetchMock)
    await listDocuments('company-1', fetchMock)

    expect(fetchMock.mock.calls).toEqual([
      ['/api/v1/companies', expect.objectContaining({ method: 'GET' })],
      ['/api/v1/companies/company-1/documents', expect.objectContaining({ method: 'GET' })],
    ])
  })

  it('uses a string FastAPI detail and safely falls back for structured details', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: '公司不存在' }), { status: 404 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: [{ msg: 'Field required' }] }), { status: 422 }),
      )

    await expect(listCompanies(fetchMock)).rejects.toThrow('公司不存在')
    await expect(listCompanies(fetchMock)).rejects.toThrow('请求失败（422）')
  })
})
