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
const loading = ref(true)
const mutating = ref(false)
const uploading = ref(false)
const pageError = ref('')

const selectedCompany = computed(
  () => companies.value.find((company) => company.id === selectedCompanyId.value) ?? null,
)

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作未完成，请稍后重试'
}

async function refreshDocuments() {
  if (!selectedCompanyId.value) {
    documents.value = []
    return
  }
  documents.value = await listDocuments(selectedCompanyId.value)
}

async function refreshCompanies(preferredCompanyId = selectedCompanyId.value) {
  const refreshed = await listCompanies()
  companies.value = refreshed
  selectedCompanyId.value =
    refreshed.find((company) => company.id === preferredCompanyId)?.id ?? refreshed[0]?.id ?? ''
  await refreshDocuments()
}

async function initialize() {
  loading.value = true
  pageError.value = ''
  try {
    await refreshCompanies()
  } catch (error) {
    pageError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function selectCompany(companyId: string) {
  selectedCompanyId.value = companyId
  uploadResults.value = null
  pageError.value = ''
  try {
    await refreshDocuments()
  } catch (error) {
    documents.value = []
    pageError.value = errorMessage(error)
  }
}

async function addCompany(input: CompanyInput) {
  mutating.value = true
  pageError.value = ''
  try {
    const company = await createCompany(input)
    await refreshCompanies(company.id)
  } catch (error) {
    pageError.value = errorMessage(error)
  } finally {
    mutating.value = false
  }
}

async function upload(files: File[]) {
  if (!selectedCompanyId.value) return
  uploading.value = true
  pageError.value = ''
  uploadResults.value = null
  try {
    uploadResults.value = await uploadDocuments(selectedCompanyId.value, files)
    await refreshDocuments()
  } catch (error) {
    uploadResults.value = {
      items: [],
      errors: files.map((file) => ({ filename: file.name, message: errorMessage(error) })),
    }
  } finally {
    uploadResetKey.value += 1
    uploading.value = false
  }
}

async function rename(document: DocumentItem, title: string) {
  mutating.value = true
  pageError.value = ''
  try {
    await renameDocument(document.id, title)
    await refreshDocuments()
  } catch (error) {
    pageError.value = errorMessage(error)
  } finally {
    mutating.value = false
  }
}

async function remove(document: DocumentItem) {
  if (!window.confirm(`确认删除《${document.title}》？此操作无法撤销。`)) return

  mutating.value = true
  pageError.value = ''
  try {
    await deleteDocument(document.id)
    await refreshDocuments()
  } catch (error) {
    pageError.value = errorMessage(error)
  } finally {
    mutating.value = false
  }
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

      <div class="workspace" :aria-busy="loading">
        <CompanyPicker
          :companies="companies"
          :selected-id="selectedCompanyId"
          :busy="loading || mutating || uploading"
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
              :disabled="mutating"
              :uploading="uploading"
              :results="uploadResults"
              :reset-key="uploadResetKey"
              @upload="upload"
            />
            <DocumentList
              :documents="documents"
              :busy="mutating || uploading"
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
