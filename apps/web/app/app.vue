<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { listCompanies, listDocuments } from './api/library'
import CommentSection from './components/CommentSection.vue'
import DocumentReader from './components/DocumentReader.vue'
import LibraryDirectory from './components/LibraryDirectory.vue'
import SiteUserControls from './components/SiteUserControls.vue'
import { useUserSession } from './composables/useUserSession'
import type { Company, DocumentItem } from './types/content'

type UserControls = {
  openLogin: () => void
}

const initialSearch = typeof window === 'undefined' ? new URLSearchParams() : new URLSearchParams(window.location.search)
let requestedCompanyId = initialSearch.get('company')
let requestedDocumentId = initialSearch.get('document')
const session = useUserSession()
const userControls = ref<UserControls | null>(null)
const commentBand = ref<HTMLElement | null>(null)

const companies = ref<Company[]>([])
const selectedCompanyId = ref<string | null>(null)
const documents = ref<DocumentItem[]>([])
const selectedDocumentId = ref<string | null>(null)
const companiesLoading = ref(true)
const documentsLoading = ref(false)
const companyError = ref<string | null>(null)
const documentError = ref<string | null>(null)
const targetCommentId = ref(initialSearch.get('comment'))
const targetMessage = ref<string | null>(null)
let companyRequestGeneration = 0
let documentRequestGeneration = 0

const selectedCompany = computed(
  () => companies.value.find((company) => company.id === selectedCompanyId.value) ?? null,
)
const selectedDocument = computed(
  () => documents.value.find((document) => document.id === selectedDocumentId.value) ?? null,
)
const readerError = computed(() => companyError.value ?? documentError.value)
const readerRetryName = computed(() => (companyError.value ? 'retry-companies' : 'retry-documents'))
const emptyMessage = computed(() => {
  if (companies.value.length === 0) return '资料库里还没有公司'
  if (selectedCompany.value && documents.value.length === 0) return '这家公司还没有可阅读的资料'
  return '选择一家公司和资料开始阅读'
})

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '资料暂时无法读取'
}

async function refreshCompanies() {
  const requestGeneration = ++companyRequestGeneration
  companiesLoading.value = true
  companyError.value = null

  try {
    const refreshed = await listCompanies()
    if (requestGeneration !== companyRequestGeneration) return

    companies.value = refreshed
    const currentId = selectedCompanyId.value
    const requestedId = requestedCompanyId
    selectedCompanyId.value = refreshed.some((company) => company.id === currentId)
      ? currentId
      : refreshed.some((company) => company.id === requestedId)
        ? requestedId
        : (refreshed[0]?.id ?? null)
    requestedCompanyId = null
  } catch (error) {
    if (requestGeneration === companyRequestGeneration) companyError.value = errorMessage(error)
  } finally {
    if (requestGeneration === companyRequestGeneration) companiesLoading.value = false
  }
}

async function refreshDocuments(companyId: string | null) {
  const requestGeneration = ++documentRequestGeneration

  if (!companyId) {
    documents.value = []
    selectedDocumentId.value = null
    documentError.value = null
    documentsLoading.value = false
    return
  }

  if (selectedCompanyId.value === companyId) {
    documentsLoading.value = true
    documentError.value = null
  }

  try {
    const refreshed = await listDocuments(companyId)
    if (
      requestGeneration !== documentRequestGeneration ||
      selectedCompanyId.value !== companyId
    ) {
      return
    }

    documents.value = refreshed
    const currentId = selectedDocumentId.value
    const requestedId = requestedDocumentId
    selectedDocumentId.value = refreshed.some((document) => document.id === currentId)
      ? currentId
      : refreshed.some((document) => document.id === requestedId)
        ? requestedId
        : (refreshed[0]?.id ?? null)
    requestedDocumentId = null
  } catch (error) {
    if (
      requestGeneration === documentRequestGeneration &&
      selectedCompanyId.value === companyId
    ) {
      documentError.value = errorMessage(error)
    }
  } finally {
    if (
      requestGeneration === documentRequestGeneration &&
      selectedCompanyId.value === companyId
    ) {
      documentsLoading.value = false
    }
  }
}

function selectCompany(companyId: string) {
  if (companyId === selectedCompanyId.value) {
    void refreshDocuments(companyId)
    return
  }
  retireTarget()
  selectedCompanyId.value = companyId
}

function selectDocument(documentId: string) {
  if (documentId !== selectedDocumentId.value) retireTarget()
  selectedDocumentId.value = documentId
}

function retryReader() {
  if (companyError.value) {
    void refreshCompanies()
  } else {
    void refreshDocuments(selectedCompanyId.value)
  }
}

function removeCommentFromUrl() {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  url.searchParams.delete('comment')
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
}

async function resolveTarget(commentId: string) {
  targetMessage.value = null
  await nextTick()
  const target = commentBand.value?.querySelector<HTMLElement>(`[data-comment-id="${commentId}"]`)
  if (!target) {
    missingTarget(commentId)
    return
  }
  target.classList.add('comment-target')
  target.scrollIntoView({ block: 'center' })
  removeCommentFromUrl()
}

function missingTarget(commentId: string) {
  if (targetCommentId.value !== commentId) return
  targetMessage.value = '这条评论已不存在或暂时无法查看'
  targetCommentId.value = null
  removeCommentFromUrl()
}

function retireTarget() {
  targetCommentId.value = null
  targetMessage.value = null
  removeCommentFromUrl()
}

function requestLogin() {
  userControls.value?.openLogin()
}

watch(
  selectedCompanyId,
  (companyId) => {
    documents.value = []
    selectedDocumentId.value = null
    documentError.value = null
    void refreshDocuments(companyId)
  },
  { flush: 'sync' },
)

onMounted(() => {
  void session.restore().catch(() => undefined)
  void refreshCompanies()
})
</script>

<template>
  <div class="site-shell">
    <header class="masthead">
      <a class="brand" href="/" aria-label="企业研究资料库首页">
        <img
          class="brand__mark"
          :src="'/icon.svg'"
          alt=""
          aria-hidden="true"
          width="32"
          height="32"
        >
        <span class="brand__copy">
          <span class="brand__name">企业研究资料库</span>
          <span class="brand__note">Company research library</span>
        </span>
      </a>
      <div class="masthead__actions">
        <p>原始资料 · 独立阅读</p>
        <SiteUserControls ref="userControls" />
      </div>
    </header>

    <main class="library-main">
      <div class="library-workspace">
        <LibraryDirectory
          :companies="companies"
          :documents="documents"
          :selected-company-id="selectedCompanyId"
          :selected-document-id="selectedDocumentId"
          :companies-loading="companiesLoading"
          :documents-loading="documentsLoading"
          @select-company="selectCompany"
          @select-document="selectDocument"
        />
        <div class="reading-column">
          <DocumentReader
            :document="selectedDocument"
            :loading="companiesLoading || documentsLoading"
            :error="readerError"
            :empty-message="emptyMessage"
            :retry-name="readerRetryName"
            @retry="retryReader"
          />
          <div v-if="selectedDocument" ref="commentBand" class="comment-band">
            <p v-if="targetMessage" class="deep-link-message" role="status">{{ targetMessage }}</p>
            <CommentSection
              :document-id="selectedDocument.id"
              :current-user="session.user.value"
              :target-comment-id="targetCommentId"
              @login-required="requestLogin"
              @target-resolved="resolveTarget"
              @target-missing="missingTarget"
            />
          </div>
        </div>
      </div>
    </main>

    <footer class="footer">
      <p>企业研究资料库</p>
      <p>HTML 与 Markdown 资料独立阅读</p>
    </footer>
  </div>
</template>
