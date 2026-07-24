import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AdminSectionNav from '../src/components/AdminSectionNav.vue'

describe('管理员工作区标签', () => {
  it('uses roving tab stops and emits keyboard-selected sections with matching panels', async () => {
    const wrapper = mount(AdminSectionNav, {
      attachTo: document.body,
      props: { active: 'documents' },
    })
    const documents = wrapper.get('#admin-tab-documents')
    expect(documents.attributes('tabindex')).toBe('0')
    expect(wrapper.get('#admin-tab-comments').attributes('tabindex')).toBe('-1')
    expect(documents.attributes('aria-controls')).toBe('admin-panel-documents')

    await documents.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('select')).toEqual([['comments']])
    expect(wrapper.get('#admin-tab-comments').element).toBe(document.activeElement)

    await wrapper.get('#admin-tab-comments').trigger('keydown', { key: 'Home' })
    expect(wrapper.emitted('select')?.at(-1)).toEqual(['documents'])
  })
})
