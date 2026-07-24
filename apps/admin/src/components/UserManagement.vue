<script setup lang="ts">
import { ref } from 'vue'

import {
  isAuthenticationRequired,
  isModerationConflict,
  listModerationUsers,
  restoreUser,
  suspendUser,
} from '../api'
import type { ModerationUser } from '../types'

const emit = defineEmits<{ authenticationRequired: [] }>()

const query = ref('')
const searchedQuery = ref('')
const users = ref<ModerationUser[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const pendingIds = ref<string[]>([])
let requestGeneration = 0

function errorMessage(caught: unknown): string {
  if (isAuthenticationRequired(caught)) emit('authenticationRequired')
  return caught instanceof Error ? caught.message : '操作未完成，请稍后重试'
}

async function search(cursor?: string, append = false) {
  const normalized = searchedQuery.value
  if (!normalized) return
  const generation = ++requestGeneration
  error.value = ''
  if (append) loadingMore.value = true
  else loading.value = true
  try {
    const page = await listModerationUsers(normalized, cursor)
    if (generation !== requestGeneration) return
    users.value = append ? [...users.value, ...page.items] : page.items
    nextCursor.value = page.next_cursor
  } catch (caught) {
    if (generation === requestGeneration) error.value = errorMessage(caught)
  } finally {
    if (generation === requestGeneration) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function submitSearch() {
  searchedQuery.value = query.value.trim()
  users.value = []
  nextCursor.value = null
  if (!searchedQuery.value) {
    error.value = '请输入用户名或邮箱'
    return
  }
  void search()
}

function isPending(id: string): boolean {
  return pendingIds.value.includes(id)
}

async function updateUser(user: ModerationUser, operation: () => Promise<ModerationUser>) {
  if (isPending(user.id)) return
  pendingIds.value = [...pendingIds.value, user.id]
  error.value = ''
  try {
    const saved = await operation()
    users.value = users.value.map((item) => (item.id === saved.id ? saved : item))
  } catch (caught) {
    if (isModerationConflict(caught)) void search()
    else error.value = errorMessage(caught)
  } finally {
    pendingIds.value = pendingIds.value.filter((id) => id !== user.id)
  }
}

async function suspend(user: ModerationUser) {
  if (!window.confirm(`确认停用用户 ${user.username}？其现有登录会话将立即失效。`)) return
  await updateUser(user, () => suspendUser(user.id))
}

async function restore(user: ModerationUser) {
  await updateUser(user, () => restoreUser(user.id))
}
</script>

<template>
  <section class="user-workspace" aria-labelledby="users-title">
    <div class="section-label">
      <p>社区管理</p>
      <h2 id="users-title">用户管理</h2>
    </div>
    <form class="user-search" aria-label="搜索用户" @submit.prevent="submitSearch">
      <label for="user-search">用户名或邮箱</label>
      <input id="user-search" v-model="query" name="user-search" autocomplete="off" />
      <button class="text-action" type="submit" :disabled="loading">搜索</button>
    </form>
    <p v-if="error" class="moderation-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state" aria-live="polite">正在查询用户…</p>
    <p v-else-if="searchedQuery && users.length === 0" class="empty-state">没有匹配的用户。</p>
    <ul v-else-if="users.length" class="user-list">
      <li v-for="user in users" :key="user.id" class="user-row">
        <div class="user-row__heading"><span class="moderation-author">{{ user.username }}</span><span class="format-badge">{{ user.status === 'suspended' ? '已停用' : '正常' }}</span></div>
        <p class="moderation-meta">{{ user.email }} · {{ user.comment_count }} 条评论</p>
        <div class="moderation-actions">
          <button v-if="user.status === 'active'" class="text-action text-action--danger" type="button" :aria-label="`停用用户 ${user.username}`" :disabled="isPending(user.id)" @click="suspend(user)">停用</button>
          <button v-else class="text-action" type="button" :aria-label="`恢复用户 ${user.username}`" :disabled="isPending(user.id)" @click="restore(user)">恢复</button>
        </div>
      </li>
    </ul>
    <button v-if="nextCursor" class="text-action moderation-more" type="button" :disabled="loadingMore" @click="search(nextCursor ?? undefined, true)">{{ loadingMore ? '正在读取…' : '加载更多' }}</button>
  </section>
</template>
