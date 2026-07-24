import { describe, expect, it } from 'vitest'

import { linkifyComment } from '../app/utils/linkifyComment'

describe('linkifyComment', () => {
  it('preserves text, punctuation boundaries, and line breaks around http links', () => {
    expect(linkifyComment('见 https://example.com/report。\n另见 http://example.org/a?q=1。')).toEqual([
      { type: 'text', value: '见 ' },
      { type: 'link', value: 'https://example.com/report', href: 'https://example.com/report' },
      { type: 'text', value: '。\n另见 ' },
      { type: 'link', value: 'http://example.org/a?q=1', href: 'http://example.org/a?q=1' },
      { type: 'text', value: '。' },
    ])
  })

  it('accepts only well-formed http and https URLs', () => {
    expect(linkifyComment('javascript:alert(1) data:text/html,nope <a href="https://bad">x</a> https://')).toEqual([
      {
        type: 'text',
        value: 'javascript:alert(1) data:text/html,nope <a href="https://bad">x</a> https://',
      },
    ])
  })

  it('does not turn malformed URLs or HTML-looking content into links', () => {
    expect(linkifyComment('https:// example.com https://?q=bad <script>https://example.com</script>')).toEqual([
      { type: 'text', value: 'https:// example.com https://?q=bad <script>' },
      { type: 'link', value: 'https://example.com', href: 'https://example.com' },
      { type: 'text', value: '</script>' },
    ])
  })
})
