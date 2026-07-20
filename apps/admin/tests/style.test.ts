import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const stylesheet = readFileSync('src/style.css', 'utf8')

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
})
