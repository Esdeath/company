<script setup lang="ts">
import { LogIn, LogOut, Settings, UserRound } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { unsubscribeEmail } from '../api/community'
import { useUserSession } from '../composables/useUserSession'
import type { UserAuthState } from '../types/community'
import AccountDialog from './AccountDialog.vue'
import AuthDialog from './AuthDialog.vue'
import NotificationMenu from './NotificationMenu.vue'

const props = withDefaults(
  defineProps<{
    verificationToken?: string | null
    resetToken?: string | null
    unsubscribeToken?: string | null
  }>(),
  {
    verificationToken: null,
    resetToken: null,
    unsubscribeToken: null,
  },
)

const session = useUserSession()
const authOpen = ref(Boolean(props.verificationToken || props.resetToken))
const accountOpen = ref(false)
const menuOpen = ref(false)
const actionError = ref('')
const actionStatus = ref('')
const accountTrigger = ref<HTMLButtonElement | null>(null)
const loginTrigger = ref<HTMLButtonElement | null>(null)
const accountMenu = ref<HTMLElement | null>(null)

function openLogin() {
  authOpen.value = true
}

async function focusSessionTrigger() {
  await nextTick()
  const trigger = session.authenticated.value ? accountTrigger.value : loginTrigger.value
  if (trigger?.isConnected) trigger.focus()
}

async function finishAuthentication(state: UserAuthState) {
  session.replaceState(state)
  authOpen.value = false
  await focusSessionTrigger()
}

async function openAccountMenu() {
  menuOpen.value = true
  await nextTick()
  accountMenu.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
}

async function closeAccountMenu(restoreFocus = true) {
  if (!menuOpen.value) return
  menuOpen.value = false
  if (restoreFocus) await focusSessionTrigger()
}

function toggleAccountMenu() {
  if (menuOpen.value) void closeAccountMenu()
  else void openAccountMenu()
}

function openAccountSettings() {
  void closeAccountMenu(false)
  accountOpen.value = true
}

async function closeAccountSettings() {
  accountOpen.value = false
  await focusSessionTrigger()
}

async function finishDeletion() {
  accountOpen.value = false
  await focusSessionTrigger()
}

async function logout() {
  actionError.value = ''
  try {
    await session.logout()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '退出登录失败'
  } finally {
    await closeAccountMenu()
  }
}

async function consumeUnsubscribeToken() {
  if (!props.unsubscribeToken) return
  actionError.value = ''
  actionStatus.value = ''
  try {
    actionStatus.value = (await unsubscribeEmail(props.unsubscribeToken)).message
  } catch {
    actionError.value = '无法更新邮件偏好，请稍后重试'
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (menuOpen.value && event.key === 'Escape') {
    event.preventDefault()
    void closeAccountMenu()
  }
}

function handlePointerDown(event: PointerEvent) {
  if (!menuOpen.value) return
  const target = event.target
  if (
    target instanceof Node &&
    !accountMenu.value?.contains(target) &&
    !accountTrigger.value?.contains(target)
  ) {
    void closeAccountMenu(false)
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('pointerdown', handlePointerDown)
  void consumeUnsubscribeToken()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('pointerdown', handlePointerDown)
})

defineExpose({ openLogin })
</script>

<template>
  <div class="site-user-controls">
    <template v-if="session.authenticated.value && session.user.value">
      <NotificationMenu />
      <div class="account-control">
        <button
          ref="accountTrigger"
          class="site-icon-button"
          type="button"
          :aria-label="`账户：${session.user.value.username}`"
          aria-haspopup="menu"
          :aria-expanded="menuOpen"
          :title="session.user.value.username"
          @click="toggleAccountMenu"
        >
          <UserRound :size="18" aria-hidden="true" />
        </button>
        <div v-if="menuOpen" ref="accountMenu" class="account-menu" role="menu" aria-label="账户">
          <p>{{ session.user.value.username }}</p>
          <button name="open-account-settings" type="button" role="menuitem" @click="openAccountSettings">
            <Settings :size="16" aria-hidden="true" />
            账户设置
          </button>
          <button name="logout-user" type="button" role="menuitem" @click="logout">
            <LogOut :size="16" aria-hidden="true" />
            退出登录
          </button>
        </div>
      </div>
    </template>
    <button v-else ref="loginTrigger" class="site-login-button" type="button" aria-label="登录" @click="openLogin">
      <LogIn :size="17" aria-hidden="true" />
      <span>登录</span>
    </button>
    <p v-if="actionStatus" class="site-user-controls__message" role="status">{{ actionStatus }}</p>
    <p v-if="actionError" class="site-user-controls__error" role="alert">{{ actionError }}</p>

    <AuthDialog
      :open="authOpen"
      :registration-enabled="session.state.value?.registration_enabled"
      :verification-token="props.verificationToken"
      :reset-token="props.resetToken"
      @authenticated="finishAuthentication"
      @close="authOpen = false"
    />
    <AccountDialog :open="accountOpen" @close="closeAccountSettings" @deleted="finishDeletion" />
  </div>
</template>

<style scoped>
.site-user-controls {
  position: relative;
  display: flex;
  flex: none;
  align-items: center;
  gap: 0.45rem;
}

.site-icon-button,
.site-login-button {
  border: 1px solid #b9c6be;
  border-radius: 0.2rem;
  background: var(--paper);
  color: var(--green);
}

.site-icon-button {
  position: relative;
  display: grid;
  width: 2.35rem;
  height: 2.35rem;
  place-items: center;
  padding: 0;
}

.site-login-button {
  display: flex;
  min-height: 2.35rem;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 0.65rem;
  font-size: 0.72rem;
  font-weight: 800;
}

.account-control {
  position: relative;
}

.account-menu {
  position: absolute;
  z-index: 25;
  inset: calc(100% + 0.65rem) 0 auto auto;
  width: 11rem;
  border: 1px solid var(--line);
  background: var(--paper);
  box-shadow: 0 1rem 2.5rem rgb(24 34 29 / 16%);
}

.account-menu p {
  margin: 0;
  padding: 0.75rem 0.8rem;
  overflow: hidden;
  border-bottom: 1px solid var(--line);
  font-family: var(--font-display);
  font-size: 0.82rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-menu button {
  display: flex;
  width: 100%;
  min-height: 2.55rem;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.8rem;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: transparent;
  font-size: 0.72rem;
  text-align: left;
}

.account-menu button:last-child {
  border-bottom: 0;
}

.site-user-controls__message,
.site-user-controls__error {
  position: absolute;
  inset: calc(100% + 0.5rem) 0 auto auto;
  width: max-content;
  max-width: min(18rem, calc(100vw - 2rem));
  margin: 0;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--red);
  background: var(--paper);
  color: var(--red);
  font-size: 0.7rem;
}

.site-user-controls__message {
  border-color: var(--green);
  color: var(--green);
}

.site-user-controls__error {
  border-color: var(--red);
  color: var(--red);
}
</style>
