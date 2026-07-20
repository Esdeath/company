import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import CompanyDirectory from '../app/components/CompanyDirectory.vue'
import type { Company } from '../app/types/content'

const companies: Company[] = [
  {
    id: 'company-1',
    name: '山河研究',
    ticker: '600001',
    market: '上交所',
    created_at: '2026-07-19T08:00:00Z',
  },
  {
    id: 'company-2',
    name: '远望科技',
    ticker: null,
    market: null,
    created_at: '2026-07-20T08:00:00Z',
  },
]

type Unmountable = { unmount: () => void }
const mountedWrappers: Unmountable[] = []

function track<T extends Unmountable>(wrapper: T): T {
  mountedWrappers.push(wrapper)
  return wrapper
}

function unmountTracked(wrapper: Unmountable) {
  wrapper.unmount()
  const index = mountedWrappers.indexOf(wrapper)
  if (index >= 0) mountedWrappers.splice(index, 1)
}

function mediaQueryStub(initialMatches = false) {
  let changeListener: ((event: MediaQueryListEvent) => void) | undefined
  const addEventListener = vi.fn((type: string, listener: (event: MediaQueryListEvent) => void) => {
    if (type === 'change') changeListener = listener
  })
  const removeEventListener = vi.fn()
  const mediaQuery = {
    matches: initialMatches,
    addEventListener,
    removeEventListener,
  }
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue(mediaQuery))
  return {
    addEventListener,
    dispatch(matches: boolean) {
      changeListener?.({ matches } as MediaQueryListEvent)
    },
    mediaQuery,
    removeEventListener,
  }
}

function mountDirectory() {
  return track(
    mount(CompanyDirectory, {
      attachTo: document.body,
      props: { companies, selectedId: 'company-1', loading: false },
    }),
  )
}

describe('CompanyDirectory drawer lifecycle', () => {
  beforeEach(() => {
    mediaQueryStub()
  })

  afterEach(() => {
    for (const wrapper of mountedWrappers.splice(0).reverse()) wrapper.unmount()
    document.body.innerHTML = ''
    document.body.style.overflow = ''
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('leaves unrelated body overflow untouched when unmounted without owning the lock', () => {
    document.body.style.overflow = 'clip'
    const wrapper = mountDirectory()

    unmountTracked(wrapper)

    expect(document.body.style.overflow).toBe('clip')
  })

  it('restores the previous body overflow when closed or unmounted after opening', async () => {
    document.body.style.overflow = 'clip'
    const closedWrapper = mountDirectory()

    await closedWrapper.get('button[name="open-company-drawer"]').trigger('click')
    expect(document.body.style.overflow).toBe('hidden')
    await closedWrapper.get('button[name="close-company-drawer"]').trigger('click')
    expect(document.body.style.overflow).toBe('clip')
    unmountTracked(closedWrapper)
    expect(document.body.style.overflow).toBe('clip')

    document.body.style.overflow = 'auto'
    const unmountedWrapper = mountDirectory()
    await unmountedWrapper.get('button[name="open-company-drawer"]').trigger('click')
    unmountTracked(unmountedWrapper)

    expect(document.body.style.overflow).toBe('auto')
  })

  it('does not overwrite the saved body overflow on repeated open requests', async () => {
    document.body.style.overflow = 'scroll'
    const wrapper = mountDirectory()
    const trigger = wrapper.get('button[name="open-company-drawer"]')

    await trigger.trigger('click')
    await trigger.trigger('click')
    await wrapper.get('button[name="close-company-drawer"]').trigger('click')

    expect(document.body.style.overflow).toBe('scroll')
  })

  it('dismisses on company selection, restores the body, and returns focus', async () => {
    document.body.style.overflow = 'clip'
    const wrapper = mountDirectory()
    const trigger = wrapper.get('button[name="open-company-drawer"]')

    await trigger.trigger('click')
    await wrapper.get('[data-company-id="company-2"]').trigger('click')
    await nextTick()

    expect(wrapper.emitted('select')).toEqual([['company-2']])
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.body.style.overflow).toBe('clip')
    expect(document.activeElement).toBe(trigger.element)
  })

  it('wraps focus with Tab and Shift+Tab inside the mobile dialog', async () => {
    const wrapper = mountDirectory()
    await wrapper.get('button[name="open-company-drawer"]').trigger('click')
    const close = wrapper.get<HTMLButtonElement>('button[name="close-company-drawer"]')
    const last = wrapper.get<HTMLButtonElement>('[data-company-id="company-2"]')

    close.element.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true }))
    expect(document.activeElement).toBe(last.element)

    last.element.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', cancelable: true }))
    expect(document.activeElement).toBe(close.element)
  })

  it('closes and releases the body lock when the desktop breakpoint becomes active', async () => {
    const media = mediaQueryStub()
    document.body.style.overflow = 'clip'
    const wrapper = mountDirectory()

    await wrapper.get('button[name="open-company-drawer"]').trigger('click')
    media.dispatch(true)
    await nextTick()

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.body.style.overflow).toBe('clip')
  })

  it('removes its global keydown and media-query listeners on unmount', () => {
    const addWindowListener = vi.spyOn(window, 'addEventListener')
    const removeWindowListener = vi.spyOn(window, 'removeEventListener')
    const media = mediaQueryStub()
    const wrapper = mountDirectory()
    const keydownListener = addWindowListener.mock.calls.find(([type]) => type === 'keydown')?.[1]
    const mediaListener = media.addEventListener.mock.calls[0]?.[1]

    unmountTracked(wrapper)

    expect(keydownListener).toBeDefined()
    expect(removeWindowListener).toHaveBeenCalledWith('keydown', keydownListener)
    expect(mediaListener).toBeDefined()
    expect(media.removeEventListener).toHaveBeenCalledWith('change', mediaListener)
  })
})
