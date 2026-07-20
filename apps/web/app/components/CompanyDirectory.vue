<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import type { Company } from '../types/content'

const props = defineProps<{
  companies: Company[]
  selectedId: string | null
  loading: boolean
}>()

const emit = defineEmits<{
  select: [companyId: string]
}>()

const drawerOpen = ref(false)
const isDesktop = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const directory = ref<HTMLElement | null>(null)
let mediaQuery: MediaQueryList | null = null
let previousBodyOverflow = ''
let ownsBodyLock = false

const selectedCompany = computed(
  () => props.companies.find((company) => company.id === props.selectedId) ?? null,
)
const navigationVisible = computed(() => isDesktop.value || drawerOpen.value)

function acquireBodyLock() {
  if (typeof document === 'undefined' || ownsBodyLock) return
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  ownsBodyLock = true
}

function releaseBodyLock() {
  if (typeof document === 'undefined' || !ownsBodyLock) return
  document.body.style.overflow = previousBodyOverflow
  ownsBodyLock = false
}

async function openDrawer() {
  drawerOpen.value = true
  if (!isDesktop.value) acquireBodyLock()
  await nextTick()
  closeButton.value?.focus()
}

async function closeDrawer(restoreFocus = true) {
  const wasOpen = drawerOpen.value
  drawerOpen.value = false
  releaseBodyLock()
  if (restoreFocus && wasOpen) {
    await nextTick()
    trigger.value?.focus()
  }
}

function selectCompany(companyId: string) {
  emit('select', companyId)
  void closeDrawer()
}

function focusableElements(): HTMLElement[] {
  if (!directory.value) return []
  return Array.from(
    directory.value.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hidden)
}

function handleKeydown(event: KeyboardEvent) {
  if (!drawerOpen.value || isDesktop.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    void closeDrawer()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = focusableElements()
  const first = focusable[0]
  const last = focusable.at(-1)
  if (!first || !last) return

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function handleBreakpoint(event: MediaQueryListEvent | MediaQueryList) {
  isDesktop.value = event.matches
  if (event.matches) void closeDrawer(false)
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  if (typeof window.matchMedia === 'function') {
    mediaQuery = window.matchMedia('(min-width: 64rem)')
    handleBreakpoint(mediaQuery)
    mediaQuery.addEventListener('change', handleBreakpoint)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  mediaQuery?.removeEventListener('change', handleBreakpoint)
  releaseBodyLock()
})
</script>

<template>
  <section class="company-directory-shell">
    <button
      ref="trigger"
      class="company-drawer-trigger"
      name="open-company-drawer"
      type="button"
      aria-haspopup="dialog"
      :aria-expanded="drawerOpen"
      @click="openDrawer"
    >
      <span>选择公司</span>
      <strong>{{ selectedCompany?.name ?? '浏览目录' }}</strong>
      <span aria-hidden="true">→</span>
    </button>

    <div
      v-if="drawerOpen && !isDesktop"
      class="company-backdrop"
      aria-hidden="true"
      @click="closeDrawer()"
    />

    <aside
      v-show="navigationVisible"
      ref="directory"
      class="company-directory"
      :class="{ 'company-directory--drawer': drawerOpen && !isDesktop }"
      aria-label="公司目录"
      :role="drawerOpen && !isDesktop ? 'dialog' : undefined"
      :aria-modal="drawerOpen && !isDesktop ? 'true' : undefined"
      aria-labelledby="company-directory-title"
      :inert="!navigationVisible"
    >
      <header class="directory-heading">
        <div>
          <p>Company index</p>
          <h2 id="company-directory-title">公司目录</h2>
        </div>
        <button
          ref="closeButton"
          class="drawer-close"
          name="close-company-drawer"
          type="button"
          aria-label="关闭公司目录"
          @click="closeDrawer()"
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>

      <p v-if="loading" class="directory-note">正在读取公司目录…</p>
      <p v-else-if="companies.length === 0" class="directory-note">暂无公司</p>
      <nav v-else aria-label="选择公司">
        <ul class="company-list">
          <li v-for="company in companies" :key="company.id">
            <button
              class="company-entry"
              :class="{ 'company-entry--active': company.id === selectedId }"
              type="button"
              :data-company-id="company.id"
              :aria-current="company.id === selectedId ? 'true' : undefined"
              @click="selectCompany(company.id)"
            >
              <span>{{ company.name }}</span>
              <small>
                {{ [company.ticker, company.market].filter(Boolean).join(' · ') || '公司研究' }}
              </small>
            </button>
          </li>
        </ul>
      </nav>
    </aside>
  </section>
</template>
