import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DocumentList from '../src/components/DocumentList.vue'
import type { DocumentItem } from '../src/types'

const documents: DocumentItem[] = [
  {
    id: 'document-1',
    company_id: 'company-1',
    title: '第一份资料',
    format: 'markdown',
    original_filename: 'first.md',
    sort_order: 0,
    uploaded_at: '2026-07-20T08:00:00Z',
    content_url: '/api/v1/documents/document-1/content',
  },
  {
    id: 'document-2',
    company_id: 'company-1',
    title: '第二份资料',
    format: 'html',
    original_filename: 'second.html',
    sort_order: 1,
    uploaded_at: '2026-07-21T08:00:00Z',
    content_url: '/api/v1/documents/document-2/content',
  },
  {
    id: 'document-3',
    company_id: 'company-1',
    title: '第三份资料',
    format: 'markdown',
    original_filename: 'third.md',
    sort_order: 2,
    uploaded_at: '2026-07-22T08:00:00Z',
    content_url: '/api/v1/documents/document-3/content',
  },
]

function mountList(busy = false, items = documents) {
  return mount(DocumentList, {
    props: { documents: items, busy, pendingIds: [] },
  })
}

describe('DocumentList ordering', () => {
  it('disables moves that would pass the first or last position', () => {
    const wrapper = mountList()

    expect(wrapper.get('button[aria-label="上移 第一份资料"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="下移 第一份资料"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('button[aria-label="上移 第三份资料"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('button[aria-label="下移 第三份资料"]').attributes('disabled')).toBeDefined()
  })

  it('moves a document down and emits the complete order', async () => {
    const wrapper = mountList()

    await wrapper.get('button[aria-label="下移 第一份资料"]').trigger('click')

    expect(wrapper.emitted('reorder')).toEqual([[['document-2', 'document-1', 'document-3']]])
    expect(wrapper.get('[role="status"]').text()).toContain('已移到第 2 项')
  })

  it('moves a document up and emits the complete order', async () => {
    const wrapper = mountList()

    await wrapper.get('button[aria-label="上移 第三份资料"]').trigger('click')

    expect(wrapper.emitted('reorder')).toEqual([[['document-1', 'document-3', 'document-2']]])
    expect(wrapper.get('[role="status"]').text()).toContain('已移到第 2 项')
  })

  it('disables both order buttons for a single document', () => {
    const wrapper = mountList(false, [documents[0]!])

    expect(wrapper.get('button[aria-label="上移 第一份资料"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="下移 第一份资料"]').attributes('disabled')).toBeDefined()
  })

  it('disables all order buttons while the document list is busy', async () => {
    const wrapper = mountList(true)
    const orderButtons = wrapper.findAll('.document-order-button')

    expect(orderButtons).toHaveLength(6)
    expect(orderButtons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    await orderButtons[1]!.trigger('click')
    expect(wrapper.emitted('reorder')).toBeUndefined()
  })

  it('does not reorder when rename or delete controls are used', async () => {
    const wrapper = mountList()

    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await wrapper.get('button[aria-label="删除 第一份资料"]').trigger('click')

    expect(wrapper.emitted('reorder')).toBeUndefined()
  })
})
