<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createCompany,
  deleteDocument,
  getSession,
  isAuthenticationRequired,
  listCompanies,
  listDocuments,
  login,
  logout,
  renameDocument,
  reorderDocuments,
  uploadDocuments,
} from './api'
import CompanyPicker from './components/CompanyPicker.vue'
import AdminSectionNav from './components/AdminSectionNav.vue'
import CommentModeration from './components/CommentModeration.vue'
import DocumentList from './components/DocumentList.vue'
import DocumentUpload from './components/DocumentUpload.vue'
import LoginPanel from './components/LoginPanel.vue'
import UserManagement from './components/UserManagement.vue'
import type {
  AdminSection,
  AuthState,
  Company,
  CompanyInput,
  DocumentItem,
  LoginInput,
  UploadBatch,
} from './types'

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
const reordering = ref(false)
const orderFeedback = ref<{ sequence: number; message: string } | null>(null)
const pendingDocumentIds = ref<string[]>([])
const pageError = ref('')
const refreshWarning = ref('')
const authState = ref<AuthState | null>(null)
const authLoading = ref(true)
const loginBusy = ref(false)
const loginError = ref('')
const logoutBusy = ref(false)
const activeSection = ref<AdminSection>('documents')
let documentRequestGeneration = 0
let orderFeedbackSequence = 0

const selectedCompany = computed(
  () => companies.value.find((company) => company.id === selectedCompanyId.value) ?? null,
)
const hasDocumentMutation = computed(() => pendingDocumentIds.value.length > 0)

function errorMessage(error: unknown): string {
  if (isAuthenticationRequired(error)) {
    void returnToLogin()
  }
  return error instanceof Error ? error.message : '操作未完成，请稍后重试'
}

function clearWorkspace() {
  companies.value = []
  selectedCompanyId.value = ''
  documents.value = []
  uploadResults.value = null
  pageError.value = ''
  refreshWarning.value = ''
  orderFeedback.value = null
  activeSection.value = 'documents'
}

async function returnToLogin() {
  clearWorkspace()
  try {
    authState.value = await getSession()
  } catch {
    authState.value = null
  }
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

async function initializeAuthentication() {
  authLoading.value = true
  loginError.value = ''
  try {
    authState.value = await getSession()
    if (authState.value.authenticated) await initialize()
  } catch (error) {
    loginError.value = errorMessage(error)
  } finally {
    authLoading.value = false
  }
}

async function signIn(input: LoginInput) {
  if (loginBusy.value) return
  loginBusy.value = true
  loginError.value = ''
  try {
    authState.value = await login(input)
    await initialize()
  } catch (error) {
    loginError.value = errorMessage(error)
    try {
      authState.value = await getSession()
    } catch {
      // Keep the useful login error when the replacement challenge cannot be loaded.
    }
  } finally {
    loginBusy.value = false
  }
}

async function signOut() {
  if (logoutBusy.value) return
  logoutBusy.value = true
  try {
    await logout()
  } catch {
    // A missing/expired server session is already equivalent to being signed out.
  }
  clearWorkspace()
  try {
    authState.value = await getSession()
  } catch {
    authState.value = null
  }
  logoutBusy.value = false
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

async function reorder(documentIds: string[]) {
  if (reordering.value || hasDocumentMutation.value || !selectedCompanyId.value) return
  if (documentIds.length !== documents.value.length || new Set(documentIds).size !== documentIds.length) {
    return
  }
  const byId = new Map(documents.value.map((document) => [document.id, document]))
  const reordered = documentIds.map((documentId) => byId.get(documentId))
  if (reordered.some((document) => document === undefined)) return

  const companyId = selectedCompanyId.value
  const requestGeneration = documentRequestGeneration
  const previous = documents.value
  documents.value = reordered as DocumentItem[]
  reordering.value = true
  orderFeedback.value = null
  pageError.value = ''
  try {
    const saved = await reorderDocuments(companyId, documentIds)
    if (
      selectedCompanyId.value === companyId &&
      documentRequestGeneration === requestGeneration
    ) {
      documents.value = saved
      orderFeedback.value = {
        sequence: ++orderFeedbackSequence,
        message: '资料顺序已保存',
      }
    }
  } catch (error) {
    const message = errorMessage(error)
    if (
      selectedCompanyId.value === companyId &&
      documentRequestGeneration === requestGeneration
    ) {
      documents.value = previous
      pageError.value = message
      orderFeedback.value = {
        sequence: ++orderFeedbackSequence,
        message: '顺序保存失败，已恢复原顺序',
      }
    }
  } finally {
    reordering.value = false
  }
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

onMounted(initializeAuthentication)
</script>

<template>
  <div class="admin-shell">
    <header class="masthead">
      <div class="identity" aria-label="企业研究资料库管理端">
        <span class="identity__library">企业研究资料库</span>
        <span class="identity__division">管理端</span>
      </div>
      <div v-if="authState?.authenticated" class="session-mark">
        <span>{{ authState.username }}</span>
        <button class="text-action" type="button" :disabled="logoutBusy" @click="signOut">
          {{ logoutBusy ? '正在退出…' : '退出' }}
        </button>
      </div>
      <p v-else class="local-mark">安全管理入口</p>
    </header>

    <main v-if="authLoading" class="auth-loading" aria-live="polite">正在确认管理员会话…</main>

    <LoginPanel
      v-else-if="!authState?.authenticated"
      :busy="loginBusy"
      :error="loginError"
      @login="signIn"
    />

    <main v-else>
      <p v-if="pageError" class="page-error" role="alert">{{ pageError }}</p>
      <p v-if="refreshWarning" class="refresh-warning" role="status" aria-live="polite">
        {{ refreshWarning }}。已完成的操作不受影响，可稍后切换公司重试刷新。
      </p>

      <AdminSectionNav :active="activeSection" @select="activeSection = $event" />

      <div
        id="admin-panel-documents"
        class="workspace"
        role="tabpanel"
        aria-labelledby="admin-tab-documents"
        v-show="activeSection === 'documents'"
        :aria-busy="loading || documentsLoading"
      >
        <CompanyPicker
          v-if="activeSection === 'documents'"
          :companies="companies"
          :selected-id="selectedCompanyId"
          :busy="loading || creating || uploading || hasDocumentMutation"
          :creating="creating"
          :create-success-key="createSuccessKey"
          @select="selectCompany"
          @create="addCompany"
        />

        <div v-if="activeSection === 'documents'" class="document-workspace">
          <header v-if="selectedCompany" class="company-heading">
            <p>{{ [selectedCompany.ticker, selectedCompany.market].filter(Boolean).join(' · ') || '公司资料' }}</p>
            <h2>{{ selectedCompany.name }}</h2>
          </header>
          <p v-else-if="!loading" class="choose-company">先新建一家公司，再开始归档资料。</p>

          <template v-if="selectedCompany">
            <DocumentUpload
              :disabled="creating || documentsLoading || hasDocumentMutation || reordering"
              :uploading="uploading"
              :results="uploadResults"
              :reset-key="uploadResetKey"
              @upload="upload"
            />
            <DocumentList
              :documents="documents"
              :busy="documentsLoading || creating || uploading || reordering || hasDocumentMutation"
              :order-feedback="orderFeedback"
              :pending-ids="pendingDocumentIds"
              @reorder="reorder"
              @rename="rename"
              @delete="remove"
            />
          </template>
        </div>
      </div>

      <div
        id="admin-panel-comments"
        role="tabpanel"
        aria-labelledby="admin-tab-comments"
        v-show="activeSection === 'comments'"
      >
        <CommentModeration v-if="activeSection === 'comments'" @authentication-required="returnToLogin" />
      </div>
      <div id="admin-panel-users" role="tabpanel" aria-labelledby="admin-tab-users" v-show="activeSection === 'users'">
        <UserManagement v-if="activeSection === 'users'" @authentication-required="returnToLogin" />
      </div>

      <nav class="public-return" aria-label="站点入口">
        <a href="/"><span aria-hidden="true">←</span> 前往公开站点</a>
        <p>所有资料变更均要求有效管理员会话。</p>
      </nav>
    </main>

    <footer class="footer">
      <p>企业研究资料库 · 安全资料管理</p>
      <p>支持 .html 与 .md</p>
    </footer>
  </div>
</template>
