<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  approveComment,
  isAuthenticationRequired,
  isModerationConflict,
  listCommentReports,
  listModerationComments,
  rejectComment,
  removeComment,
  resolveCommentReport,
} from '../api'
import type { CommentStatus, ModerationComment, ModerationReport, ReportStatus } from '../types'

type ModerationView = 'pending' | 'reports' | 'all'

const emit = defineEmits<{ authenticationRequired: [] }>()

const view = ref<ModerationView>('pending')
const comments = ref<ModerationComment[]>([])
const reports = ref<ModerationReport[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const pendingIds = ref<string[]>([])
const rejectingId = ref<string | null>(null)
const rejectionReason = ref('')
let requestGeneration = 0

const currentItems = computed(() => (view.value === 'reports' ? reports.value : comments.value))
const currentLabel = computed(() => (view.value === 'reports' ? '份举报' : '条'))

function errorMessage(error: unknown): string {
  if (isAuthenticationRequired(error)) emit('authenticationRequired')
  return error instanceof Error ? error.message : '操作未完成，请稍后重试'
}

function commentStatus(): CommentStatus | undefined {
  return view.value === 'pending' ? 'pending' : undefined
}

function reportStatus(): ReportStatus | undefined {
  return view.value === 'reports' ? 'open' : undefined
}

async function refresh(cursor?: string, append = false) {
  const generation = ++requestGeneration
  error.value = ''
  if (append) loadingMore.value = true
  else loading.value = true

  try {
    if (view.value === 'reports') {
      const page = await listCommentReports(reportStatus(), cursor)
      if (generation !== requestGeneration) return
      reports.value = append ? [...reports.value, ...page.items] : page.items
      nextCursor.value = page.next_cursor
    } else {
      const page = await listModerationComments(commentStatus(), cursor)
      if (generation !== requestGeneration) return
      comments.value = append ? [...comments.value, ...page.items] : page.items
      nextCursor.value = page.next_cursor
    }
  } catch (caught) {
    if (generation === requestGeneration) error.value = errorMessage(caught)
  } finally {
    if (generation === requestGeneration) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function selectView(next: ModerationView) {
  if (view.value === next) return
  view.value = next
  nextCursor.value = null
  void refresh()
}

function isPending(id: string): boolean {
  return pendingIds.value.includes(id)
}

function beginMutation(id: string): boolean {
  if (isPending(id)) return false
  pendingIds.value = [...pendingIds.value, id]
  return true
}

function finishMutation(id: string) {
  pendingIds.value = pendingIds.value.filter((pendingId) => pendingId !== id)
}

function replaceComment(saved: ModerationComment) {
  if (view.value === 'pending' && saved.status !== 'pending') {
    comments.value = comments.value.filter((item) => item.id !== saved.id)
    return
  }
  comments.value = comments.value.map((item) => (item.id === saved.id ? saved : item))
}

async function mutateComment(
  comment: ModerationComment,
  operation: () => Promise<ModerationComment>,
) {
  if (!beginMutation(comment.id)) return
  error.value = ''
  try {
    replaceComment(await operation())
  } catch (caught) {
    if (isModerationConflict(caught)) void refresh()
    else error.value = errorMessage(caught)
  } finally {
    finishMutation(comment.id)
  }
}

async function approve(comment: ModerationComment) {
  await mutateComment(comment, () => approveComment(comment.id))
}

function showReject(comment: ModerationComment) {
  rejectingId.value = comment.id
  rejectionReason.value = ''
  error.value = ''
}

async function submitReject(comment: ModerationComment) {
  const reason = rejectionReason.value.trim()
  if (!reason) {
    error.value = '请填写驳回原因'
    return
  }
  await mutateComment(comment, () => rejectComment(comment.id, reason))
  rejectingId.value = null
  rejectionReason.value = ''
}

async function remove(comment: ModerationComment) {
  await mutateComment(comment, () => removeComment(comment.id))
}

async function resolve(report: ModerationReport, resolution: 'kept' | 'removed') {
  if (!beginMutation(report.id)) return
  error.value = ''
  try {
    const saved = await resolveCommentReport(report.id, resolution)
    if (view.value === 'reports' && saved.status !== 'open') {
      reports.value = reports.value.filter((item) => item.id !== saved.id)
    } else {
      reports.value = reports.value.map((item) => (item.id === saved.id ? saved : item))
    }
  } catch (caught) {
    if (isModerationConflict(caught)) void refresh()
    else error.value = errorMessage(caught)
  } finally {
    finishMutation(report.id)
  }
}

function author(comment: ModerationComment): string {
  return comment.author_username || '已注销用户'
}

onMounted(() => void refresh())
</script>

<template>
  <section class="moderation-workspace" aria-labelledby="moderation-title">
    <div class="section-label section-label--row">
      <div>
        <p>社区管理</p>
        <h2 id="moderation-title">评论审核</h2>
      </div>
      <span class="moderation-count">{{ currentItems.length }} {{ currentLabel }}</span>
    </div>

    <div class="moderation-tabs" role="tablist" aria-label="审核筛选">
      <button class="moderation-tab" :class="{ 'moderation-tab--active': view === 'pending' }" type="button" role="tab" :aria-selected="view === 'pending'" @click="selectView('pending')">待审</button>
      <button class="moderation-tab" :class="{ 'moderation-tab--active': view === 'reports' }" type="button" name="report-filter" role="tab" :aria-selected="view === 'reports'" @click="selectView('reports')">举报</button>
      <button class="moderation-tab" :class="{ 'moderation-tab--active': view === 'all' }" type="button" role="tab" :aria-selected="view === 'all'" @click="selectView('all')">全部</button>
    </div>

    <p v-if="error" class="moderation-error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state" aria-live="polite">正在读取审核队列…</p>
    <p v-else-if="currentItems.length === 0" class="empty-state">当前筛选没有待处理内容。</p>

    <ul v-else-if="view !== 'reports'" class="moderation-list">
      <li v-for="comment in comments" :key="comment.id" class="moderation-row">
        <div class="moderation-row__heading">
          <span class="moderation-author">{{ author(comment) }}</span>
          <span class="format-badge">{{ comment.status === 'pending' ? '待审' : comment.status }}</span>
        </div>
        <p class="moderation-meta">{{ comment.document_title }} · {{ comment.created_at }}</p>
        <p class="moderation-body">{{ comment.body || '评论正文已不可用' }}</p>
        <div class="moderation-actions">
          <button class="text-action" type="button" :aria-label="`通过 评论 ${author(comment)}`" :disabled="isPending(comment.id)" @click="approve(comment)">通过</button>
          <button class="text-action" type="button" :aria-label="`驳回 评论 ${author(comment)}`" :disabled="isPending(comment.id)" @click="showReject(comment)">驳回</button>
          <button class="text-action text-action--danger" type="button" :disabled="isPending(comment.id)" @click="remove(comment)">移除</button>
        </div>
        <form v-if="rejectingId === comment.id" class="rejection-form" aria-label="驳回评论" @submit.prevent="submitReject(comment)">
          <label :for="`rejection-${comment.id}`">驳回原因</label>
          <textarea :id="`rejection-${comment.id}`" v-model="rejectionReason" name="rejection-reason" :disabled="isPending(comment.id)" />
          <button class="text-action" type="submit" :disabled="isPending(comment.id)">确认驳回</button>
        </form>
      </li>
    </ul>

    <ul v-else class="moderation-list">
      <li v-for="report in reports" :key="report.id" class="moderation-row">
        <div class="moderation-row__heading"><span class="moderation-author">{{ report.reporter_username }}</span><span class="format-badge">举报</span></div>
        <p class="moderation-meta">{{ report.reason }} · {{ report.comment.document_title }}</p>
        <p class="moderation-body">{{ report.details || report.comment.body || '未提供补充说明' }}</p>
        <div class="moderation-actions">
          <button class="text-action" type="button" aria-label="保留被举报评论" :disabled="isPending(report.id)" @click="resolve(report, 'kept')">保留</button>
          <button class="text-action text-action--danger" type="button" aria-label="移除被举报评论" :disabled="isPending(report.id)" @click="resolve(report, 'removed')">移除</button>
        </div>
      </li>
    </ul>

    <button v-if="nextCursor" class="text-action moderation-more" type="button" :disabled="loadingMore" @click="refresh(nextCursor ?? undefined, true)">{{ loadingMore ? '正在读取…' : '加载更多' }}</button>
  </section>
</template>
