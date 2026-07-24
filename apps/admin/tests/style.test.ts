import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const stylesheet = readFileSync('src/style.css', 'utf8')
const task12Components = [
  'src/App.vue',
  'src/components/AdminSectionNav.vue',
  'src/components/CommentModeration.vue',
  'src/components/UserManagement.vue',
].map((file) => readFileSync(file, 'utf8'))

describe('responsive workspace styles', () => {
  it('keeps operational controls in one column below 48rem', () => {
    expect(stylesheet).not.toContain('@media (min-width: 36rem)')
    expect(stylesheet).toMatch(/@media \(min-width: 48rem\)[\s\S]*?\.paired-fields[\s\S]*?grid-template-columns/)
    expect(stylesheet).toMatch(/@media \(min-width: 48rem\)[\s\S]*?\.upload-form[\s\S]*?grid-template-columns/)
    expect(stylesheet).toMatch(/@media \(min-width: 48rem\)[\s\S]*?\.document-actions[\s\S]*?grid-template-columns/)
  })

  it('removes the mobile company selector from desktop layout and tab order', () => {
    expect(stylesheet).toMatch(
      /@media \(min-width: 64rem\)[\s\S]*?\.mobile-company-select\s*\{\s*display:\s*none;/,
    )
  })

  it('keeps Task 12 typography at zero letter spacing', () => {
    expect(stylesheet).toMatch(
      /\.moderation-workspace \.section-label > div > p,[\s\S]*?letter-spacing:\s*0;/,
    )
    expect(stylesheet).toMatch(/\.user-workspace \.section-label > p[\s\S]*?letter-spacing:\s*0;/)
    expect(stylesheet).toMatch(/\.moderation-notice[\s\S]*?letter-spacing:\s*0;/)
    expect(stylesheet).toMatch(/\.moderation-success[\s\S]*?letter-spacing:\s*0;/)
    for (const component of task12Components) expect(component).not.toContain('letter-spacing')
  })
})
