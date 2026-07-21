import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { inflateSync } from 'node:zlib'

import { describe, expect, it } from 'vitest'

const webRoot = resolve(import.meta.dirname, '..')
const publicFile = (name: string) => resolve(webRoot, 'public', name)
const pngSignature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

type Raster = {
  width: number
  height: number
  pixels: Uint8Array
}

function decodePng(png: Buffer): Raster {
  expect(png.subarray(0, 8)).toEqual(pngSignature)

  let offset = 8
  let width = 0
  let height = 0
  const data: Buffer[] = []

  while (offset < png.length) {
    const length = png.readUInt32BE(offset)
    const type = png.subarray(offset + 4, offset + 8).toString('ascii')
    const chunk = png.subarray(offset + 8, offset + 8 + length)
    offset += 12 + length

    if (type === 'IHDR') {
      width = chunk.readUInt32BE(0)
      height = chunk.readUInt32BE(4)
      expect([chunk[8], chunk[9], chunk[12]]).toEqual([8, 6, 0])
    }
    if (type === 'IDAT') data.push(chunk)
    if (type === 'IEND') break
  }

  const stride = width * 4
  const encoded = inflateSync(Buffer.concat(data))
  const pixels = new Uint8Array(stride * height)

  for (let y = 0; y < height; y += 1) {
    const filter = encoded[y * (stride + 1)]
    const rowStart = y * (stride + 1) + 1
    const outputStart = y * stride

    for (let x = 0; x < stride; x += 1) {
      const left = x >= 4 ? pixels[outputStart + x - 4] : 0
      const above = y > 0 ? pixels[outputStart - stride + x] : 0
      const upperLeft = y > 0 && x >= 4 ? pixels[outputStart - stride + x - 4] : 0
      const value = encoded[rowStart + x]
      const predictor = (() => {
        if (filter === 0) return 0
        if (filter === 1) return left
        if (filter === 2) return above
        if (filter === 3) return Math.floor((left + above) / 2)

        const p = left + above - upperLeft
        const pa = Math.abs(p - left)
        const pb = Math.abs(p - above)
        const pc = Math.abs(p - upperLeft)
        return pa <= pb && pa <= pc ? left : pb <= pc ? above : upperLeft
      })()
      pixels[outputStart + x] = (value + predictor) & 0xff
    }
  }

  return { width, height, pixels }
}

function pngRaster(name: string): Raster {
  return decodePng(readFileSync(publicFile(name)))
}

function pngDimensions(name: string): [number, number] {
  const png = readFileSync(publicFile(name))
  expect(png.subarray(1, 4).toString('ascii')).toBe('PNG')
  const { width, height } = decodePng(png)
  return [width, height]
}

function icoRasters(): Raster[] {
  const ico = readFileSync(publicFile('favicon.ico'))
  expect(ico.readUInt16LE(0)).toBe(0)
  expect(ico.readUInt16LE(2)).toBe(1)
  const count = ico.readUInt16LE(4)
  const frames: Raster[] = []

  for (let index = 0; index < count; index += 1) {
    const entry = 6 + index * 16
    const width = ico[entry] || 256
    const height = ico[entry + 1] || 256
    const bytes = ico.readUInt32LE(entry + 8)
    const start = ico.readUInt32LE(entry + 12)
    const frame = ico.subarray(start, start + bytes)

    if (frame.subarray(0, 8).equals(pngSignature)) {
      frames.push(decodePng(frame))
      continue
    }

    expect(frame.readUInt32LE(0), `unsupported ICO frame ${index}`).toBe(40)
    expect(frame.readInt32LE(4)).toBe(width)
    expect(Math.abs(frame.readInt32LE(8)) / 2).toBe(height)
    expect(frame.readUInt16LE(12)).toBe(1)
    expect(frame.readUInt16LE(14)).toBe(32)

    const pixels = new Uint8Array(width * height * 4)
    const pixelStart = 40
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const source = pixelStart + ((height - 1 - y) * width + x) * 4
        const target = (y * width + x) * 4
        pixels[target] = frame[source + 2]
        pixels[target + 1] = frame[source + 1]
        pixels[target + 2] = frame[source]
        pixels[target + 3] = frame[source + 3]
      }
    }
    frames.push({ width, height, pixels })
  }

  return frames
}

function brandPixelCounts({ pixels }: Raster): Record<string, number> {
  const colors = {
    green: [0x28, 0x55, 0x41],
    paperWhite: [0xfb, 0xfc, 0xfa],
    red: [0xb9, 0x50, 0x3d],
  }
  const counts = { green: 0, paperWhite: 0, red: 0 }

  for (let offset = 0; offset < pixels.length; offset += 4) {
    if (pixels[offset + 3] < 240) continue
    for (const [name, color] of Object.entries(colors)) {
      if (color.every((channel, index) => Math.abs(pixels[offset + index] - channel) <= 16)) {
        counts[name as keyof typeof counts] += 1
      }
    }
  }

  return counts
}

function expectBrandRaster(name: string, raster: Raster) {
  const area = raster.width * raster.height
  const counts = brandPixelCounts(raster)
  const thresholds = {
    green: Math.max(8, Math.floor(area * 0.5)),
    paperWhite: Math.max(1, Math.floor(area * 0.04)),
    red: Math.max(1, Math.floor(area * 0.005)),
  }

  for (const [color, minimum] of Object.entries(thresholds)) {
    expect(counts[color as keyof typeof counts], `${name} has insufficient opaque ${color} pixels: ${JSON.stringify(counts)}`).toBeGreaterThanOrEqual(minimum)
  }

  for (const [x, y] of [[0, 0], [raster.width - 1, 0], [0, raster.height - 1], [raster.width - 1, raster.height - 1]]) {
    expect(raster.pixels[(y * raster.width + x) * 4 + 3], `${name} corner (${x}, ${y}) must be transparent`).toBe(0)
  }
}

describe('public-site brand assets', () => {
  it('registers browser, mobile, and manifest metadata in Nuxt', () => {
    const config = readFileSync(resolve(webRoot, 'nuxt.config.ts'), 'utf8')

    for (const href of [
      '/icon.svg',
      '/favicon.ico',
      '/favicon-16x16.png',
      '/favicon-32x32.png',
      '/apple-touch-icon.png',
      '/site.webmanifest',
    ]) {
      expect(config).toContain(`href: '${href}'`)
    }
    expect(config).toContain("content: '#285541'")
  })

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

  it.each([
    'favicon-16x16.png',
    'favicon-32x32.png',
    'apple-touch-icon.png',
    'icon-192.png',
    'icon-512.png',
  ])('renders all approved colors and transparent corners in %s', (name) => {
    expectBrandRaster(name, pngRaster(name))
  })

  it('publishes two branded ICO fallback frames', () => {
    const frames = icoRasters()

    expect(frames).toHaveLength(2)
    expect(frames.map(({ width, height }) => [width, height])).toEqual([[16, 16], [32, 32]])
    frames.forEach((frame, index) => expectBrandRaster(`favicon.ico frame ${index}`, frame))
  })

  it('rejects a raster that omits the paper-white symbol', () => {
    const pixels = new Uint8Array(4 * 4 * 4)
    for (const pixel of [1, 2, 4, 5, 6, 7, 8, 9, 10, 11]) {
      pixels.set([0x28, 0x55, 0x41, 0xff], pixel * 4)
    }
    pixels.set([0xb9, 0x50, 0x3d, 0xff], 5 * 4)

    expect(() => expectBrandRaster('missing-white fixture', { width: 4, height: 4, pixels })).toThrow('paperWhite')
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
