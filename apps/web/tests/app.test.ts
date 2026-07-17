import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '../app/app.vue'

describe('public application shell', () => {
  it('identifies the public engineering shell with one page title', () => {
    const wrapper = mount(App)
    const headings = wrapper.findAll('h1')

    expect(headings).toHaveLength(1)
    expect(headings[0]?.text()).toBe('企业研究资料库')
    expect(wrapper.text()).toContain('公开端工程骨架')
  })

  it('provides the management boundary entry', () => {
    const wrapper = mount(App)

    expect(wrapper.get('a[href="/admin/"]').text()).toContain('管理端')
  })

  it('does not include placeholder business claims', () => {
    const text = mount(App).text()

    expect(text).not.toContain('贵州茅台')
    expect(text).not.toContain('哔哩哔哩')
    expect(text).not.toContain('估值结论')
  })
})
