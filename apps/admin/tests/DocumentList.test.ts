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
]

function mountList(busy = false) {
  return mount(DocumentList, {
    props: { documents, busy, pendingIds: [] },
  })
}

function stubRowRects(rows: ReturnType<ReturnType<typeof mountList>['findAll']>) {
  rows.forEach((row, index) => {
    row.element.getBoundingClientRect = () =>
      ({
        top: index * 80,
        bottom: (index + 1) * 80,
        height: 80,
        left: 0,
        right: 600,
        width: 600,
        x: 0,
        y: index * 80,
        toJSON: () => ({}),
      }) as DOMRect
  })
}

describe('DocumentList ordering', () => {
  it('drags a whole row past another row and emits the complete order', async () => {
    const wrapper = mountList()
    const rows = wrapper.findAll('.document-row')
    stubRowRects(rows)

    await rows[0]!.trigger('pointerdown', { button: 0, clientY: 20, pointerId: 7 })
    await rows[0]!.trigger('pointermove', { clientY: 150, pointerId: 7 })

    expect(wrapper.findAll('.document-title').map((node) => node.text())).toEqual([
      '第二份资料',
      '第一份资料',
    ])
    expect(wrapper.get('.document-row--dragging').attributes('data-document-id')).toBe(
      'document-1',
    )

    await rows[0]!.trigger('pointerup', { clientY: 150, pointerId: 7 })

    expect(wrapper.emitted('reorder')).toEqual([[['document-2', 'document-1']]])
    expect(wrapper.get('[role="status"]').text()).toContain('已移到第 2 项')
  })

  it('does not start row dragging from rename or delete controls', async () => {
    const wrapper = mountList()
    const input = wrapper.get('input')
    const deleteButton = wrapper.get('button[aria-label="删除 第一份资料"]')

    await input.trigger('pointerdown', { button: 0, clientY: 20, pointerId: 8 })
    await input.trigger('pointermove', { clientY: 150, pointerId: 8 })
    await input.trigger('pointerup', { clientY: 150, pointerId: 8 })
    await deleteButton.trigger('pointerdown', { button: 0, clientY: 20, pointerId: 9 })
    await deleteButton.trigger('pointermove', { clientY: 150, pointerId: 9 })
    await deleteButton.trigger('pointerup', { clientY: 150, pointerId: 9 })

    expect(wrapper.emitted('reorder')).toBeUndefined()
  })

  it('moves the focused row with Alt and arrow keys', async () => {
    const wrapper = mountList()
    const rows = wrapper.findAll('.document-row')

    await rows[0]!.trigger('keydown', { altKey: true, key: 'ArrowDown' })

    expect(wrapper.emitted('reorder')).toEqual([[['document-2', 'document-1']]])
    expect(wrapper.get('[role="status"]').text()).toContain('已移到第 2 项')
  })

  it('ignores unavailable keyboard moves and all input while busy', async () => {
    const wrapper = mountList(true)
    const rows = wrapper.findAll('.document-row')

    await rows[0]!.trigger('keydown', { altKey: true, key: 'ArrowUp' })
    await rows[0]!.trigger('keydown', { altKey: true, key: 'ArrowDown' })
    await rows[0]!.trigger('pointerdown', { button: 0, clientY: 20, pointerId: 10 })
    await rows[0]!.trigger('pointermove', { clientY: 150, pointerId: 10 })
    await rows[0]!.trigger('pointerup', { clientY: 150, pointerId: 10 })

    expect(wrapper.emitted('reorder')).toBeUndefined()
  })
})
