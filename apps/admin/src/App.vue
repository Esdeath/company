<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createCompany,
  deleteDocument,
  listCompanies,
  listDocuments,
  renameDocument,
  uploadDocuments,
} from './api'
import CompanyPicker from './components/CompanyPicker.vue'
import DocumentList from './components/DocumentList.vue'
import DocumentUpload from './components/DocumentUpload.vue'
import type { Company, CompanyInput, DocumentItem, UploadBatch } from './types'

const companies = ref<Company[]>([])
const selectedCompanyId = ref('')
const documents = ref<DocumentItem[]>([])
const uploadResults = ref<UploadBatch | null>(null)
const uploadResetKey = ref(0)
const createSuccessKey = ref(0)
const loading = ref(true)
const documentsLoading = ref(false)
const creating = ref(false)
const uploading = ref(false)
const pendingDocumentIds = ref<string[]>([])
const pageError = ref('')
const refreshWarning = ref('')
let documentRequestGeneration = 0

const selectedCompany = computed(
  () => companies.value.find((company) => company.id === selectedCompanyId.value) ?? null,
)
const hasDocumentMutation = computed(() => pendingDocumentIds.value.length > 0)

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作未完成，请稍后重试'
}

function warnRefresh(prefix: string, error: unknown) {
  refreshWarning.value = `${prefix}：${errorMessage(error)}`
}

function beginDocumentMutation(documentId: string): boolean {
  if (pendingDocumentIds.value.includes(documentId)) return false
  pendingDocumentIds.value = [...pendingDocumentIds.value, documentId]
  return true
}

function finishDocumentMutation(documentId: string) {
  pendingDocumentIds.value = pendingDocumentIds.value.filter((id) => id !== documentId)
}

async function refreshDocuments(companyId: string) {
  const requestGeneration = ++documentRequestGeneration

  if (!companyId) {
    documents.value = []
    documentsLoading.value = false
    return
  }

  if (selectedCompanyId.value === companyId) {
    documentsLoading.value = true
    refreshWarning.value = ''
  }

  try {
    const refreshed = await listDocuments(companyId)
    if (
      requestGeneration === documentRequestGeneration &&
      selectedCompanyId.value === companyId
    ) {
      documents.value = refreshed
    }
  } catch (error) {
    if (
      requestGeneration === documentRequestGeneration &&
      selectedCompanyId.value === companyId
    ) {
      warnRefresh('资料目录未能刷新', error)
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

async function initialize() {
  loading.value = true
  pageError.value = ''
  try {
    companies.value = await listCompanies()
    selectedCompanyId.value = companies.value[0]?.id ?? ''
    documents.value = []
    await refreshDocuments(selectedCompanyId.value)
  } catch (error) {
    pageError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function selectCompany(companyId: string) {
  selectedCompanyId.value = companyId
  documents.value = []
  uploadResults.value = null
  pageError.value = ''
  refreshWarning.value = ''
  await refreshDocuments(companyId)
}

async function refreshCompaniesAfterCreate(company: Company) {
  try {
    const refreshed = await listCompanies()
    companies.value = refreshed.some((item) => item.id === company.id)
      ? refreshed
      : [company, ...refreshed]
  } catch (error) {
    warnRefresh('公司列表未能刷新', error)
    return
  }

  await refreshDocuments(company.id)
}

async function addCompany(input: CompanyInput) {
  if (creating.value) return
  creating.value = true
  pageError.value = ''
  refreshWarning.value = ''

  let company: Company
  try {
    company = await createCompany(input)
  } catch (error) {
    pageError.value = errorMessage(error)
    creating.value = false
    return
  }

  companies.value = [company, ...companies.value.filter((item) => item.id !== company.id)]
  selectedCompanyId.value = company.id
  documents.value = []
  uploadResults.value = null
  createSuccessKey.value += 1
  await refreshCompaniesAfterCreate(company)
  creating.value = false
}

async function upload(files: File[]) {
  if (!selectedCompanyId.value || uploading.value) return
  const companyId = selectedCompanyId.value
  uploading.value = true
  pageError.value = ''
  uploadResults.value = null

  let batch: UploadBatch
  try {
    batch = await uploadDocuments(companyId, files)
  } catch (error) {
    if (selectedCompanyId.value === companyId) {
      uploadResults.value = {
        items: [],
        errors: files.map((file) => ({ filename: file.name, message: errorMessage(error) })),
      }
    }
    uploadResetKey.value += 1
    uploading.value = false
    return
  }

  if (selectedCompanyId.value === companyId) uploadResults.value = batch
  await refreshDocuments(companyId)
  uploadResetKey.value += 1
  uploading.value = false
}

async function rename(document: DocumentItem, title: string) {
  if (!beginDocumentMutation(document.id)) return
  const companyId = selectedCompanyId.value
  pageError.value = ''

  let renamed: DocumentItem
  try {
    renamed = await renameDocument(document.id, title)
  } catch (error) {
    pageError.value = errorMessage(error)
    finishDocumentMutation(document.id)
    return
  }

  if (selectedCompanyId.value === companyId) {
    documents.value = documents.value.map((item) => (item.id === renamed.id ? renamed : item))
  }
  await refreshDocuments(companyId)
  finishDocumentMutation(document.id)
}

async function remove(document: DocumentItem) {
  if (pendingDocumentIds.value.includes(document.id)) return
  if (!window.confirm(`确认删除《${document.title}》？此操作无法撤销。`)) return
  if (!beginDocumentMutation(document.id)) return

  const companyId = selectedCompanyId.value
  pageError.value = ''
  try {
    await deleteDocument(document.id)
  } catch (error) {
    pageError.value = errorMessage(error)
    finishDocumentMutation(document.id)
    return
  }

  if (selectedCompanyId.value === companyId) {
    documents.value = documents.value.filter((item) => item.id !== document.id)
  }
  await refreshDocuments(companyId)
  finishDocumentMutation(document.id)
}

onMounted(initialize)
</script>

<template>
  <div class="admin-shell">
    <header class="masthead">
      <div class="identity" aria-label="企业研究资料库管理端">
        <span class="identity__library">企业研究资料库</span>
        <span class="identity__division">管理端</span>
      </div>
      <p class="local-mark">仅供本地开发环境使用</p>
    </header>

    <main>
      <header class="page-intro">
        <p class="eyebrow">资料入库与整理</p>
        <h1>资料归档台</h1>
        <p>按公司收纳 HTML 与 Markdown 原文件，文件会直接出现在公开资料库中。</p>
      </header>

      <p v-if="pageError" class="page-error" role="alert">{{ pageError }}</p>
      <p v-if="refreshWarning" class="refresh-warning" role="status" aria-live="polite">
        {{ refreshWarning }}。已完成的操作不受影响，可稍后切换公司重试刷新。
      </p>

      <div class="workspace" :aria-busy="loading || documentsLoading">
        <CompanyPicker
          :companies="companies"
          :selected-id="selectedCompanyId"
          :busy="loading || creating || uploading || hasDocumentMutation"
          :creating="creating"
          :create-success-key="createSuccessKey"
          @select="selectCompany"
          @create="addCompany"
        />

        <div class="document-workspace">
          <header v-if="selectedCompany" class="company-heading">
            <p>{{ [selectedCompany.ticker, selectedCompany.market].filter(Boolean).join(' · ') || '公司资料' }}</p>
            <h2>{{ selectedCompany.name }}</h2>
          </header>
          <p v-else-if="!loading" class="choose-company">先新建一家公司，再开始归档资料。</p>

          <template v-if="selectedCompany">
            <DocumentUpload
              :disabled="creating || documentsLoading || hasDocumentMutation"
              :uploading="uploading"
              :results="uploadResults"
              :reset-key="uploadResetKey"
              @upload="upload"
            />
            <DocumentList
              :documents="documents"
              :busy="documentsLoading || creating || uploading"
              :pending-ids="pendingDocumentIds"
              @rename="rename"
              @delete="remove"
            />
          </template>
        </div>
      </div>

      <nav class="public-return" aria-label="站点入口">
        <a href="/"><span aria-hidden="true">←</span> 前往公开站点</a>
        <p>本工具仅限本地开发使用，不对外开放。</p>
      </nav>
    </main>

    <footer class="footer">
      <p>企业研究资料库 · 本地资料管理</p>
      <p>支持 .html 与 .md</p>
    </footer>
  </div>
</template>
