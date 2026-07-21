import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const webRoot = resolve(import.meta.dirname, '..')
const publicFile = (name: string) => resolve(webRoot, 'public', name)

function pngDimensions(name: string): [number, number] {
  const png = readFileSync(publicFile(name))
  expect(png.subarray(1, 4).toString('ascii')).toBe('PNG')
  return [png.readUInt32BE(16), png.readUInt32BE(20)]
}

describe('public-site brand assets', () => {
  it('keeps the approved colors and symbol-only SVG source', () => {
    const svg = readFileSync(publicFile('icon.svg'), 'utf8')

    expect(svg).toContain('#285541')
    expect(svg).toContain('#fbfcfa')
    expect(svg).toContain('#b9503d')
    expect(svg).not.toMatch(/<text\b/)
  })

  it.each([
    ['favicon-16x16.png', 16],
    ['favicon-32x32.png', 32],
    ['apple-touch-icon.png', 180],
    ['icon-192.png', 192],
    ['icon-512.png', 512],
  ])('publishes %s at %ix%i', (name, size) => {
    expect(pngDimensions(name)).toEqual([size, size])
  })

  it('publishes a multi-size ICO fallback', () => {
    const ico = readFileSync(publicFile('favicon.ico'))

    expect(ico.readUInt16LE(0)).toBe(0)
    expect(ico.readUInt16LE(2)).toBe(1)
    expect(ico.readUInt16LE(4)).toBeGreaterThanOrEqual(2)
  })

  it('describes both installable icon sizes in the web manifest', () => {
    const manifest = JSON.parse(readFileSync(publicFile('site.webmanifest'), 'utf8'))

    expect(manifest).toMatchObject({
      name: '企业研究资料库',
      short_name: '研究资料库',
      theme_color: '#285541',
      background_color: '#f4f6f3',
      display: 'standalone',
    })
    expect(manifest.icons).toEqual([
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
    ])
  })
})
