<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import type { Company, DocumentItem } from '../types/content'

const props = defineProps<{
  companies: Company[]
  documents: DocumentItem[]
  selectedCompanyId: string | null
  selectedDocumentId: string | null
  companiesLoading: boolean
  documentsLoading: boolean
}>()

const emit = defineEmits<{
  'select-company': [companyId: string]
  'select-document': [documentId: string]
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
  () => props.companies.find((company) => company.id === props.selectedCompanyId) ?? null,
)
const selectedDocument = computed(
  () => props.documents.find((document) => document.id === props.selectedDocumentId) ?? null,
)
const navigationVisible = computed(() => isDesktop.value || drawerOpen.value)
const triggerLabel = computed(() =>
  [selectedCompany.value?.name, selectedDocument.value?.title].filter(Boolean).join(' · ') || '浏览目录',
)

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
  emit('select-company', companyId)
}

function selectDocument(documentId: string) {
  emit('select-document', documentId)
  void closeDrawer()
}

function focusableElements(): HTMLElement[] {
  if (!directory.value) return []
  return Array.from(directory.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => !element.hidden)
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
  <section class="library-directory-shell">
    <button
      ref="trigger"
      class="library-drawer-trigger"
      name="open-library-directory"
      type="button"
      aria-haspopup="dialog"
      :aria-expanded="drawerOpen"
      @click="openDrawer"
    >
      <span>浏览目录</span><strong>{{ triggerLabel }}</strong><span aria-hidden="true">→</span>
    </button>
    <div
      v-if="drawerOpen && !isDesktop"
      class="library-backdrop"
      aria-hidden="true"
      @click="closeDrawer()"
    />
    <aside
      v-show="navigationVisible"
      ref="directory"
      class="library-directory"
      :class="{ 'library-directory--drawer': drawerOpen && !isDesktop }"
      aria-label="公司与资料"
      :role="drawerOpen && !isDesktop ? 'dialog' : undefined"
      :aria-modal="drawerOpen && !isDesktop ? 'true' : undefined"
      aria-labelledby="library-directory-title"
      :inert="!navigationVisible"
    >
      <header class="directory-heading">
        <div><p>Research library</p><h2 id="library-directory-title">公司与资料</h2></div>
        <button
          ref="closeButton"
          class="drawer-close"
          name="close-library-directory"
          type="button"
          aria-label="关闭公司与资料目录"
          @click="closeDrawer()"
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>
      <p v-if="companiesLoading" class="directory-note">正在读取公司目录…</p>
      <p v-else-if="companies.length === 0" class="directory-note">暂无公司</p>
      <nav v-else aria-label="选择公司与资料">
        <ul class="library-tree">
          <li v-for="company in companies" :key="company.id">
            <button
              class="company-entry"
              :class="{ 'company-entry--active': company.id === selectedCompanyId }"
              type="button"
              :data-company-id="company.id"
              :aria-expanded="company.id === selectedCompanyId"
              @click="selectCompany(company.id)"
            >
              <span class="company-entry__toggle" aria-hidden="true">
                {{ company.id === selectedCompanyId ? '⌄' : '›' }}
              </span>
              <span class="company-entry__copy"><strong class="company-entry__label">
                {{ company.name }}{{ company.ticker ? `(${company.ticker})` : '' }}
              </strong></span>
            </button>
            <div v-if="company.id === selectedCompanyId" class="document-branch">
              <p v-if="documentsLoading" class="directory-note">资料目录读取中…</p>
              <p v-else-if="documents.length === 0" class="directory-note">暂无资料</p>
              <ul v-else class="document-list">
                <li v-for="document in documents" :key="document.id">
                  <button
                    class="document-entry"
                    :class="{ 'document-entry--active': document.id === selectedDocumentId }"
                    type="button"
                    :data-document-id="document.id"
                    :aria-current="document.id === selectedDocumentId ? 'true' : undefined"
                    @click="selectDocument(document.id)"
                  >
                    <span class="document-entry__title">{{ document.title }}</span>
                  </button>
                </li>
              </ul>
            </div>
          </li>
        </ul>
      </nav>
    </aside>
  </section>
</template>
