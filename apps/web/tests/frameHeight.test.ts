import { describe, expect, it } from 'vitest'

import {
  FRAME_FALLBACK_HEIGHT,
  readFrameContentHeight,
} from '../app/utils/frameHeight'

function frameWith(root: Partial<HTMLElement>, body: Partial<HTMLElement> | null) {
  return {
    contentDocument: {
      documentElement: root,
      body,
    },
  } as unknown as HTMLIFrameElement
}

describe('iframe content height', () => {
  it('uses the largest root or body layout extent and rounds upward', () => {
    const frame = frameWith(
      { scrollHeight: 1400, offsetHeight: 1390 },
      { scrollHeight: 1450.2, offsetHeight: 1420 },
    )

    expect(readFrameContentHeight(frame)).toBe(1451)
    expect(FRAME_FALLBACK_HEIGHT).toBe('clamp(32rem, 72svh, 58rem)')
  })

  it('returns null for inaccessible or invalid documents', () => {
    const inaccessible = {} as HTMLIFrameElement
    Object.defineProperty(inaccessible, 'contentDocument', {
      get: () => { throw new DOMException('blocked') },
    })

    expect(readFrameContentHeight(inaccessible)).toBeNull()
    expect(readFrameContentHeight(frameWith({ scrollHeight: 0, offsetHeight: 0 }, null))).toBeNull()
  })
})
