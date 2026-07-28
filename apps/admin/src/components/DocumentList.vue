<script setup lang="ts">
import { ref, watch } from 'vue'

import type { DocumentItem } from '../types'

const props = defineProps<{
  documents: DocumentItem[]
  busy?: boolean
  orderFeedback?: { sequence: number; message: string } | null
  pendingIds: string[]
}>()

const emit = defineEmits<{
  rename: [document: DocumentItem, title: string]
  delete: [document: DocumentItem]
  reorder: [documentIds: string[]]
}>()

const statusMessage = ref('')

watch(
  () => props.orderFeedback,
  (feedback) => {
    if (feedback) statusMessage.value = feedback.message
  },
)

function moveDocument(documentId: string, offset: -1 | 1) {
  if (props.busy) return
  const documentIds = props.documents.map((document) => document.id)
  const currentIndex = documentIds.indexOf(documentId)
  const nextIndex = currentIndex + offset
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= documentIds.length) return

  const currentDocumentId = documentIds[currentIndex]!
  documentIds[currentIndex] = documentIds[nextIndex]!
  documentIds[nextIndex] = currentDocumentId
  statusMessage.value = `已移到第 ${nextIndex + 1} 项，正在保存`
  emit('reorder', documentIds)
}

function rename(document: DocumentItem, source: Event | HTMLInputElement) {
  const input = source instanceof HTMLInputElement ? source : (source.target as HTMLInputElement)
  const title = input.value.trim()
  if (title && title !== document.title) emit('rename', document, title)
}

function isPending(documentId: string): boolean {
  return props.pendingIds.includes(documentId)
}

function formatUploadedAt(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}
</script>

<template>
  <section class="document-register" aria-labelledby="documents-title">
    <div class="section-label section-label--row">
      <div>
        <p>资料目录</p>
        <h2 id="documents-title">已归档文件</h2>
      </div>
      <span class="document-count">{{ documents.length }} 份</span>
    </div>

    <p v-if="documents.length === 0" class="empty-state">这里还没有资料。先从上方选择原文件。</p>

    <span class="document-order-status visually-hidden" role="status" aria-live="polite">
      {{ statusMessage }}
    </span>

    <ul v-if="documents.length > 0" class="document-list">
      <li
        v-for="(document, index) in documents"
        :key="document.id"
        class="document-row"
      >
        <div class="document-row__heading">
          <span class="document-order-actions" role="group" :aria-label="`调整 ${document.title} 的顺序`">
            <button
              class="document-order-button"
              type="button"
              title="上移"
              :aria-label="`上移 ${document.title}`"
              :disabled="busy || index === 0"
              @click="moveDocument(document.id, -1)"
            >
              ↑
            </button>
            <button
              class="document-order-button"
              type="button"
              title="下移"
              :aria-label="`下移 ${document.title}`"
              :disabled="busy || index === documents.length - 1"
              @click="moveDocument(document.id, 1)"
            >
              ↓
            </button>
          </span>
          <span class="format-badge">{{ document.format === 'markdown' ? 'MD' : 'HTML' }}</span>
          <span class="document-title">{{ document.title }}</span>
        </div>
        <p class="document-meta">
          <span>{{ document.original_filename }}</span>
          <time :datetime="document.uploaded_at">{{ formatUploadedAt(document.uploaded_at) }}</time>
        </p>
        <div class="document-actions">
          <label :for="`rename-${document.id}`" class="visually-hidden">重命名 {{ document.title }}</label>
          <input
            :id="`rename-${document.id}`"
            :aria-label="`重命名 ${document.title}`"
            :value="document.title"
            :disabled="busy || isPending(document.id)"
            @keydown.enter.prevent="rename(document, $event)"
          />
          <button
            class="text-action"
            type="button"
            :disabled="busy || isPending(document.id)"
            @click="rename(document, ($event.currentTarget as HTMLButtonElement).previousElementSibling as HTMLInputElement)"
          >
            保存名称
          </button>
          <button
            class="text-action text-action--danger"
            type="button"
            :aria-label="`删除 ${document.title}`"
            :disabled="busy || isPending(document.id)"
            @click="emit('delete', document)"
          >
            删除
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>
