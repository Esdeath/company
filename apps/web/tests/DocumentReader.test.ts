import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DocumentReader from '../app/components/DocumentReader.vue'
import type { DocumentItem } from '../app/types/content'

const DOCUMENT: DocumentItem = {
  id: 'document-1',
  company_id: 'company-1',
  title: '管理层访谈',
  format: 'markdown',
  original_filename: 'interview.md',
  uploaded_at: '2026-07-20T08:00:00Z',
  content_url: '/api/v1/documents/document-1/content',
}

describe('DocumentReader', () => {
  it('uses one isolated iframe for HTML and rendered Markdown', () => {
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })
    const frame = wrapper.get('iframe')

    expect(wrapper.findAll('iframe')).toHaveLength(1)
    expect(frame.attributes('src')).toBe(DOCUMENT.content_url)
    expect(frame.attributes()).toHaveProperty('sandbox', '')
    expect(frame.attributes('title')).toBe('阅读：管理层访谈')
  })

  it('renders progress, error with retry, and empty states without an iframe', async () => {
    const wrapper = mount(DocumentReader, {
      props: { document: null, loading: true, error: null },
    })

    expect(wrapper.get('[role="status"]').text()).toContain('正在读取资料目录')
    expect(wrapper.find('iframe').exists()).toBe(false)

    await wrapper.setProps({ loading: false, error: '资料目录暂不可用' })
    expect(wrapper.get('[role="alert"]').text()).toContain('资料目录暂不可用')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)

    await wrapper.setProps({ error: null, emptyMessage: '这家公司还没有可阅读的资料' })
    expect(wrapper.text()).toContain('这家公司还没有可阅读的资料')
    expect(wrapper.find('iframe').exists()).toBe(false)
  })
})
