export const FRAME_FALLBACK_HEIGHT = 'clamp(32rem, 72svh, 58rem)'

export function readFrameContentHeight(frame: HTMLIFrameElement): number | null {
  try {
    const frameDocument = frame.contentDocument
    const root = frameDocument?.documentElement
    if (!root) return null
    const body = frameDocument.body
    const values = [
      root.scrollHeight,
      root.offsetHeight,
      body?.scrollHeight ?? 0,
      body?.offsetHeight ?? 0,
    ]
    const height = Math.max(...values)
    return Number.isFinite(height) && height > 0 ? Math.ceil(height) : null
  } catch {
    return null
  }
}
