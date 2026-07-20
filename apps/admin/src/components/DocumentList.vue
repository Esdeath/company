<script setup lang="ts">
import type { DocumentItem } from '../types'

defineProps<{
  documents: DocumentItem[]
  busy?: boolean
}>()

const emit = defineEmits<{
  rename: [document: DocumentItem, title: string]
  delete: [document: DocumentItem]
}>()

function rename(document: DocumentItem, source: Event | HTMLInputElement) {
  const input = source instanceof HTMLInputElement ? source : (source.target as HTMLInputElement)
  const title = input.value.trim()
  if (title && title !== document.title) emit('rename', document, title)
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

    <ul v-else class="document-list">
      <li v-for="document in documents" :key="document.id" class="document-row">
        <div class="document-row__heading">
          <span class="format-badge">{{ document.format === 'markdown' ? 'MD' : 'HTML' }}</span>
          <a :href="document.content_url" target="_blank" rel="noreferrer">{{ document.title }}</a>
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
            :disabled="busy"
            @keydown.enter.prevent="rename(document, $event)"
          />
          <button
            class="text-action"
            type="button"
            :disabled="busy"
            @click="rename(document, ($event.currentTarget as HTMLButtonElement).previousElementSibling as HTMLInputElement)"
          >
            保存名称
          </button>
          <button
            class="text-action text-action--danger"
            type="button"
            :aria-label="`删除 ${document.title}`"
            :disabled="busy"
            @click="emit('delete', document)"
          >
            删除
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>
