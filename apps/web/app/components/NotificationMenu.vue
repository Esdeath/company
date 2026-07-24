<script setup lang="ts">
import { Bell, CheckCheck, RefreshCw } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/community'
import type { Notification } from '../types/community'

const emit = defineEmits<{
  'unread-count-changed': [count: number]
}>()

const open = ref(false)
const loading = ref(true)
const busy = ref(false)
const items = ref<Notification[]>([])
const unreadCount = ref(0)
const errorMessage = ref('')
const trigger = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)

const triggerLabel = computed(() =>
  unreadCount.value ? `通知，${unreadCount.value} 条未读` : '通知',
)

function errorText(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '通知暂时无法读取'
}

function publishUnreadCount(count: number) {
  unreadCount.value = count
  emit('unread-count-changed', count)
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const page = await listNotifications()
    items.value = page.items
    publishUnreadCount(page.unread_count)
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    loading.value = false
  }
}

async function openMenu() {
  open.value = true
  await nextTick()
  menu.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
}

async function closeMenu(restoreFocus = true) {
  if (!open.value) return
  open.value = false
  if (restoreFocus) {
    await nextTick()
    trigger.value?.focus()
  }
}

function toggleMenu() {
  if (open.value) void closeMenu()
  else void openMenu()
}

async function markOne(item: Notification) {
  if (item.read_at) return
  try {
    const updated = await markNotificationRead(item.id)
    items.value = items.value.map((existing) => (existing.id === updated.id ? updated : existing))
    publishUnreadCount(Math.max(0, unreadCount.value - 1))
  } catch (error) {
    errorMessage.value = errorText(error)
  }
}

async function followNotification(item: Notification) {
  await markOne(item)
  window.location.assign(notificationHref(item))
}

async function markAll() {
  if (!unreadCount.value || busy.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    await markAllNotificationsRead()
    const readAt = new Date().toISOString()
    items.value = items.value.map((item) => ({ ...item, read_at: item.read_at ?? readAt }))
    publishUnreadCount(0)
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    busy.value = false
  }
}

function notificationHref(item: Notification): string {
  const search = new URLSearchParams({
    company: item.company_id,
    document: item.document_id,
    comment: item.comment_id,
  })
  return `/?${search.toString()}`
}

function handleKeydown(event: KeyboardEvent) {
  if (open.value && event.key === 'Escape') {
    event.preventDefault()
    void closeMenu()
  }
}

function handlePointerDown(event: PointerEvent) {
  if (!open.value) return
  const target = event.target
  if (target instanceof Node && !menu.value?.contains(target) && !trigger.value?.contains(target)) {
    void closeMenu(false)
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  document.addEventListener('pointerdown', handlePointerDown)
  void load()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('pointerdown', handlePointerDown)
})
</script>

<template>
  <div class="notification-control">
    <button
      ref="trigger"
      class="site-icon-button"
      type="button"
      :aria-label="triggerLabel"
      aria-haspopup="menu"
      :aria-expanded="open"
      title="通知"
      @click="toggleMenu"
    >
      <Bell :size="18" aria-hidden="true" />
      <span v-if="unreadCount" class="notification-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
    </button>

    <section v-if="open" ref="menu" class="notification-menu" role="menu" aria-label="通知">
      <header class="notification-menu__header">
        <strong>通知</strong>
        <span>{{ unreadCount }} 条未读</span>
        <button
          name="refresh-notifications"
          type="button"
          role="menuitem"
          aria-label="刷新通知"
          title="刷新通知"
          @click="load"
        >
          <RefreshCw :size="16" aria-hidden="true" />
        </button>
      </header>

      <p v-if="loading" class="notification-menu__state" role="status">正在读取通知</p>
      <div v-else-if="errorMessage" class="notification-menu__state" role="alert">
        <p>{{ errorMessage }}</p>
        <button name="retry-notifications" type="button" role="menuitem" @click="load">重新载入</button>
      </div>
      <p v-else-if="items.length === 0" class="notification-menu__state">还没有通知</p>
      <ul v-else class="notification-list">
        <li v-for="item in items" :key="item.id" :class="{ 'notification-list__item--unread': !item.read_at }">
          <a
            :href="notificationHref(item)"
            :data-notification-id="item.id"
            role="menuitem"
            @click.prevent="followNotification(item)"
          >
            <strong>{{ item.message }}</strong>
            <span>{{ item.excerpt }}</span>
          </a>
        </li>
      </ul>

      <button
        v-if="items.length"
        class="notification-menu__all"
        name="mark-all-notifications-read"
        type="button"
        role="menuitem"
        :disabled="!unreadCount || busy"
        @click="markAll"
      >
        <CheckCheck :size="16" aria-hidden="true" />
        全部标为已读
      </button>
    </section>
  </div>
</template>

<style scoped>
.notification-control {
  position: relative;
}

.site-icon-button {
  position: relative;
  display: grid;
  width: 2.35rem;
  height: 2.35rem;
  place-items: center;
  padding: 0;
  border: 1px solid #b9c6be;
  border-radius: 0.2rem;
  background: var(--paper);
  color: var(--green);
}

.notification-badge {
  position: absolute;
  inset: -0.28rem -0.35rem auto auto;
  min-width: 1.1rem;
  height: 1.1rem;
  padding-inline: 0.25rem;
  border: 2px solid var(--page);
  border-radius: 1rem;
  background: var(--red);
  color: white;
  font-family: var(--font-utility);
  font-size: 0.58rem;
  font-weight: 800;
  line-height: 0.85rem;
  text-align: center;
}

.notification-menu {
  position: absolute;
  z-index: 25;
  inset: calc(100% + 0.65rem) 0 auto auto;
  width: min(22rem, calc(100vw - 2rem));
  border: 1px solid var(--line);
  background: var(--paper);
  box-shadow: 0 1rem 2.5rem rgb(24 34 29 / 16%);
}

.notification-menu__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.65rem;
  padding: 0.8rem;
  border-bottom: 1px solid var(--line);
}

.notification-menu__header span,
.notification-menu__state,
.notification-list span {
  color: var(--muted);
  font-size: 0.72rem;
}

.notification-menu button {
  border: 0;
  background: transparent;
}

.notification-menu__header button {
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  padding: 0;
}

.notification-menu__state {
  margin: 0;
  padding: 1.25rem 0.8rem;
}

.notification-menu__state p {
  margin: 0 0 0.65rem;
}

.notification-menu__state button {
  padding: 0;
  color: var(--green);
  font-weight: 800;
}

.notification-list {
  max-height: min(24rem, 62svh);
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.notification-list li {
  border-bottom: 1px solid var(--line);
}

.notification-list a {
  position: relative;
  display: grid;
  gap: 0.3rem;
  padding: 0.85rem 0.8rem 0.85rem 1rem;
  text-decoration: none;
}

.notification-list__item--unread a::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 0.2rem;
  background: var(--red);
  content: '';
}

.notification-list strong {
  font-size: 0.78rem;
  line-height: 1.5;
}

.notification-list span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notification-menu__all {
  display: flex;
  width: 100%;
  min-height: 2.7rem;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.65rem;
  color: var(--green);
  font-size: 0.72rem;
  font-weight: 800;
}
</style>
