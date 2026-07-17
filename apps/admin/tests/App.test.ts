import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '../src/App.vue'

describe('资料管理后台工程骨架', () => {
  it('清楚标明页面与当前里程碑', () => {
    const wrapper = mount(App)
    const headings = wrapper.findAll('h1')

    expect(headings).toHaveLength(1)
    expect(headings[0]?.text()).toBe('资料管理后台')
    expect(wrapper.text()).toContain('管理端工程骨架')
  })

  it('说明后续能力边界并提供公开端入口', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toContain('登录与资料上传将在后续里程碑实现')
    expect(wrapper.get('a[href="/"]').text()).toContain('返回公开端')
  })

  it('不展示尚未实现的控件或虚构业务内容', () => {
    const wrapper = mount(App)
    const renderedText = wrapper.text()

    expect(wrapper.find('form, input, button, select, textarea').exists()).toBe(false)
    expect(renderedText).not.toContain('用户名')
    expect(renderedText).not.toContain('密码')
    expect(renderedText).not.toContain('贵州茅台')
    expect(renderedText).not.toContain('哔哩哔哩')
    expect(renderedText).not.toContain('估值结论')
  })
})
