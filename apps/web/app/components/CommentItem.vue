<script setup lang="ts">
import { computed, ref } from 'vue'

import { linkifyComment } from '../utils/linkifyComment'
import type { Comment } from '../types/community'

const props = withDefaults(
  defineProps<{
    comment: Comment
    depth?: number
    editingCommentId?: string | null
    editingBody?: string
    reportedIds?: string[]
    reportingIds?: string[]
  }>(),
  {
    depth: 0,
    editingCommentId: null,
    editingBody: '',
    reportedIds: () => [],
    reportingIds: () => [],
  },
)

const emit = defineEmits<{
  reply: [commentId: string]
  edit: [commentId: string]
  delete: [commentId: string]
  report: [commentId: string]
  'edit-draft': [body: string]
  'save-edit': [commentId: string]
  'cancel-edit': []
}>()

const confirmingDelete = ref(false)
const bodySegments = computed(() => linkifyComment(props.comment.body ?? ''))
const authorName = computed(() => (props.comment.author.id ? props.comment.author.username : '已注销用户'))
const canReply = computed(
  () => props.depth === 0 && props.comment.status === 'published' && props.comment.parent_id === null,
)
const isEditing = computed(() => props.editingCommentId === props.comment.id)
const isReported = computed(() => props.reportedIds.includes(props.comment.id))
const isReporting = computed(() => props.reportingIds.includes(props.comment.id))
const hasReplies = computed(() => props.depth === 0 && props.comment.replies.length > 0)

function requestDelete() {
  confirmingDelete.value = true
}

function cancelDelete() {
  confirmingDelete.value = false
}

function confirmDelete() {
  confirmingDelete.value = false
  emit('delete', props.comment.id)
}
</script>

<template>
  <article class="comment-item" :class="`comment-item--${comment.status}`" :data-comment-id="comment.id">
    <header class="comment-item__header">
      <strong>{{ authorName }}</strong>
      <time :datetime="comment.created_at">{{ new Date(comment.created_at).toLocaleString('zh-CN') }}</time>
      <span v-if="comment.status === 'pending'" class="comment-item__status">待审核</span>
      <span v-if="comment.edited_at" class="comment-item__edited">已编辑</span>
    </header>

    <p v-if="comment.status === 'deleted'" class="comment-item__deleted">此评论已删除</p>
    <form v-else-if="isEditing" class="comment-item__edit" @submit.prevent="emit('save-edit', comment.id)">
      <label :for="`edit-body-${comment.id}`">编辑评论</label>
      <textarea
        :id="`edit-body-${comment.id}`"
        :name="`edit-body-${comment.id}`"
        :value="editingBody"
        maxlength="2000"
        @input="emit('edit-draft', ($event.target as HTMLTextAreaElement).value)"
      />
      <div class="comment-item__commands">
        <button :name="`save-edit-${comment.id}`" type="submit">保存</button>
        <button :name="`cancel-edit-${comment.id}`" type="button" @click="emit('cancel-edit')">取消</button>
      </div>
    </form>
    <p v-else class="comment-item__body">
      <template v-for="(segment, index) in bodySegments" :key="`${segment.value}-${index}`">
        <a
          v-if="segment.type === 'link'"
          :href="segment.href"
          target="_blank"
          rel="noopener noreferrer"
        >{{ segment.value }}</a>
        <template v-else>{{ segment.value }}</template>
      </template>
    </p>

    <div class="comment-item__commands" aria-label="评论操作">
      <button
        :name="`reply-${comment.id}`"
        type="button"
        :disabled="!canReply"
        @click="emit('reply', comment.id)"
      >回复</button>
      <button v-if="comment.can_edit && comment.status !== 'deleted'" :name="`edit-${comment.id}`" type="button" @click="emit('edit', comment.id)">编辑</button>
      <button v-if="comment.can_delete && comment.status !== 'deleted'" :name="`delete-${comment.id}`" type="button" @click="requestDelete">删除</button>
      <button
        v-if="comment.can_report && comment.status !== 'deleted'"
        :name="`report-${comment.id}`"
        type="button"
        :disabled="isReported || isReporting"
        @click="emit('report', comment.id)"
      >{{ isReported ? '已举报' : isReporting ? '正在举报' : '举报' }}</button>
    </div>

    <div v-if="confirmingDelete" class="comment-item__confirm" role="alert">
      <span>确定删除这条评论？</span>
      <button :name="`confirm-delete-${comment.id}`" type="button" @click="confirmDelete">确定删除</button>
      <button :name="`cancel-delete-${comment.id}`" type="button" @click="cancelDelete">取消</button>
    </div>

    <ol v-if="hasReplies" class="comment-item__replies">
      <li v-for="reply in comment.replies" :key="reply.id">
        <CommentItem
          :comment="reply"
          :depth="1"
          :editing-comment-id="editingCommentId"
          :editing-body="editingBody"
          :reported-ids="reportedIds"
          :reporting-ids="reportingIds"
          @edit="emit('edit', $event)"
          @delete="emit('delete', $event)"
          @report="emit('report', $event)"
          @edit-draft="emit('edit-draft', $event)"
          @save-edit="emit('save-edit', $event)"
          @cancel-edit="emit('cancel-edit')"
        />
      </li>
    </ol>
  </article>
</template>

<style scoped>
.comment-item {
  padding-block: 1rem;
  border-top: 1px solid var(--line);
}

.comment-item__header,
.comment-item__commands,
.comment-item__confirm {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
}

.comment-item__header time,
.comment-item__edited,
.comment-item__status,
.comment-item__commands,
.comment-item__confirm {
  color: var(--muted);
  font-size: 0.72rem;
}

.comment-item__status {
  color: var(--green);
  font-weight: 700;
}

.comment-item__body {
  margin: 0.55rem 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
}

.comment-item__body a {
  color: var(--green);
}

.comment-item__deleted {
  margin: 0.55rem 0;
  color: var(--muted);
}

.comment-item__commands button,
.comment-item__confirm button {
  padding: 0;
  border: 0;
  background: transparent;
  text-decoration: underline;
}

.comment-item__commands button:disabled {
  cursor: default;
  opacity: 0.5;
}

.comment-item__confirm {
  margin-block-start: 0.7rem;
}

.comment-item__replies {
  margin: 0.75rem 0 0 1rem;
  padding: 0 0 0 1rem;
  border-left: 1px solid var(--line);
}

.comment-item__replies > li {
  list-style: none;
}

.comment-item__edit {
  display: grid;
  gap: 0.55rem;
  margin-block: 0.65rem;
}

.comment-item__edit textarea {
  width: 100%;
  min-height: 6rem;
  resize: vertical;
}
</style>
