import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DocumentReader from '../app/components/DocumentReader.vue'
import type { DocumentItem } from '../app/types/content'
import { FRAME_FALLBACK_HEIGHT } from '../app/utils/frameHeight'

const DOCUMENT: DocumentItem = {
  id: 'document-1',
  company_id: 'company-1',
  title: '管理层访谈',
  format: 'markdown',
  original_filename: 'interview.md',
  sort_order: 0,
  uploaded_at: '2026-07-20T08:00:00Z',
  content_url: '/api/v1/documents/document-1/content',
}

const SECOND_DOCUMENT: DocumentItem = {
  ...DOCUMENT,
  id: 'document-2',
  title: '年度报告',
  sort_order: 1,
  content_url: '/api/v1/documents/document-2/content',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('DocumentReader', () => {
  it('probes content before mounting one isolated iframe and tracks its load', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })

    expect(wrapper.get('[role="status"]').text()).toContain('正在检查资料内容')
    expect(wrapper.find('iframe').exists()).toBe(false)
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      DOCUMENT.content_url,
      expect.objectContaining({ method: 'HEAD', signal: expect.any(AbortSignal) }),
    )
    const frame = wrapper.get('iframe')
    expect(wrapper.findAll('iframe')).toHaveLength(1)
    expect(frame.attributes('src')).toBe(DOCUMENT.content_url)
    expect(frame.attributes('sandbox')).toBe('allow-same-origin')
    expect(wrapper.vm.$.setupState.frameHeight as string).toBe(FRAME_FALLBACK_HEIGHT)
    expect(frame.attributes('title')).toBe('阅读：管理层访谈')
    expect(wrapper.get('[role="status"]').text()).toContain('正在打开资料')

    await frame.trigger('load')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('iframe').exists()).toBe(true)
  })

  it('reports a failed probe and retries the content without asking the parent', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })

    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('资料内容暂不可用（404）')
    expect(wrapper.find('iframe').exists()).toBe(false)

    await wrapper.get('button[name="retry-content"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.get('iframe').attributes('src')).toBe(DOCUMENT.content_url)
    expect(wrapper.emitted('retry')).toBeUndefined()
  })

  it('reports an iframe network error and offers a content retry', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })
    await flushPromises()

    await wrapper.get('iframe').trigger('error')

    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.get('[role="alert"]').text()).toContain('资料页面加载失败')
    expect(wrapper.get('button[name="retry-content"]').exists()).toBe(true)
  })

  it('ignores a stale probe after a rapid document switch', async () => {
    const firstProbe = deferred<Response>()
    const secondProbe = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValueOnce(firstProbe.promise).mockReturnValueOnce(secondProbe.promise),
    )
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })

    await wrapper.setProps({ document: SECOND_DOCUMENT })
    secondProbe.resolve(new Response(null, { status: 200 }))
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe(SECOND_DOCUMENT.content_url)

    firstProbe.resolve(new Response(null, { status: 200 }))
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe(SECOND_DOCUMENT.content_url)
  })

  it('ignores stale iframe load and error events from an earlier generation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })
    await flushPromises()
    const frame = wrapper.get('iframe')
    const currentGeneration = frame.attributes('data-reader-generation')
    frame.element.setAttribute('data-reader-generation', '0')

    await frame.trigger('error')
    await frame.trigger('load')

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('iframe').attributes('src')).toBe(DOCUMENT.content_url)
    expect(wrapper.get('[role="status"]').text()).toContain('正在打开资料')

    frame.element.setAttribute('data-reader-generation', currentGeneration)
    await frame.trigger('load')
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('fits the frame to its document and follows later size changes', async () => {
    const callbacks: ResizeObserverCallback[] = []
    const disconnect = vi.fn()
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: ResizeObserverCallback) {
          callbacks.push(callback)
        }

        observe = vi.fn()
        disconnect = disconnect
      },
    )
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))

    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })
    try {
      await flushPromises()
      const frame = wrapper.get('iframe')
      const root = { scrollHeight: 1800, offsetHeight: 1750 }
      const body = { scrollHeight: 1900, offsetHeight: 1850 }
      Object.defineProperty(frame.element, 'isConnected', {
        configurable: true,
        value: true,
      })
      Object.defineProperty(frame.element, 'contentDocument', {
        configurable: true,
        value: { documentElement: root, body },
      })
      Object.defineProperty(frame.element, 'contentWindow', {
        configurable: true,
        value: { ResizeObserver: globalThis.ResizeObserver },
      })

      await frame.trigger('load')
      expect(frame.element.style.getPropertyValue('height')).toBe('1900px')

      body.scrollHeight = 2400
      callbacks[0]?.([], {} as ResizeObserver)
      await wrapper.vm.$nextTick()
      expect(frame.element.style.getPropertyValue('height')).toBe('2400px')

      await wrapper.setProps({ document: SECOND_DOCUMENT })
      expect(disconnect).toHaveBeenCalledOnce()
    } finally {
      wrapper.unmount()
    }
  })

  it('aborts an unfinished probe when unmounted', () => {
    let signal: AbortSignal | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        signal = init.signal as AbortSignal
        return new Promise<Response>(() => undefined)
      }),
    )
    const wrapper = mount(DocumentReader, {
      props: { document: DOCUMENT, loading: false, error: null },
    })

    wrapper.unmount()

    expect(signal?.aborted).toBe(true)
  })

  it('keeps directory progress, directory retry, and empty states separate', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DocumentReader, {
      props: { document: null, loading: true, error: null },
    })

    expect(wrapper.get('[role="status"]').text()).toContain('正在读取资料目录')
    expect(fetchMock).not.toHaveBeenCalled()

    await wrapper.setProps({ loading: false, error: '资料目录暂不可用' })
    expect(wrapper.get('[role="alert"]').text()).toContain('资料目录暂不可用')
    await wrapper.get('button[name="retry-documents"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)

    await wrapper.setProps({ error: null, emptyMessage: '这家公司还没有可阅读的资料' })
    expect(wrapper.text()).toContain('这家公司还没有可阅读的资料')
    expect(wrapper.find('iframe').exists()).toBe(false)
  })
})
