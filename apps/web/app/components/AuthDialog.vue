<script setup lang="ts">
import { ArrowLeft, X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useUserSession } from '../composables/useUserSession'
import type { UserAuthState } from '../types/community'

type DialogMode = 'login' | 'register' | 'verification-sent' | 'reset-request' | 'reset-confirm'

const props = withDefaults(
  defineProps<{
    open: boolean
    registrationEnabled?: boolean
    verificationToken?: string | null
    resetToken?: string | null
  }>(),
  {
    registrationEnabled: undefined,
    verificationToken: null,
    resetToken: null,
  },
)

const emit = defineEmits<{
  authenticated: [state: UserAuthState]
  close: []
}>()

const session = useUserSession()
const mode = ref<DialogMode>('login')
const busy = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const email = ref('')
const username = ref('')
const password = ref('')
const confirmation = ref('')
const fieldErrors = ref<Record<string, string>>({})
let restoreFocusTo: HTMLElement | null = null
let submittedVerificationToken: string | null = null

const registrationIsEnabled = computed(
  () => props.registrationEnabled ?? session.state.value?.registration_enabled ?? true,
)

function resetMessages() {
  errorMessage.value = ''
  successMessage.value = ''
  fieldErrors.value = {}
}

function setMode(nextMode: DialogMode) {
  mode.value = nextMode
  resetMessages()
  void focusFirstControl()
}

async function focusFirstControl() {
  await nextTick()
  const name = mode.value === 'register' ? 'email' : mode.value === 'reset-confirm' ? 'password' : 'email'
  document.querySelector<HTMLInputElement>(`[data-auth-dialog] input[name="${name}"]`)?.focus()
}

function errorText(error: unknown): string {
  return error instanceof Error && error.message.trim() ? error.message : '操作暂时无法完成，请稍后重试'
}

function finishAuthentication(state: UserAuthState) {
  emit('authenticated', state)
  closeDialog(true)
}

function closeDialog(force = false) {
  if (busy.value && !force) return
  emit('close')
  void nextTick(() => restoreFocusTo?.focus())
}

function onKeydown(event: KeyboardEvent) {
  if (props.open && event.key === 'Escape') {
    event.preventDefault()
    closeDialog()
  }
}

async function submitVerification(token: string) {
  busy.value = true
  resetMessages()
  try {
    finishAuthentication(await session.verifyEmail({ token }))
  } catch (error) {
    errorMessage.value = errorText(error)
    mode.value = 'login'
  } finally {
    busy.value = false
  }
}

async function submit() {
  if (busy.value) return
  busy.value = true
  resetMessages()

  try {
    if (mode.value === 'login') {
      finishAuthentication(await session.login({ email: email.value, password: password.value }))
      return
    }

    if (mode.value === 'register') {
      if (!registrationIsEnabled.value) {
        errorMessage.value = '注册暂未开放'
        return
      }
      const response = await session.register({
        email: email.value,
        username: username.value,
        password: password.value,
      })
      successMessage.value = response.message
      mode.value = 'verification-sent'
      return
    }

    if (mode.value === 'reset-request') {
      const response = await session.requestReset({ email: email.value })
      successMessage.value = response.message
      return
    }

    if (mode.value === 'reset-confirm') {
      if (password.value !== confirmation.value) {
        fieldErrors.value = { confirmation: '两次输入的密码不一致' }
        return
      }
      if (!props.resetToken) {
        errorMessage.value = '链接无效或已过期'
        return
      }
      finishAuthentication(
        await session.confirmReset({ token: props.resetToken, password: password.value }),
      )
    }
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    busy.value = false
  }
}

function prepareOpen() {
  restoreFocusTo = document.activeElement instanceof HTMLElement ? document.activeElement : null
  resetMessages()
  mode.value = props.resetToken ? 'reset-confirm' : 'login'
  void focusFirstControl()

  if (props.verificationToken && props.verificationToken !== submittedVerificationToken) {
    submittedVerificationToken = props.verificationToken
    void submitVerification(props.verificationToken)
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) prepareOpen()
  },
  { immediate: true },
)

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div v-if="open" class="auth-layer" data-auth-dialog>
    <button class="auth-backdrop" type="button" aria-label="关闭账户对话框" @click="() => closeDialog()" />
    <section class="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-dialog-title">
      <header class="auth-dialog__header">
        <div>
          <p class="auth-dialog__eyebrow">读者账户</p>
          <h2 id="auth-dialog-title">
            {{
              mode === 'register'
                ? '注册账户'
                : mode === 'verification-sent'
                  ? '确认邮箱'
                  : mode === 'reset-request' || mode === 'reset-confirm'
                    ? '重设密码'
                    : '登录'
            }}
          </h2>
        </div>
        <button
          class="auth-icon-button"
          type="button"
          name="close-auth-dialog"
          aria-label="关闭账户对话框"
          title="关闭"
          :disabled="busy"
          @click="() => closeDialog()"
        >
          <X :size="18" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </header>

      <p v-if="errorMessage" class="auth-dialog__alert" role="alert">{{ errorMessage }}</p>

      <div v-if="mode === 'verification-sent'" class="auth-dialog__message" role="status">
        <p>{{ successMessage || '请检查邮箱以完成注册' }}</p>
        <button class="auth-text-button" type="button" name="back-to-login" @click="setMode('login')">
          返回登录
        </button>
      </div>

      <form v-else class="auth-form" @submit.prevent="submit">
        <template v-if="mode !== 'reset-confirm'">
          <label for="auth-email">邮箱</label>
          <input
            id="auth-email"
            v-model="email"
            name="email"
            type="email"
            autocomplete="email"
            required
            :disabled="busy"
          >
        </template>

        <template v-if="mode === 'register'">
          <label for="auth-username">用户名</label>
          <input
            id="auth-username"
            v-model="username"
            name="username"
            type="text"
            autocomplete="username"
            minlength="3"
            maxlength="30"
            required
            :disabled="busy"
          >
        </template>

        <template v-if="mode !== 'reset-request'">
          <label for="auth-password">密码</label>
          <input
            id="auth-password"
            v-model="password"
            name="password"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            minlength="8"
            required
            :disabled="busy"
          >
        </template>

        <template v-if="mode === 'reset-confirm'">
          <label for="auth-confirm-password">确认新密码</label>
          <input
            id="auth-confirm-password"
            v-model="confirmation"
            name="confirm-password"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required
            :disabled="busy"
            :aria-describedby="fieldErrors.confirmation ? 'auth-confirmation-error' : undefined"
          >
          <p v-if="fieldErrors.confirmation" id="auth-confirmation-error" class="auth-field-error">
            {{ fieldErrors.confirmation }}
          </p>
        </template>

        <p v-if="mode === 'login' && !registrationIsEnabled" class="auth-dialog__note">
          注册暂未开放
        </p>
        <p v-if="mode === 'reset-request' && successMessage" class="auth-dialog__message" role="status">
          {{ successMessage }}
        </p>

        <button class="auth-submit" type="submit" name="submit-auth" :disabled="busy">
          {{
            busy
              ? '处理中'
              : mode === 'register'
                ? '发送验证邮件'
                : mode === 'reset-request'
                  ? '发送重置邮件'
                  : mode === 'reset-confirm'
                    ? '更新密码并登录'
                    : '登录'
          }}
        </button>
      </form>

      <footer v-if="mode !== 'verification-sent'" class="auth-dialog__footer">
        <button
          v-if="mode === 'login' && registrationIsEnabled"
          class="auth-text-button"
          type="button"
          name="show-register"
          :disabled="busy"
          @click="setMode('register')"
        >
          注册
        </button>
        <button
          v-if="mode === 'login'"
          class="auth-text-button"
          type="button"
          name="show-password-reset"
          :disabled="busy"
          @click="setMode('reset-request')"
        >
          忘记密码
        </button>
        <button
          v-if="mode !== 'login'"
          class="auth-icon-button auth-icon-button--back"
          type="button"
          name="back-to-login"
          aria-label="返回登录"
          title="返回登录"
          :disabled="busy"
          @click="setMode('login')"
        >
          <ArrowLeft :size="17" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.auth-layer {
  position: fixed;
  z-index: 60;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 1rem;
}

.auth-backdrop {
  position: absolute;
  inset: 0;
  border: 0;
  background: rgb(24 34 29 / 52%);
}

.auth-dialog {
  position: relative;
  width: min(100%, 25rem);
  padding: 1.35rem;
  border: 1px solid var(--line, #dfe6e1);
  border-radius: 0.35rem;
  background: var(--paper, #fbfcfa);
  box-shadow: 0 1.25rem 3rem rgb(24 34 29 / 22%);
}

.auth-dialog__header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--line, #dfe6e1);
}

.auth-dialog__eyebrow,
.auth-dialog__note,
.auth-field-error {
  margin: 0;
  color: var(--muted, #68756e);
  font-family: var(--font-utility, monospace);
  font-size: 0.68rem;
}

.auth-dialog__eyebrow {
  color: var(--green, #285541);
  font-weight: 800;
  letter-spacing: 0.08em;
}

.auth-dialog h2 {
  margin: 0.3rem 0 0;
  font-family: var(--font-display, Georgia, serif);
  font-size: 1.3rem;
}

.auth-icon-button {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  flex: 0 0 auto;
  place-items: center;
  padding: 0;
  border: 1px solid var(--line, #dfe6e1);
  border-radius: 50%;
  background: transparent;
}

.auth-icon-button:hover:not(:disabled) {
  border-color: var(--green, #285541);
  color: var(--green, #285541);
}

.auth-form {
  display: grid;
  gap: 0.5rem;
  padding-top: 1rem;
}

.auth-form label {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  font-weight: 700;
}

.auth-form input {
  width: 100%;
  min-height: 2.6rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid #b9c6be;
  border-radius: 0.2rem;
  background: #fff;
  color: var(--ink, #18221d);
  font: inherit;
}

.auth-form input:focus {
  border-color: var(--green, #285541);
  outline: 0.125rem solid rgb(40 85 65 / 18%);
  outline-offset: 0;
}

.auth-submit {
  min-height: 2.7rem;
  margin-top: 0.8rem;
  border: 1px solid var(--green, #285541);
  border-radius: 0.2rem;
  background: var(--green, #285541);
  color: #fff;
  font-weight: 700;
}

.auth-submit:disabled,
.auth-icon-button:disabled,
.auth-text-button:disabled {
  cursor: wait;
  opacity: 0.58;
}

.auth-dialog__alert,
.auth-dialog__message {
  margin: 1rem 0 0;
  padding: 0.7rem 0.8rem;
  border-left: 0.2rem solid var(--red, #b9503d);
  background: #f9efec;
  font-size: 0.82rem;
  line-height: 1.55;
}

.auth-dialog__message {
  border-color: var(--green, #285541);
  background: var(--green-soft, #eaf2ed);
}

.auth-dialog__message p {
  margin: 0;
}

.auth-field-error {
  color: var(--red, #b9503d);
}

.auth-dialog__footer {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  min-height: 3.5rem;
  margin-top: 0.8rem;
}

.auth-icon-button--back {
  margin-left: auto;
}

.auth-text-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--green, #285541);
  font-size: 0.78rem;
  text-decoration: underline;
  text-underline-offset: 0.18rem;
}
</style>
