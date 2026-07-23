<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { DocumentItem } from '../types'

const props = defineProps<{
  documents: DocumentItem[]
  busy?: boolean
  pendingIds: string[]
}>()

const listElement = ref<HTMLUListElement | null>(null)
const previewIds = ref<string[]>([])
const draggingId = ref<string | null>(null)
const statusMessage = ref('')
let pointerState: {
  documentId: string
  pointerId: number
  row: HTMLElement
  startY: number
} | null = null

watch(
  () => props.documents,
  (documents) => {
    previewIds.value = documents.map((document) => document.id)
  },
  { immediate: true },
)

const orderedDocuments = computed(() => {
  const byId = new Map(props.documents.map((document) => [document.id, document]))
  return previewIds.value
    .map((documentId) => byId.get(documentId))
    .filter((document): document is DocumentItem => document !== undefined)
})

function moveDocument(documentIds: string[], documentId: string, index: number): string[] {
  const withoutDocument = documentIds.filter((id) => id !== documentId)
  const boundedIndex = Math.max(0, Math.min(index, withoutDocument.length))
  withoutDocument.splice(boundedIndex, 0, documentId)
  return withoutDocument
}

function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest('input, button, a, select, textarea'))
}

function onPointerDown(event: PointerEvent, documentId: string) {
  if (props.busy || event.button !== 0 || isInteractiveTarget(event.target)) return
  const row = event.currentTarget as HTMLElement
  pointerState = {
    documentId,
    pointerId: event.pointerId,
    row,
    startY: event.clientY,
  }
  try {
    row.setPointerCapture(event.pointerId)
  } catch {
    // Synthetic events and older browsers may not support pointer capture.
  }
}

function onPointerMove(event: PointerEvent) {
  if (!pointerState || pointerState.pointerId !== event.pointerId || props.busy) return
  if (draggingId.value === null && Math.abs(event.clientY - pointerState.startY) < 6) return
  event.preventDefault()
  draggingId.value = pointerState.documentId

  const rows = [...(listElement.value?.querySelectorAll<HTMLElement>('.document-row') ?? [])]
    .filter((row) => row.dataset.documentId !== pointerState?.documentId)
  const insertionIndex = rows.findIndex((row) => {
    const rect = row.getBoundingClientRect()
    return event.clientY < rect.top + rect.height / 2
  })
  previewIds.value = moveDocument(
    previewIds.value,
    pointerState.documentId,
    insertionIndex === -1 ? rows.length : insertionIndex,
  )
}

function announceAndEmit(documentId: string) {
  const savedIds = props.documents.map((document) => document.id)
  if (previewIds.value.every((documentId, index) => documentId === savedIds[index])) return
  const position = previewIds.value.indexOf(documentId) + 1
  statusMessage.value = `已移到第 ${position} 项，正在保存`
  emit('reorder', [...previewIds.value])
}

function finishPointer(event: PointerEvent, cancelled = false) {
  if (!pointerState || pointerState.pointerId !== event.pointerId) return
  const { documentId, row } = pointerState
  try {
    row.releasePointerCapture(event.pointerId)
  } catch {
    // The browser may have released capture before pointercancel.
  }
  if (cancelled) {
    previewIds.value = props.documents.map((document) => document.id)
  } else if (draggingId.value !== null) {
    announceAndEmit(documentId)
  }
  draggingId.value = null
  pointerState = null
}

function onRowKeydown(event: KeyboardEvent, documentId: string) {
  if (props.busy || !event.altKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return
  const currentIndex = previewIds.value.indexOf(documentId)
  const nextIndex = currentIndex + (event.key === 'ArrowUp' ? -1 : 1)
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= previewIds.value.length) return
  event.preventDefault()
  previewIds.value = moveDocument(previewIds.value, documentId, nextIndex)
  announceAndEmit(documentId)
}

const emit = defineEmits<{
  rename: [document: DocumentItem, title: string]
  delete: [document: DocumentItem]
  reorder: [documentIds: string[]]
}>()

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

    <span id="document-order-instructions" class="visually-hidden">
      按住资料行拖动排序，或使用 Alt 加上下方向键移动。
    </span>
    <span class="visually-hidden" role="status" aria-live="polite">{{ statusMessage }}</span>

    <ul v-if="documents.length > 0" ref="listElement" class="document-list">
      <li
        v-for="document in orderedDocuments"
        :key="document.id"
        class="document-row"
        :class="{
          'document-row--busy': busy,
          'document-row--dragging': draggingId === document.id,
        }"
        :data-document-id="document.id"
        :aria-disabled="busy || undefined"
        aria-describedby="document-order-instructions"
        tabindex="0"
        @keydown="onRowKeydown($event, document.id)"
        @pointerdown="onPointerDown($event, document.id)"
        @pointermove="onPointerMove"
        @pointerup="finishPointer($event)"
        @pointercancel="finishPointer($event, true)"
      >
        <div class="document-row__heading">
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
