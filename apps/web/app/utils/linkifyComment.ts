export type CommentSegment =
  | { type: 'text'; value: string }
  | { type: 'link'; value: string; href: string }

const URL_PATTERN = /https?:\/\/[^\s<>"']+/gi
const TRAILING_PUNCTUATION = /[.,;:!?\]}，。；：！？、】【》）]+$/u

function safeUrl(value: string): string | null {
  const trimmed = value.replace(TRAILING_PUNCTUATION, '')
  if (!trimmed) return null

  try {
    const url = new URL(trimmed)
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || !url.hostname) return null
    return trimmed
  } catch {
    return null
  }
}

export function linkifyComment(text: string): CommentSegment[] {
  const segments: CommentSegment[] = []
  let cursor = 0

  for (const match of text.matchAll(URL_PATTERN)) {
    const rawUrl = match[0]
    const index = match.index ?? cursor
    const beforeMatch = text.slice(0, index)
    const insideHtmlTag = beforeMatch.lastIndexOf('<') > beforeMatch.lastIndexOf('>')
    const href = insideHtmlTag ? null : safeUrl(rawUrl)
    if (!href) continue

    if (index > cursor) segments.push({ type: 'text', value: text.slice(cursor, index) })
    const value = rawUrl.slice(0, href.length)
    segments.push({ type: 'link', value, href })
    cursor = index + value.length
  }

  if (cursor < text.length || segments.length === 0) {
    segments.push({ type: 'text', value: text.slice(cursor) })
  }

  return segments
}
