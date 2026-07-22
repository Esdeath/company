<script setup lang="ts">
import { ref } from 'vue'

import type { LoginInput } from '../types'

defineProps<{
  busy: boolean
  error: string
}>()

const emit = defineEmits<{
  login: [input: LoginInput]
}>()

const username = ref('')
const password = ref('')

function submit() {
  if (!username.value.trim() || !password.value) return
  emit('login', { username: username.value.trim(), password: password.value })
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <p class="eyebrow">受保护的资料入口</p>
      <h1 id="login-title">管理员登录</h1>
      <p class="login-panel__intro">登录后可新建公司、上传资料和整理公开内容。</p>

      <form class="login-form" aria-label="管理员登录" @submit.prevent="submit">
        <label>
          用户名
          <input
            v-model="username"
            name="username"
            type="text"
            autocomplete="username"
            required
            :disabled="busy"
          />
        </label>
        <label>
          密码
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
            :disabled="busy"
          />
        </label>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button class="primary-action" type="submit" :disabled="busy">
          {{ busy ? '正在验证…' : '进入管理端' }}
        </button>
      </form>

      <a class="login-return" href="/"><span aria-hidden="true">←</span> 返回公开资料库</a>
    </section>
  </main>
</template>
