import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'app/assets/css/main.css'), 'utf8')
const app = readFileSync(resolve(process.cwd(), 'app/app.vue'), 'utf8')
const componentsDirectory = resolve(process.cwd(), 'app/components')
const componentStyles = readdirSync(componentsDirectory)
  .filter((name) => name.endsWith('.vue'))
  .map((name) => readFileSync(resolve(componentsDirectory, name), 'utf8'))
  .join('\n')
const notificationMenu = readFileSync(resolve(componentsDirectory, 'NotificationMenu.vue'), 'utf8')

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const matches = [...css.matchAll(new RegExp(`${escaped}\\s*\\{([^}]+)\\}`, 'g'))]
  return matches.map((match) => match[1]).join('\n')
}

describe('公开资料阅读工作台布局', () => {
  it('lets the full article and comments participate in natural page flow', () => {
    expect(rule('.site-shell')).toContain('min-height: 100svh')
    expect(rule('.site-shell')).not.toMatch(/(?:^|\n)\s*height:\s*100svh/)
    expect(rule('.library-workspace')).not.toContain('height: 100%')
    expect(rule('.document-reader')).toContain('min-height: clamp(32rem, 72svh, 58rem)')
    expect(rule('.document-reader')).not.toMatch(/(?:^|\n)\s*height:\s*100%/)
    expect(rule('.document-reader')).toContain('overflow: hidden')
    expect(app).toMatch(/class="reading-column"[\s\S]*<DocumentReader[\s\S]*<CommentSection/)
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

  it('keeps the mobile notification popover inside stable viewport insets', () => {
    expect(notificationMenu).toMatch(
      /@media \(max-width: 35rem\)[\s\S]*\.notification-menu\s*\{[\s\S]*position: fixed;[\s\S]*inset: 4\.75rem 1rem auto;/,
    )
  })

  it('uses zero letter spacing throughout component styles', () => {
    const values = [...componentStyles.matchAll(/letter-spacing:\s*([^;}]+)/g)]
      .map((match) => match[1]?.trim())
    expect(new Set(values)).toEqual(new Set(['0']))
  })
})
