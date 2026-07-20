<script setup lang="ts">
import type { DocumentItem } from '../types/content'

withDefaults(
  defineProps<{
    document: DocumentItem | null
    loading: boolean
    error: string | null
    emptyMessage?: string
    retryName?: string
  }>(),
  {
    emptyMessage: '选择一份资料开始阅读',
    retryName: 'retry-documents',
  },
)

defineEmits<{
  retry: []
}>()
</script>

<template>
  <section class="document-reader" aria-label="资料阅读区" :aria-busy="loading">
    <div v-if="loading" class="reader-state" role="status" aria-live="polite">
      <span class="reader-progress" aria-hidden="true" />
      <div>
        <strong>正在读取资料目录</strong>
        <p>找到资料后将在这里打开。</p>
      </div>
    </div>

    <div v-else-if="error" class="reader-state reader-state--error" role="alert">
      <div>
        <strong>资料暂时无法读取</strong>
        <p>{{ error }}</p>
      </div>
      <button :name="retryName" type="button" @click="$emit('retry')">重新载入</button>
    </div>

    <div v-else-if="!document" class="reader-state reader-state--empty">
      <div>
        <strong>等待研究资料</strong>
        <p>{{ emptyMessage }}</p>
      </div>
    </div>

    <iframe
      v-else
      class="document-frame"
      :src="document.content_url"
      sandbox=""
      :title="`阅读：${document.title}`"
    />
  </section>
</template>
