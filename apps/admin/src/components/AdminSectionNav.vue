<script setup lang="ts">
import { nextTick } from 'vue'

import type { AdminSection } from '../types'

defineProps<{ active: AdminSection }>()

const emit = defineEmits<{ select: [section: AdminSection] }>()

const sections: Array<{ id: AdminSection; label: string }> = [
  { id: 'documents', label: '资料' },
  { id: 'comments', label: '评论审核' },
  { id: 'users', label: '用户' },
]

async function selectWithKeyboard(section: AdminSection, event: KeyboardEvent) {
  const currentIndex = sections.findIndex((item) => item.id === section)
  let nextIndex: number | null = null
  if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    nextIndex = (currentIndex - 1 + sections.length) % sections.length
  } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    nextIndex = (currentIndex + 1) % sections.length
  } else if (event.key === 'Home') {
    nextIndex = 0
  } else if (event.key === 'End') {
    nextIndex = sections.length - 1
  }
  if (nextIndex === null) return
  event.preventDefault()
  const next = sections[nextIndex]!.id
  emit('select', next)
  await nextTick()
  document.getElementById(`admin-tab-${next}`)?.focus()
}
</script>

<template>
  <nav class="admin-section-nav" role="tablist" aria-label="管理工作区">
    <button
      v-for="section in sections"
      :key="section.id"
      class="admin-section-tab"
      :class="{ 'admin-section-tab--active': active === section.id }"
      type="button"
      role="tab"
      :id="`admin-tab-${section.id}`"
      :tabindex="active === section.id ? 0 : -1"
      :aria-selected="active === section.id"
      :aria-controls="`admin-panel-${section.id}`"
      @click="emit('select', section.id)"
      @keydown="selectWithKeyboard(section.id, $event)"
    >
      {{ section.label }}
    </button>
  </nav>
</template>
