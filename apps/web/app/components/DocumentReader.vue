<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import type { DocumentItem } from '../types/content'

const props = withDefaults(
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

type ContentState = 'idle' | 'probing' | 'frame-loading' | 'ready' | 'error'

const contentState = ref<ContentState>('idle')
const contentError = ref<string | null>(null)
const frameSrc = ref<string | null>(null)
const frameGeneration = ref(0)
let requestGeneration = 0
let probeController: AbortController | null = null

const readerBusy = computed(
  () => props.loading || contentState.value === 'probing' || contentState.value === 'frame-loading',
)

function abortProbe() {
  probeController?.abort()
  probeController = null
}

async function probeContent() {
  const generation = ++requestGeneration
  abortProbe()
  contentError.value = null
  frameSrc.value = null
  contentState.value = 'idle'

  const document = props.document
  if (props.loading || props.error || !document) return

  const controller = new AbortController()
  probeController = controller
  contentState.value = 'probing'

  try {
    const response = await fetch(document.content_url, {
      method: 'HEAD',
      signal: controller.signal,
    })
    if (generation !== requestGeneration || controller.signal.aborted) return
    if (!response.ok) throw new Error(`资料内容暂不可用（${response.status}）`)

    frameGeneration.value = generation
    frameSrc.value = document.content_url
    contentState.value = 'frame-loading'
  } catch (error) {
    if (generation !== requestGeneration || controller.signal.aborted) return
    contentError.value = error instanceof Error ? error.message : '资料内容暂时无法读取'
    contentState.value = 'error'
  } finally {
    if (probeController === controller) probeController = null
  }
}

function iframeEventGeneration(event: Event): number {
  return Number((event.currentTarget as HTMLIFrameElement).dataset.readerGeneration)
}

function handleFrameLoad(event: Event) {
  if (
    iframeEventGeneration(event) === requestGeneration &&
    contentState.value === 'frame-loading'
  ) {
    contentState.value = 'ready'
  }
}

function handleFrameError(event: Event) {
  if (iframeEventGeneration(event) !== requestGeneration) return
  frameSrc.value = null
  contentError.value = '资料页面加载失败，请重新载入。'
  contentState.value = 'error'
}

watch(
  [() => props.document?.id ?? null, () => props.loading, () => props.error],
  () => void probeContent(),
  { immediate: true },
)

onBeforeUnmount(() => {
  requestGeneration += 1
  abortProbe()
})
</script>

<template>
  <section class="document-reader" aria-label="资料阅读区" :aria-busy="readerBusy">
    <div v-if="loading" class="reader-state" role="status" aria-live="polite">
      <span class="reader-progress" aria-hidden="true" />
      <div>
        <strong>正在读取资料目录</strong>
        <p>找到资料后将在这里打开。</p>
      </div>
    </div>

    <div v-else-if="error" class="reader-state reader-state--error" role="alert">
      <div>
        <strong>资料目录暂时无法读取</strong>
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

    <div v-else-if="contentState === 'error'" class="reader-state reader-state--error" role="alert">
      <div>
        <strong>资料内容暂时无法读取</strong>
        <p>{{ contentError }}</p>
      </div>
      <button name="retry-content" type="button" @click="probeContent">重新载入</button>
    </div>

    <template v-else>
      <div
        v-if="contentState === 'probing' || contentState === 'frame-loading'"
        class="reader-state"
        :class="{ 'reader-state--frame-loading': contentState === 'frame-loading' }"
        role="status"
        aria-live="polite"
      >
        <span class="reader-progress" aria-hidden="true" />
        <div>
          <strong>{{ contentState === 'probing' ? '正在检查资料内容' : '正在打开资料' }}</strong>
          <p>{{ contentState === 'probing' ? '确认资料可读取后再打开。' : '页面加载完成后即可阅读。' }}</p>
        </div>
      </div>

      <iframe
        v-if="frameSrc"
        class="document-frame"
        :src="frameSrc"
        sandbox=""
        :title="`阅读：${document.title}`"
        :data-reader-generation="frameGeneration"
        @load="handleFrameLoad"
        @error="handleFrameError"
      />
    </template>
  </section>
</template>
