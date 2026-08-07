import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CompanyPicker from '../src/components/CompanyPicker.vue'
import type { Company } from '../src/types'

const companies: Company[] = [
  { id: 'company-1', name: '第一公司', ticker: '0001', market: 'HK', sort_order: 0 },
  { id: 'company-2', name: '第二公司', ticker: '0002', market: 'HK', sort_order: 1 },
  { id: 'company-3', name: '第三公司', ticker: '0003', market: 'HK', sort_order: 2 },
]

function mountPicker(busy = false) {
  return mount(CompanyPicker, {
    props: {
      companies,
      selectedId: 'company-1',
      busy,
      createSuccessKey: 0,
    },
  })
}

describe('CompanyPicker ordering', () => {
  it('disables moves that would pass the first or last position', () => {
    const wrapper = mountPicker()

    expect(wrapper.get('button[aria-label="上移 第一公司"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="下移 第一公司"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('button[aria-label="上移 第三公司"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('button[aria-label="下移 第三公司"]').attributes('disabled')).toBeDefined()
  })

  it('moves a company down and emits the complete order', async () => {
    const wrapper = mountPicker()

    await wrapper.get('button[aria-label="下移 第一公司"]').trigger('click')

    expect(wrapper.emitted('reorder')).toEqual([[['company-2', 'company-1', 'company-3']]])
    expect(wrapper.get('[role="status"]').text()).toContain('已移到第 2 项')
  })

  it('disables all order buttons while the company list is busy', async () => {
    const wrapper = mountPicker(true)
    const orderButtons = wrapper.findAll('.company-order-button')

    expect(orderButtons).toHaveLength(6)
    expect(orderButtons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    await orderButtons[1]!.trigger('click')
    expect(wrapper.emitted('reorder')).toBeUndefined()
  })
})
