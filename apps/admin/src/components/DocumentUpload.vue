<script setup lang="ts">
import { ref, watch } from 'vue'

import type { UploadBatch } from '../types'

const props = defineProps<{
  disabled: boolean
  uploading: boolean
  results: UploadBatch | null
  resetKey: number
}>()

const emit = defineEmits<{
  upload: [files: File[]]
}>()

const input = ref<HTMLInputElement | null>(null)
const files = ref<File[]>([])

function chooseFiles(event: Event) {
  files.value = Array.from((event.target as HTMLInputElement).files ?? [])
}

function submitUpload() {
  if (files.value.length > 0) emit('upload', files.value)
}

watch(
  () => props.resetKey,
  () => {
    files.value = []
    if (input.value) input.value.value = ''
  },
)
</script>

<template>
  <section class="upload-desk" aria-labelledby="upload-title">
    <div class="section-label section-label--row">
      <div>
        <p>新增资料</p>
        <h2 id="upload-title">从原文件入库</h2>
      </div>
      <span class="format-note">HTML / MD</span>
    </div>

    <form aria-label="上传资料" class="upload-form" @submit.prevent="submitUpload">
      <label class="file-picker" for="document-files">
        <span>{{ files.length ? `已选择 ${files.length} 个文件` : '选择 HTML 或 Markdown 文件' }}</span>
        <small>可一次选择多个文件</small>
      </label>
      <input
        id="document-files"
        ref="input"
        type="file"
        accept=".html,.md"
        multiple
        :disabled="disabled || uploading"
        @change="chooseFiles"
      />
      <ul v-if="files.length" class="selected-files" aria-label="待上传文件">
        <li v-for="file in files" :key="`${file.name}-${file.size}-${file.lastModified}`">{{ file.name }}</li>
      </ul>
      <button class="primary-action" type="submit" :disabled="disabled || uploading || files.length === 0">
        {{ uploading ? '正在上传…' : '上传所选文件' }}
      </button>
    </form>

    <div class="upload-results" aria-live="polite" aria-atomic="false">
      <template v-if="results">
        <p v-for="item in results.items" :key="item.id" class="result-row result-row--success">
          <span aria-hidden="true">✓</span>
          <span><strong>{{ item.title }}</strong> 已上传</span>
        </p>
        <p v-for="error in results.errors" :key="`${error.filename}-${error.message}`" class="result-row result-row--error">
          <span aria-hidden="true">!</span>
          <span><strong>{{ error.filename }}</strong>：{{ error.message }}</span>
        </p>
      </template>
    </div>
  </section>
</template>
