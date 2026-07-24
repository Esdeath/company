<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import {
  createComment,
  deleteComment,
  getCommentThread,
  isUserAuthenticationRequired,
  listDocumentComments,
  reportComment,
  updateComment,
} from '../api/community'
import type { Comment, CommentPage, User } from '../types/community'
import CommentItem from './CommentItem.vue'

type CurrentUser = User

const MAX_COMMENT_LENGTH = 2000

const props = defineProps<{
  documentId: string
  currentUser: CurrentUser | null
  targetCommentId: string | null
}>()

const emit = defineEmits<{
  'login-required': []
  'target-resolved': [commentId: string]
}>()

const roots = ref<Comment[]>([])
const threadRoots = ref<Comment[]>([])
const viewerPending = ref<Comment[]>([])
const threadViewerPending = ref<Comment[]>([])
const nextCursor = ref<string | null>(null)
const totalCount = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const errorMessage = ref<string | null>(null)
const publishing = ref(false)
const draft = ref('')
const replyTo = ref<string | null>(null)
const replyDraft = ref('')
const editingCommentId = ref<string | null>(null)
const editingDraft = ref('')
const reportedIds = ref<string[]>([])
const reportingIds = ref<string[]>([])
const actionError = ref<string | null>(null)

const commentDrafts = new Map<string, string>()
const replyDrafts = new Map<string, { parentId: string | null; body: string }>()
let listGeneration = 0
let threadGeneration = 0

const visibleRoots = computed(() => {
  const allRoots = mergeById([...roots.value, ...threadRoots.value])
  const publicRoots = allRoots.map((root) => ({ ...root, replies: sortOldest(root.replies) }))
  const pendingRoots: Comment[] = []

  for (const pending of mergeById([...viewerPending.value, ...threadViewerPending.value])) {
    if (pending.parent_id) {
      const parent = publicRoots.find((root) => root.id === pending.parent_id)
      if (parent) {
        parent.replies = sortOldest(mergeById([...parent.replies, pending]))
        continue
      }
    }
    pendingRoots.push(pending)
  }

  return {
    publicRoots: sortNewest(publicRoots),
    pendingRoots: sortNewest(pendingRoots),
  }
})

const canPublish = computed(
  () => Boolean(props.currentUser) && draft.value.trim().length > 0 && draft.value.length <= MAX_COMMENT_LENGTH && !publishing.value,
)

function sortNewest(items: Comment[]): Comment[] {
  return [...items].sort((left, right) => right.created_at.localeCompare(left.created_at))
}

function sortOldest(items: Comment[]): Comment[] {
  return [...items].sort((left, right) => left.created_at.localeCompare(right.created_at))
}

function mergeById(items: Comment[]): Comment[] {
  const byId = new Map<string, Comment>()
  for (const item of items) {
    const existing = byId.get(item.id)
    byId.set(item.id, existing ? { ...existing, ...item, replies: mergeById([...existing.replies, ...item.replies]) } : item)
  }
  return [...byId.values()]
}

function mapCommentTree(items: Comment[], commentId: string, mutate: (comment: Comment) => Comment): Comment[] {
  return items.map((item) => {
    if (item.id === commentId) return mutate(item)
    return { ...item, replies: item.replies.map((reply) => (reply.id === commentId ? mutate(reply) : reply)) }
  })
}

function mutatePublicTrees(commentId: string, mutate: (comment: Comment) => Comment) {
  roots.value = mapCommentTree(roots.value, commentId, mutate)
  threadRoots.value = mapCommentTree(threadRoots.value, commentId, mutate)
}

function publicComment(comment: Comment): Comment {
  return {
    ...comment,
    can_edit: false,
    can_delete: false,
    can_report: false,
    replies: comment.replies.map(publicComment),
  }
}

function errorText(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '评论暂时无法处理，请稍后重试'
}

function saveDrafts(documentId: string) {
  commentDrafts.set(documentId, draft.value)
  replyDrafts.set(documentId, { parentId: replyTo.value, body: replyDraft.value })
}

function restoreDrafts(documentId: string) {
  draft.value = commentDrafts.get(documentId) ?? ''
  const savedReply = replyDrafts.get(documentId)
  replyTo.value = savedReply?.parentId ?? null
  replyDraft.value = savedReply?.body ?? ''
}

async function loadComments(reset = true) {
  const generation = ++listGeneration
  if (reset) {
    loading.value = true
    errorMessage.value = null
  } else {
    loadingMore.value = true
  }

  const cursor = reset ? null : nextCursor.value
  try {
    const page = await listDocumentComments(props.documentId, cursor)
    if (generation !== listGeneration) return
    applyPage(page, reset)
  } catch (error) {
    if (generation !== listGeneration) return
    errorMessage.value = errorText(error)
  } finally {
    if (generation === listGeneration) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

function applyPage(page: CommentPage, reset: boolean) {
  roots.value = reset ? page.items : mergeById([...roots.value, ...page.items])
  viewerPending.value = reset ? page.viewer_pending : mergeById([...viewerPending.value, ...page.viewer_pending])
  nextCursor.value = page.next_cursor
  totalCount.value = reset ? page.total_count : Math.max(totalCount.value, page.total_count)
}

async function loadTargetThread(commentId: string) {
  const generation = ++threadGeneration
  try {
    const thread = await getCommentThread(commentId)
    if (generation !== threadGeneration) return
    threadRoots.value = mergeById([...threadRoots.value, thread.root])
    threadViewerPending.value = thread.viewer_pending
    emit('target-resolved', thread.target_comment_id)
  } catch {
    // The regular list remains useful when a deep-linked comment was removed.
  }
}

function requestLogin() {
  emit('login-required')
}

async function publish(parentId: string | null = null) {
  const body = (parentId ? replyDraft.value : draft.value).trim()
  if (!props.currentUser) {
    requestLogin()
    return
  }
  if (!body || body.length > MAX_COMMENT_LENGTH || publishing.value) return

  publishing.value = true
  actionError.value = null
  try {
    const created = await createComment(props.documentId, { body, parent_id: parentId })
    if (created.status === 'pending') {
      viewerPending.value = mergeById([...viewerPending.value, created])
    } else if (created.parent_id) {
      mutatePublicTrees(created.parent_id, (root) => ({
        ...root,
        replies: mergeById([...root.replies, created]),
      }))
    } else {
      roots.value = mergeById([...roots.value, created])
      totalCount.value += 1
    }
    if (parentId) {
      replyDraft.value = ''
      replyTo.value = null
    } else {
      draft.value = ''
    }
  } catch (error) {
    if (isUserAuthenticationRequired(error)) requestLogin()
    else actionError.value = errorText(error)
  } finally {
    publishing.value = false
  }
}

function beginReply(commentId: string) {
  replyTo.value = commentId
  editingCommentId.value = null
}

function beginEdit(commentId: string) {
  const existing = findComment(commentId)
  if (!existing || existing.status === 'deleted') return
  editingCommentId.value = commentId
  editingDraft.value = existing.body ?? ''
  replyTo.value = null
}

function findComment(commentId: string): Comment | null {
  for (const root of [...roots.value, ...threadRoots.value, ...viewerPending.value, ...threadViewerPending.value]) {
    if (root.id === commentId) return root
    const reply = root.replies.find((item) => item.id === commentId)
    if (reply) return reply
  }
  return null
}

function replaceComment(updated: Comment) {
  const mergeUpdatedComment = (existing: Comment): Comment => ({
    ...existing,
    ...updated,
    replies: updated.replies.length ? mergeById([...existing.replies, ...updated.replies]) : existing.replies,
  })
  mutatePublicTrees(updated.id, mergeUpdatedComment)
  viewerPending.value = mapCommentTree(viewerPending.value, updated.id, mergeUpdatedComment)
  threadViewerPending.value = mapCommentTree(threadViewerPending.value, updated.id, mergeUpdatedComment)
}

async function saveEdit(commentId: string) {
  const body = editingDraft.value.trim()
  if (!body || body.length > MAX_COMMENT_LENGTH) return
  actionError.value = null
  try {
    replaceComment(await updateComment(commentId, { body }))
    editingCommentId.value = null
    editingDraft.value = ''
  } catch (error) {
    if (isUserAuthenticationRequired(error)) requestLogin()
    else actionError.value = errorText(error)
  }
}

async function removeComment(commentId: string) {
  actionError.value = null
  try {
    replaceComment(await deleteComment(commentId))
  } catch (error) {
    if (isUserAuthenticationRequired(error)) requestLogin()
    else actionError.value = errorText(error)
  }
}

async function report(commentId: string) {
  if (reportedIds.value.includes(commentId) || reportingIds.value.includes(commentId)) return
  actionError.value = null
  reportingIds.value = [...reportingIds.value, commentId]
  try {
    await reportComment(commentId, { reason: 'spam' })
    reportedIds.value = [...reportedIds.value, commentId]
  } catch (error) {
    if (isUserAuthenticationRequired(error)) requestLogin()
    else actionError.value = errorText(error)
  } finally {
    reportingIds.value = reportingIds.value.filter((id) => id !== commentId)
  }
}

function retry() {
  void loadComments(true)
}

function loadMore() {
  if (!nextCursor.value || loadingMore.value || loading.value) return
  void loadComments(false)
}

watch(
  () => props.documentId,
  (documentId, previousDocumentId) => {
    if (previousDocumentId) saveDrafts(previousDocumentId)
    listGeneration += 1
    threadGeneration += 1
    roots.value = []
    threadRoots.value = []
    viewerPending.value = []
    threadViewerPending.value = []
    nextCursor.value = null
    totalCount.value = 0
    errorMessage.value = null
    actionError.value = null
    editingCommentId.value = null
    restoreDrafts(documentId)
    void loadComments(true)
  },
  { immediate: true },
)

watch(
  () => props.currentUser?.id ?? null,
  () => {
    listGeneration += 1
    threadGeneration += 1
    roots.value = roots.value.map(publicComment)
    threadRoots.value = threadRoots.value.map(publicComment)
    viewerPending.value = []
    threadViewerPending.value = []
    reportedIds.value = []
    reportingIds.value = []
    actionError.value = null
    void loadComments(true)
    if (props.targetCommentId) void loadTargetThread(props.targetCommentId)
  },
)

watch(
  () => props.targetCommentId,
  (targetCommentId) => {
    threadGeneration += 1
    threadRoots.value = []
    threadViewerPending.value = []
    if (targetCommentId) void loadTargetThread(targetCommentId)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  saveDrafts(props.documentId)
  listGeneration += 1
  threadGeneration += 1
})
</script>

<template>
  <section class="comment-section" aria-label="评论">
    <header class="comment-section__header">
      <div>
        <p>读者讨论</p>
        <h2>评论</h2>
      </div>
      <span>{{ totalCount }} 条</span>
    </header>

    <div v-if="!currentUser" class="comment-section__login-prompt">
      <p>登录后即可发表评论。</p>
      <button name="login-to-comment" type="button" @click="requestLogin">登录</button>
    </div>
    <form v-else class="comment-section__composer" @submit.prevent="publish()">
      <label for="comment-body">发表评论</label>
      <textarea id="comment-body" v-model="draft" name="comment-body" :maxlength="MAX_COMMENT_LENGTH" />
      <div class="comment-section__composer-footer">
        <span :class="{ 'comment-section__counter--limit': draft.length > MAX_COMMENT_LENGTH }">{{ draft.length }} / 2,000</span>
        <button name="publish-comment" type="submit" :disabled="!canPublish">发布</button>
      </div>
    </form>

    <p v-if="actionError" class="comment-section__alert" role="alert">{{ actionError }}</p>

    <div v-if="loading" class="comment-section__state" role="status" aria-live="polite">正在加载评论</div>
    <div v-else-if="errorMessage" class="comment-section__state comment-section__state--error" role="alert">
      <p>{{ errorMessage }}</p>
      <button name="retry-comments" type="button" @click="retry">重新载入</button>
    </div>
    <template v-else>
      <section v-if="visibleRoots.pendingRoots.length" class="comment-section__pending" aria-label="仅你可见的待审核评论">
        <p>仅你可见</p>
        <ol>
          <li v-for="comment in visibleRoots.pendingRoots" :key="comment.id">
            <CommentItem
              :comment="comment"
              :editing-comment-id="editingCommentId"
              :editing-body="editingDraft"
              :reported-ids="reportedIds"
              :reporting-ids="reportingIds"
              @reply="beginReply"
              @edit="beginEdit"
              @delete="removeComment"
              @report="report"
              @edit-draft="editingDraft = $event"
              @save-edit="saveEdit"
              @cancel-edit="editingCommentId = null"
            />
          </li>
        </ol>
      </section>

      <ol v-if="visibleRoots.publicRoots.length" class="comment-section__list">
        <li v-for="comment in visibleRoots.publicRoots" :key="comment.id">
          <CommentItem
            :comment="comment"
            :editing-comment-id="editingCommentId"
            :editing-body="editingDraft"
            :reported-ids="reportedIds"
            :reporting-ids="reportingIds"
            @reply="beginReply"
            @edit="beginEdit"
            @delete="removeComment"
            @report="report"
            @edit-draft="editingDraft = $event"
            @save-edit="saveEdit"
            @cancel-edit="editingCommentId = null"
          />
          <form v-if="replyTo === comment.id" class="comment-section__reply" @submit.prevent="publish(comment.id)">
            <label :for="`reply-body-${comment.id}`">回复评论</label>
            <textarea :id="`reply-body-${comment.id}`" v-model="replyDraft" :name="`reply-body-${comment.id}`" :maxlength="MAX_COMMENT_LENGTH" />
            <div class="comment-section__composer-footer">
              <span>{{ replyDraft.length }} / 2,000</span>
              <button :name="`publish-reply-${comment.id}`" type="submit" :disabled="!currentUser || !replyDraft.trim() || replyDraft.length > MAX_COMMENT_LENGTH || publishing">发布回复</button>
              <button :name="`cancel-reply-${comment.id}`" type="button" @click="replyTo = null">取消</button>
            </div>
          </form>
        </li>
      </ol>
      <p v-else-if="!visibleRoots.pendingRoots.length" class="comment-section__empty">还没有评论，写下第一条吧。</p>
      <button v-if="nextCursor" name="load-more-comments" type="button" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? '正在加载' : '加载更多' }}
      </button>
    </template>
  </section>
</template>

<style scoped>
.comment-section {
  display: grid;
  gap: 1rem;
  padding-block: 2rem;
  border-top: 1px solid var(--line);
}

.comment-section__header,
.comment-section__composer-footer {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}

.comment-section__header p,
.comment-section__pending > p {
  margin: 0 0 0.25rem;
  color: var(--green);
  font-family: var(--font-utility);
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.comment-section__header h2 {
  font-size: 1.25rem;
}

.comment-section__header > span,
.comment-section__composer-footer,
.comment-section__login-prompt,
.comment-section__empty {
  color: var(--muted);
  font-size: 0.78rem;
}

.comment-section__composer,
.comment-section__reply {
  display: grid;
  gap: 0.55rem;
}

.comment-section textarea {
  width: 100%;
  min-height: 7rem;
  padding: 0.65rem;
  border: 1px solid var(--line);
  border-radius: 0;
  background: var(--paper);
  color: var(--ink);
  font: inherit;
  line-height: 1.6;
  resize: vertical;
}

.comment-section button {
  min-height: 2rem;
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--green);
  border-radius: 0;
  background: transparent;
}

.comment-section button:disabled {
  cursor: default;
  opacity: 0.55;
}

.comment-section__counter--limit,
.comment-section__alert,
.comment-section__state--error {
  color: var(--red);
}

.comment-section__state,
.comment-section__empty {
  padding-block: 1.25rem;
}

.comment-section__login-prompt,
.comment-section__state--error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

.comment-section__login-prompt p,
.comment-section__state--error p {
  margin: 0;
}

.comment-section__list,
.comment-section__pending ol {
  margin: 0;
  padding: 0;
}

.comment-section__list > li,
.comment-section__pending li {
  list-style: none;
}

.comment-section__pending {
  padding: 0.85rem 1rem;
  border: 1px solid var(--line);
  background: var(--green-soft);
}

.comment-section__reply {
  padding-block: 0.75rem 1rem;
}
</style>
