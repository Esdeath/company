<script setup lang="ts">
import type { DocumentItem } from '../types/content'

defineProps<{
  companyName: string | null
  documents: DocumentItem[]
  selectedId: string | null
  loading: boolean
}>()

const emit = defineEmits<{
  select: [documentId: string]
}>()

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function formattedDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : dateFormatter.format(date)
}
</script>

<template>
  <aside class="document-directory" aria-labelledby="document-directory-title">
    <header class="directory-heading document-directory__heading">
      <div>
        <p>Research notes</p>
        <h2 id="document-directory-title">{{ companyName ?? '资料目录' }}</h2>
      </div>
      <span v-if="companyName" class="directory-count">{{ documents.length }} 份</span>
    </header>

    <p v-if="loading" class="directory-note">目录读取中…</p>
    <p v-else-if="companyName && documents.length === 0" class="directory-note">暂无资料</p>
    <p v-else-if="!companyName" class="directory-note">先选择一家公司</p>

    <nav v-else aria-label="选择资料">
      <ul class="document-list">
        <li v-for="document in documents" :key="document.id">
          <button
            class="document-entry"
            :class="{ 'document-entry--active': document.id === selectedId }"
            type="button"
            :data-document-id="document.id"
            :aria-current="document.id === selectedId ? 'true' : undefined"
            @click="emit('select', document.id)"
          >
            <span class="document-entry__title">{{ document.title }}</span>
            <span class="document-entry__meta">
              <span class="format-badge">{{ document.format === 'markdown' ? 'MD' : 'HTML' }}</span>
              <time :datetime="document.uploaded_at">{{ formattedDate(document.uploaded_at) }}</time>
            </span>
          </button>
        </li>
      </ul>
    </nav>
  </aside>
</template>
