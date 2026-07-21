<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { listCompanies, listDocuments } from './api/library'
import CompanyDirectory from './components/CompanyDirectory.vue'
import DocumentDirectory from './components/DocumentDirectory.vue'
import DocumentReader from './components/DocumentReader.vue'
import type { Company, DocumentItem } from './types/content'

const companies = ref<Company[]>([])
const selectedCompanyId = ref<string | null>(null)
const documents = ref<DocumentItem[]>([])
const selectedDocumentId = ref<string | null>(null)
const companiesLoading = ref(true)
const documentsLoading = ref(false)
const companyError = ref<string | null>(null)
const documentError = ref<string | null>(null)
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
    selectedCompanyId.value = refreshed.some((company) => company.id === currentId)
      ? currentId
      : (refreshed[0]?.id ?? null)
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
    selectedDocumentId.value = refreshed.some((document) => document.id === currentId)
      ? currentId
      : (refreshed[0]?.id ?? null)
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
  selectedCompanyId.value = companyId
}

function retryReader() {
  if (companyError.value) {
    void refreshCompanies()
  } else {
    void refreshDocuments(selectedCompanyId.value)
  }
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
      <p>原始资料 · 独立阅读</p>
    </header>

    <main class="library-main">
      <header class="library-intro">
        <div>
          <p class="eyebrow">Public research desk</p>
          <h1>企业研究资料库</h1>
        </div>
        <p>按公司查找研究资料，在独立阅读页中连续阅读。</p>
      </header>

      <div class="library-workspace">
        <CompanyDirectory
          :companies="companies"
          :selected-id="selectedCompanyId"
          :loading="companiesLoading"
          @select="selectCompany"
        />
        <DocumentDirectory
          :company-name="selectedCompany?.name ?? null"
          :documents="documents"
          :selected-id="selectedDocumentId"
          :loading="documentsLoading"
          @select="selectedDocumentId = $event"
        />
        <DocumentReader
          :document="selectedDocument"
          :loading="companiesLoading || documentsLoading"
          :error="readerError"
          :empty-message="emptyMessage"
          :retry-name="readerRetryName"
          @retry="retryReader"
        />
      </div>
    </main>

    <footer class="footer">
      <p>企业研究资料库</p>
      <p>HTML 与 Markdown 资料独立阅读</p>
    </footer>
  </div>
</template>
