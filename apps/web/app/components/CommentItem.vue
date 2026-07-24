<script setup lang="ts">
import { computed, ref } from 'vue'

import { linkifyComment } from '../utils/linkifyComment'
import type { Comment, CommentReportInput } from '../types/community'

type ReportReason = 'spam' | 'harassment' | 'illegal' | 'other'

const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: 'spam', label: '垃圾广告或重复内容' },
  { value: 'harassment', label: '骚扰或人身攻击' },
  { value: 'illegal', label: '违法或危险内容' },
  { value: 'other', label: '其他问题' },
]

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
  report: [commentId: string, input: CommentReportInput]
  'edit-draft': [body: string]
  'save-edit': [commentId: string]
  'cancel-edit': []
}>()

const confirmingDelete = ref(false)
const reportFormOpen = ref(false)
const reportReason = ref<ReportReason | ''>('')
const reportDetails = ref('')
const bodySegments = computed(() => linkifyComment(props.comment.body ?? ''))
const authorName = computed(() => (props.comment.author.id ? props.comment.author.username : '已注销用户'))
const canReply = computed(() => props.comment.status === 'published')
const isEditing = computed(() => props.editingCommentId === props.comment.id)
const isReported = computed(() => props.reportedIds.includes(props.comment.id))
const isReporting = computed(() => props.reportingIds.includes(props.comment.id))
const hasReplies = computed(() => props.depth === 0 && props.comment.replies.length > 0)
const canSubmitReport = computed(
  () =>
    Boolean(reportReason.value) &&
    reportReason.value.length <= 100 &&
    reportDetails.value.length <= 2000 &&
    !isReported.value &&
    !isReporting.value,
)

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

function openReport() {
  if (isReported.value || isReporting.value) return
  reportFormOpen.value = true
}

function cancelReport() {
  if (isReporting.value) return
  reportFormOpen.value = false
  reportReason.value = ''
  reportDetails.value = ''
}

function submitReport() {
  if (!canSubmitReport.value || !reportReason.value) return
  const details = reportDetails.value.trim()
  emit('report', props.comment.id, {
    reason: reportReason.value,
    ...(details ? { details } : {}),
  })
}

function forwardReport(commentId: string, input: CommentReportInput) {
  emit('report', commentId, input)
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
        @click="openReport"
      >{{ isReported ? '已举报' : isReporting ? '正在举报' : '举报' }}</button>
    </div>

    <div v-if="confirmingDelete" class="comment-item__confirm" role="alert">
      <span>确定删除这条评论？</span>
      <button :name="`confirm-delete-${comment.id}`" type="button" @click="confirmDelete">确定删除</button>
      <button :name="`cancel-delete-${comment.id}`" type="button" @click="cancelDelete">取消</button>
    </div>

    <form
      v-if="reportFormOpen && !isReported"
      class="comment-item__report"
      :data-report-comment-id="comment.id"
      @submit.prevent="submitReport"
    >
      <label :for="`report-reason-${comment.id}`">举报原因</label>
      <select
        :id="`report-reason-${comment.id}`"
        v-model="reportReason"
        :name="`report-reason-${comment.id}`"
        :disabled="isReporting"
        required
      >
        <option value="" disabled>请选择原因</option>
        <option v-for="reason in REPORT_REASONS" :key="reason.value" :value="reason.value">
          {{ reason.label }}
        </option>
      </select>
      <label :for="`report-details-${comment.id}`">补充说明（选填）</label>
      <textarea
        :id="`report-details-${comment.id}`"
        v-model="reportDetails"
        :name="`report-details-${comment.id}`"
        :disabled="isReporting"
        maxlength="2000"
      />
      <div class="comment-item__report-commands">
        <button :name="`confirm-report-${comment.id}`" type="submit" :disabled="!canSubmitReport">
          {{ isReporting ? '正在提交' : '确认举报' }}
        </button>
        <button :name="`cancel-report-${comment.id}`" type="button" :disabled="isReporting" @click="cancelReport">
          取消
        </button>
      </div>
    </form>

    <ol v-if="hasReplies" class="comment-item__replies">
      <li v-for="reply in comment.replies" :key="reply.id">
        <CommentItem
          :comment="reply"
          :depth="1"
          :editing-comment-id="editingCommentId"
          :editing-body="editingBody"
          :reported-ids="reportedIds"
          :reporting-ids="reportingIds"
          @reply="emit('reply', $event)"
          @edit="emit('edit', $event)"
          @delete="emit('delete', $event)"
          @report="forwardReport"
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

.comment-item__edit textarea,
.comment-item__report textarea {
  width: 100%;
  min-height: 6rem;
  resize: vertical;
}

.comment-item__report {
  display: grid;
  gap: 0.5rem;
  margin-block: 0.7rem;
  padding-block-start: 0.7rem;
  border-top: 1px solid var(--line);
}

.comment-item__report label {
  color: var(--muted);
  font-size: 0.76rem;
}

.comment-item__report select,
.comment-item__report textarea {
  box-sizing: border-box;
  padding: 0.55rem;
  border: 1px solid var(--line);
  background: var(--paper);
  color: inherit;
  font: inherit;
}

.comment-item__report textarea {
  min-height: 4.5rem;
}

.comment-item__report-commands {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}
</style>
