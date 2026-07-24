<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { deleteAccount, updatePassword, updatePreferences, updateProfile } from '../api/community'
import { useUserSession } from '../composables/useUserSession'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  deleted: []
}>()

const session = useUserSession()
const dialog = ref<HTMLElement | null>(null)
const usernameInput = ref<HTMLInputElement | null>(null)
const username = ref('')
const currentPassword = ref('')
const newPassword = ref('')
const deletePassword = ref('')
const replyEmailEnabled = ref(false)
const busy = ref<string | null>(null)
const errorMessage = ref('')
const successMessage = ref('')
let restoreFocusTo: HTMLElement | null = null

function resetMessages() {
  errorMessage.value = ''
  successMessage.value = ''
}

function errorText(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '账户操作暂时无法完成'
}

function updateSessionUser(user: NonNullable<typeof session.state.value>['user']) {
  if (!session.state.value) return
  session.state.value = { ...session.state.value, authenticated: Boolean(user), user }
}

async function saveProfile() {
  if (!username.value.trim() || busy.value) return
  busy.value = 'profile'
  resetMessages()
  try {
    const user = await updateProfile({ username: username.value.trim() })
    updateSessionUser(user)
    username.value = user.username
    successMessage.value = '用户名已更新'
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    busy.value = null
  }
}

async function savePassword() {
  if (!currentPassword.value || !newPassword.value || busy.value) return
  busy.value = 'password'
  resetMessages()
  try {
    session.state.value = await updatePassword({
      current_password: currentPassword.value,
      password: newPassword.value,
    })
    currentPassword.value = ''
    newPassword.value = ''
    successMessage.value = '密码已更新'
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    busy.value = null
  }
}

async function savePreference() {
  if (busy.value) return
  const enabled = replyEmailEnabled.value
  busy.value = 'preferences'
  resetMessages()
  try {
    updateSessionUser(await updatePreferences({ reply_email_enabled: enabled }))
    successMessage.value = '邮件提醒偏好已更新'
  } catch (error) {
    replyEmailEnabled.value = session.state.value?.user?.reply_email_enabled ?? false
    errorMessage.value = errorText(error)
  } finally {
    busy.value = null
  }
}

async function removeAccount() {
  if (!deletePassword.value || busy.value) return
  busy.value = 'delete'
  resetMessages()
  try {
    await deleteAccount({ password: deletePassword.value })
    const registrationEnabled = session.state.value?.registration_enabled ?? false
    session.state.value = {
      authenticated: false,
      user: null,
      csrf_token: null,
      expires_at: null,
      registration_enabled: registrationEnabled,
    }
    deletePassword.value = ''
    emit('deleted')
    closeDialog(true)
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    busy.value = null
  }
}

function closeDialog(force = false) {
  if (busy.value && !force) return
  currentPassword.value = ''
  newPassword.value = ''
  deletePassword.value = ''
  emit('close')
  void nextTick(() => restoreFocusTo?.focus())
}

function focusableElements(): HTMLElement[] {
  if (!dialog.value) return []
  return Array.from(dialog.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ))
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDialog()
    return
  }
  if (event.key !== 'Tab') return
  const controls = focusableElements()
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    restoreFocusTo = document.activeElement instanceof HTMLElement ? document.activeElement : null
    username.value = session.state.value?.user?.username ?? ''
    replyEmailEnabled.value = session.state.value?.user?.reply_email_enabled ?? false
    resetMessages()
    await nextTick()
    usernameInput.value?.focus()
  },
  { immediate: true },
)

onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div v-if="open" class="account-dialog-backdrop" @mousedown.self="closeDialog()">
      <section
        ref="dialog"
        class="account-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="账户设置"
      >
        <header class="account-dialog__header">
          <div>
            <p>{{ session.state.value?.user?.email }}</p>
            <h2>账户设置</h2>
          </div>
          <button type="button" aria-label="关闭账户设置" title="关闭" @click="closeDialog()">
            <X :size="19" aria-hidden="true" />
          </button>
        </header>

        <p v-if="errorMessage" class="account-dialog__message account-dialog__message--error" role="alert">{{ errorMessage }}</p>
        <p v-else-if="successMessage" class="account-dialog__message" role="status">{{ successMessage }}</p>

        <form data-account-section="profile" @submit.prevent="saveProfile">
          <label for="account-username">用户名</label>
          <div class="account-dialog__row">
            <input id="account-username" ref="usernameInput" v-model="username" name="username" autocomplete="username">
            <button type="submit" :disabled="busy !== null || !username.trim()">保存用户名</button>
          </div>
        </form>

        <form data-account-section="password" @submit.prevent="savePassword">
          <strong>修改密码</strong>
          <label for="account-current-password">当前密码</label>
          <input id="account-current-password" v-model="currentPassword" name="current-password" type="password" autocomplete="current-password">
          <label for="account-new-password">新密码</label>
          <input id="account-new-password" v-model="newPassword" name="new-password" type="password" autocomplete="new-password">
          <button type="submit" :disabled="busy !== null || !currentPassword || !newPassword">更新密码</button>
        </form>

        <section class="account-dialog__preference" aria-labelledby="reply-email-label">
          <div>
            <strong id="reply-email-label">回复邮件提醒</strong>
            <span>有人回复评论时发送邮件</span>
          </div>
          <label class="account-toggle">
            <input
              v-model="replyEmailEnabled"
              name="reply-email-enabled"
              type="checkbox"
              :disabled="busy !== null"
              @change="savePreference"
            >
            <span aria-hidden="true" />
            <span class="visually-hidden">回复邮件提醒</span>
          </label>
        </section>

        <form class="account-dialog__danger" data-account-section="delete" @submit.prevent="removeAccount">
          <strong>注销账户</strong>
          <label for="delete-account-password">输入当前密码确认</label>
          <div class="account-dialog__row">
            <input id="delete-account-password" v-model="deletePassword" name="delete-password" type="password" autocomplete="current-password">
            <button name="delete-account" type="submit" :disabled="busy !== null || !deletePassword">注销账户</button>
          </div>
        </form>
      </section>
  </div>
</template>

<style scoped>
.account-dialog-backdrop {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 1rem;
  overflow-y: auto;
  background: rgb(24 34 29 / 52%);
}

.account-dialog {
  width: min(100%, 34rem);
  max-height: calc(100svh - 2rem);
  overflow-y: auto;
  border: 1px solid var(--line);
  border-top: 0.2rem solid var(--red);
  background: var(--paper);
  box-shadow: 0 1.5rem 4rem rgb(24 34 29 / 22%);
}

.account-dialog__header,
.account-dialog form,
.account-dialog__preference,
.account-dialog__message {
  padding: 1rem 1.2rem;
  border-bottom: 1px solid var(--line);
}

.account-dialog__header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
}

.account-dialog__header p {
  margin: 0 0 0.2rem;
  color: var(--muted);
  font-size: 0.7rem;
}

.account-dialog__header h2 {
  font-size: 1.25rem;
}

.account-dialog__header button {
  display: grid;
  width: 2.3rem;
  height: 2.3rem;
  place-items: center;
  padding: 0;
  border: 1px solid var(--line);
  background: transparent;
}

.account-dialog form {
  display: grid;
  gap: 0.55rem;
}

.account-dialog label,
.account-dialog__preference span {
  color: var(--muted);
  font-size: 0.72rem;
}

.account-dialog input:not([type='checkbox']) {
  min-width: 0;
  min-height: 2.5rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid #b9c6be;
  border-radius: 0;
  background: white;
  color: var(--ink);
  font: inherit;
}

.account-dialog button {
  min-height: 2.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--green);
  border-radius: 0;
  background: transparent;
  color: var(--green);
  font-size: 0.75rem;
  font-weight: 800;
}

.account-dialog button:disabled {
  opacity: 0.5;
}

.account-dialog__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.55rem;
}

.account-dialog__preference {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.account-dialog__preference > div {
  display: grid;
  gap: 0.25rem;
}

.account-toggle {
  position: relative;
  display: inline-flex;
  flex: none;
}

.account-toggle input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.account-toggle > span:not(.visually-hidden) {
  position: relative;
  display: block;
  width: 2.5rem;
  height: 1.35rem;
  border: 1px solid #9eb0a6;
  background: var(--line);
}

.account-toggle > span:not(.visually-hidden)::after {
  position: absolute;
  inset: 0.18rem auto auto 0.18rem;
  width: 0.85rem;
  height: 0.85rem;
  background: white;
  content: '';
  transition: transform 120ms ease;
}

.account-toggle input:checked + span {
  background: var(--green);
}

.account-toggle input:checked + span::after {
  transform: translateX(1.12rem);
}

.account-toggle input:focus-visible + span {
  outline: 0.1875rem solid var(--red);
  outline-offset: 0.1875rem;
}

.account-dialog__message {
  margin: 0;
  color: var(--green);
  font-size: 0.75rem;
}

.account-dialog__message--error,
.account-dialog__danger strong,
.account-dialog__danger button {
  color: var(--red);
}

.account-dialog__danger button {
  border-color: var(--red);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 32rem) {
  .account-dialog__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
