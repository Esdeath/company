<script setup lang="ts">
import type { AdminSection } from '../types'

defineProps<{ active: AdminSection }>()

const emit = defineEmits<{ select: [section: AdminSection] }>()

const sections: Array<{ id: AdminSection; label: string }> = [
  { id: 'documents', label: '资料' },
  { id: 'comments', label: '评论审核' },
  { id: 'users', label: '用户' },
]
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
      :aria-selected="active === section.id"
      @click="emit('select', section.id)"
    >
      {{ section.label }}
    </button>
  </nav>
</template>
