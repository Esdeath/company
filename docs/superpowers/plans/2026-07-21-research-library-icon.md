# Research Library Icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved B1 research-lens icon to the public site's browser metadata, mobile application assets, and masthead.

**Architecture:** Keep one hand-editable SVG in `apps/web/public/` as the visual source, generate checked-in PNG and ICO derivatives with ImageMagick, and expose the asset set through Nuxt head metadata plus a small Web App Manifest. The masthead references the same SVG directly so the browser, installed icon, and on-page brand remain visually consistent.

**Tech Stack:** Nuxt 4.4.8, Vue 3.5.40, TypeScript 5.9.3, Vitest 4.1.10, SVG, ImageMagick 7

## Global Constraints

- Use the approved B1 “deep-green research lens” pure-symbol direction.
- Use `#285541` for the background, `#fbfcfa` for the lens and document lines, and `#b9503d` for the discovery dot.
- Do not add text, letters, gradients, shadows, or fine decoration inside the icon.
- Keep all public-site assets under `apps/web/public/`.
- Do not change the Admin branding, site typography, page palette, or workspace layout.
- Keep the icon legible at 16px and prevent masthead overlap at a 320px viewport.

---

### Task 1: Create and verify the icon asset set

**Files:**
- Create: `apps/web/tests/branding.test.ts`
- Create: `apps/web/public/icon.svg`
- Create: `apps/web/public/favicon-16x16.png`
- Create: `apps/web/public/favicon-32x32.png`
- Create: `apps/web/public/favicon.ico`
- Create: `apps/web/public/apple-touch-icon.png`
- Create: `apps/web/public/icon-192.png`
- Create: `apps/web/public/icon-512.png`
- Create: `apps/web/public/site.webmanifest`

**Interfaces:**
- Consumes: the approved colors and geometry from the design specification.
- Produces: stable public URLs `/icon.svg`, `/favicon.ico`, `/favicon-16x16.png`, `/favicon-32x32.png`, `/apple-touch-icon.png`, `/icon-192.png`, `/icon-512.png`, and `/site.webmanifest`.

- [ ] **Step 1: Write the failing asset contract test**

Create `apps/web/tests/branding.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the test and verify that assets are missing**

Run:

```bash
corepack pnpm --filter @company/web test -- branding.test.ts
```

Expected: FAIL with `ENOENT` for `apps/web/public/icon.svg`.

- [ ] **Step 3: Add the SVG source and web manifest**

Create `apps/web/public/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="企业研究资料库">
  <rect width="128" height="128" rx="28" fill="#285541"/>
  <circle cx="56" cy="54" r="29" fill="none" stroke="#fbfcfa" stroke-width="11"/>
  <path d="m77 76 25 25" fill="none" stroke="#fbfcfa" stroke-width="11" stroke-linecap="round"/>
  <path d="M40 47h32M40 58h23M40 69h15" fill="none" stroke="#fbfcfa" stroke-width="5" stroke-linecap="round"/>
  <circle cx="78" cy="32" r="8" fill="#b9503d"/>
</svg>
```

Create `apps/web/public/site.webmanifest`:

```json
{
  "name": "企业研究资料库",
  "short_name": "研究资料库",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f4f6f3",
  "theme_color": "#285541",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 4: Generate deterministic raster derivatives**

Run from the repository root:

```bash
magick -background none -density 384 apps/web/public/icon.svg -resize 16x16 apps/web/public/favicon-16x16.png
magick -background none -density 384 apps/web/public/icon.svg -resize 32x32 apps/web/public/favicon-32x32.png
magick apps/web/public/favicon-16x16.png apps/web/public/favicon-32x32.png apps/web/public/favicon.ico
magick -background none -density 384 apps/web/public/icon.svg -resize 180x180 apps/web/public/apple-touch-icon.png
magick -background none -density 384 apps/web/public/icon.svg -resize 192x192 apps/web/public/icon-192.png
magick -background none -density 384 apps/web/public/icon.svg -resize 512x512 apps/web/public/icon-512.png
```

Expected: ImageMagick exits 0 and creates six raster files under `apps/web/public/`.

- [ ] **Step 5: Run the asset contract test**

Run:

```bash
corepack pnpm --filter @company/web test -- branding.test.ts
```

Expected: `branding.test.ts` passes the SVG, five PNG dimensions, ICO, and manifest checks.

- [ ] **Step 6: Commit the asset set**

```bash
git add apps/web/public apps/web/tests/branding.test.ts
git commit -m "feat: add research library icon assets"
```

### Task 2: Connect branding metadata and masthead UI

**Files:**
- Modify: `apps/web/tests/branding.test.ts`
- Modify: `apps/web/tests/app.test.ts`
- Modify: `apps/web/nuxt.config.ts`
- Modify: `apps/web/app/app.vue`
- Modify: `apps/web/app/assets/css/main.css`

**Interfaces:**
- Consumes: the stable public URLs produced by Task 1.
- Produces: Nuxt head metadata for browser/mobile discovery and a decorative `.brand__mark` image in the existing homepage link.

- [ ] **Step 1: Add failing tests for head metadata and masthead markup**

Append this case to `apps/web/tests/branding.test.ts`:

```ts
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
```

Append this case inside the existing `describe('公开资料阅读工作台', ...)` block in `apps/web/tests/app.test.ts`:

```ts
it('shows the decorative brand mark inside the existing homepage link', async () => {
  const wrapper = await mountWorkspace()
  const brand = wrapper.get('a.brand')
  const mark = brand.get('img.brand__mark')

  expect(mark.attributes()).toMatchObject({
    src: '/icon.svg',
    alt: '',
    'aria-hidden': 'true',
    width: '32',
    height: '32',
  })
  expect(brand.text()).toContain('企业研究资料库')
})
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
corepack pnpm --filter @company/web test -- branding.test.ts app.test.ts
```

Expected: FAIL because `nuxt.config.ts` lacks icon links and `a.brand` lacks `img.brand__mark`.

- [ ] **Step 3: Register Nuxt head metadata**

Add this `app` block to `defineNuxtConfig` in `apps/web/nuxt.config.ts`:

```ts
app: {
  head: {
    link: [
      { rel: 'icon', type: 'image/svg+xml', href: '/icon.svg' },
      { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
      { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/favicon-16x16.png' },
      { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32x32.png' },
      { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' },
      { rel: 'manifest', href: '/site.webmanifest' },
    ],
    meta: [{ name: 'theme-color', content: '#285541' }],
  },
},
```

- [ ] **Step 4: Add the decorative masthead icon**

Replace the current brand link body in `apps/web/app/app.vue` with:

```vue
<a class="brand" href="/" aria-label="企业研究资料库首页">
  <img
    class="brand__mark"
    src="/icon.svg"
    alt=""
    aria-hidden="true"
    width="32"
    height="32"
  />
  <span class="brand__copy">
    <span class="brand__name">企业研究资料库</span>
    <span class="brand__note">Company research library</span>
  </span>
</a>
```

Replace the existing `.brand` rule and add mark/copy rules in `apps/web/app/assets/css/main.css`:

```css
.brand {
  display: grid;
  min-width: 0;
  grid-template-columns: 2rem minmax(0, 1fr);
  align-items: center;
  gap: 0.65rem;
  text-decoration: none;
}

.brand__mark {
  display: block;
  width: 2rem;
  height: 2rem;
}

.brand__copy {
  display: grid;
  min-width: 0;
  gap: 0.12rem;
}
```

- [ ] **Step 5: Run focused tests and the full Web check**

Run:

```bash
corepack pnpm --filter @company/web test -- branding.test.ts app.test.ts
corepack pnpm --filter @company/web check
```

Expected: focused tests pass; lint, typecheck, all Vitest tests, and the Nuxt production build exit 0.

- [ ] **Step 6: Verify responsive rendering in a real browser**

Start the existing Web dev server:

```bash
corepack pnpm --filter @company/web dev
```

Use the browser against `http://127.0.0.1:3000/` at 320x800 and 1280x800. Verify the SVG loads, the icon is 32x32, the masthead text does not overlap the right-hand note, and no horizontal scrollbar appears. Inspect `/favicon.ico`, `/apple-touch-icon.png`, `/icon-192.png`, `/icon-512.png`, and `/site.webmanifest`; each request must return HTTP 200.

- [ ] **Step 7: Commit the integration**

```bash
git add apps/web/nuxt.config.ts apps/web/app/app.vue apps/web/app/assets/css/main.css apps/web/tests/app.test.ts apps/web/tests/branding.test.ts
git commit -m "feat: integrate public-site brand icon"
```
