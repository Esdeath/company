import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'app/assets/css/main.css'), 'utf8')
const app = readFileSync(resolve(process.cwd(), 'app/app.vue'), 'utf8')

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const matches = [...css.matchAll(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`, 'g'))]
  return matches.map((match) => match[1]).join('\n')
}

describe('公开资料阅读工作台布局', () => {
  it('lets the outer page scroll and keeps a stable reader viewport', () => {
    expect(rule('.site-shell')).toContain('min-height: 100svh')
    expect(rule('.site-shell')).not.toMatch(/(?:^|\n)\s*height:\s*100svh/)
    expect(rule('.document-reader')).toContain('height: clamp(32rem, 72svh, 58rem)')
    expect(rule('.document-reader')).toContain('overflow: hidden')
    expect(rule('.document-frame')).toContain('height: 100%')
  })

  it('places an unframed comment band after the reader in the reading column', () => {
    expect(app).toMatch(/class="reading-column"[\s\S]*<DocumentReader[\s\S]*<CommentSection/)
    expect(rule('.comment-band')).toContain('border: 0')
  })

  it('bounds the sticky directory and prevents horizontal overflow at 320px', () => {
    expect(rule('html,\nbody')).toContain('overflow-x: hidden')
    expect(rule('.library-workspace')).toContain('min-width: 0')
    expect(rule('.reading-column')).toContain('min-width: 0')
    expect(rule('.library-directory')).toContain('max-height: calc(100svh - 3rem)')
    expect(css).not.toMatch(/font-size:\s*[^;]*(vw|svw)/)
    const letterSpacingValues = [...css.matchAll(/letter-spacing:\s*([^;}]+)/g)]
      .map((match) => match[1]?.trim())
    expect(new Set(letterSpacingValues)).toEqual(new Set(['0']))
  })
})
