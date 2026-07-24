import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CommentItem from '../app/components/CommentItem.vue'
import type { Comment } from '../app/types/community'

const COMMENT: Comment = {
  id: 'comment-1',
  document_id: 'document-1',
  parent_id: null,
  body: '第一行\nhttps://example.com/report。',
  status: 'published',
  author: { id: 'user-1', username: '研究员' },
  created_at: '2026-07-24T08:00:00Z',
  edited_at: '2026-07-24T09:00:00Z',
  replies: [],
  can_edit: true,
  can_delete: true,
  can_report: true,
}

function mountItem(comment: Comment = COMMENT) {
  return mount(CommentItem, { props: { comment } })
}

describe('CommentItem', () => {
  it('uses semantic comment markup and safe text/link nodes', () => {
    const wrapper = mountItem()

    expect(wrapper.get('article').attributes('data-comment-id')).toBe('comment-1')
    expect(wrapper.get('time').attributes('datetime')).toBe(COMMENT.created_at)
    expect(wrapper.get('a').attributes()).toMatchObject({
      href: 'https://example.com/report',
      target: '_blank',
      rel: 'noopener noreferrer',
    })
    expect(wrapper.html()).not.toContain('v-html')
    expect(wrapper.text()).toContain('已编辑')
  })

  it('shows distinct pending, deleted, and anonymized states', () => {
    const pending = mountItem({ ...COMMENT, status: 'pending' })
    expect(pending.text()).toContain('待审核')

    const deleted = mountItem({ ...COMMENT, status: 'deleted', body: null })
    expect(deleted.text()).toContain('此评论已删除')
    expect(deleted.find('button[name="reply-comment-1"]').attributes('disabled')).toBeDefined()

    const anonymized = mountItem({ ...COMMENT, author: { id: null, username: '任何值' } })
    expect(anonymized.text()).toContain('已注销用户')
  })

  it('emits command UUIDs and confirms deletion', async () => {
    const wrapper = mountItem()

    await wrapper.get('button[name="reply-comment-1"]').trigger('click')
    await wrapper.get('button[name="edit-comment-1"]').trigger('click')
    await wrapper.get('button[name="report-comment-1"]').trigger('click')
    await wrapper.get('button[name="delete-comment-1"]').trigger('click')
    expect(wrapper.emitted('delete')).toBeUndefined()
    await wrapper.get('button[name="confirm-delete-comment-1"]').trigger('click')

    expect(wrapper.emitted('reply')).toEqual([['comment-1']])
    expect(wrapper.emitted('edit')).toEqual([['comment-1']])
    expect(wrapper.emitted('report')).toEqual([['comment-1']])
    expect(wrapper.emitted('delete')).toEqual([['comment-1']])
  })

  it('renders replies in a nested ordered list without allowing a second reply level', () => {
    const wrapper = mountItem({
      ...COMMENT,
      replies: [{ ...COMMENT, id: 'reply-1', parent_id: 'comment-1', can_edit: false, can_delete: false }],
    })

    expect(wrapper.get('ol').element.tagName).toBe('OL')
    expect(wrapper.find('ol ol').exists()).toBe(false)
  })
})
