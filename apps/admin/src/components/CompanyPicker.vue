<script setup lang="ts">
import { ref } from 'vue'

import type { Company, CompanyInput } from '../types'

defineProps<{
  companies: Company[]
  selectedId: string
  busy?: boolean
}>()

const emit = defineEmits<{
  select: [companyId: string]
  create: [input: CompanyInput]
}>()

const showingForm = ref(false)
const name = ref('')
const ticker = ref('')
const market = ref('')

function submitCompany() {
  const trimmedName = name.value.trim()
  if (!trimmedName) return

  emit('create', {
    name: trimmedName,
    ticker: ticker.value.trim() || null,
    market: market.value.trim() || null,
  })
  name.value = ''
  ticker.value = ''
  market.value = ''
  showingForm.value = false
}
</script>

<template>
  <aside class="company-folio" aria-labelledby="company-folio-title">
    <div class="section-label">
      <p>公司卷宗</p>
      <h2 id="company-folio-title">选择归档位置</h2>
    </div>

    <label class="mobile-company-select" for="company-select">
      <span>当前公司</span>
      <select
        id="company-select"
        :disabled="busy || companies.length === 0"
        :value="selectedId"
        @change="emit('select', ($event.target as HTMLSelectElement).value)"
      >
        <option v-if="companies.length === 0" value="">暂无公司</option>
        <option v-for="company in companies" :key="company.id" :value="company.id">
          {{ company.name }}
        </option>
      </select>
    </label>

    <nav class="folio-tabs" aria-label="公司列表">
      <button
        v-for="company in companies"
        :key="company.id"
        class="folio-tab"
        :class="{ 'folio-tab--active': company.id === selectedId }"
        type="button"
        :aria-current="company.id === selectedId ? 'page' : undefined"
        :disabled="busy"
        @click="emit('select', company.id)"
      >
        <span>{{ company.name }}</span>
        <small v-if="company.ticker || company.market">
          {{ [company.ticker, company.market].filter(Boolean).join(' · ') }}
        </small>
        <small v-else>未填写证券信息</small>
      </button>
    </nav>

    <button
      class="text-action company-form-toggle"
      name="show-company-form"
      type="button"
      :aria-expanded="showingForm"
      aria-controls="new-company-form"
      @click="showingForm = !showingForm"
    >
      {{ showingForm ? '收起新建公司' : '＋ 新建公司' }}
    </button>

    <form
      v-if="showingForm"
      id="new-company-form"
      class="company-form"
      aria-label="新建公司"
      @submit.prevent="submitCompany"
    >
      <label for="company-name">公司名称</label>
      <input id="company-name" v-model="name" name="company-name" required autocomplete="organization" />

      <div class="paired-fields">
        <label for="ticker">
          <span>股票代码 <small>选填</small></span>
          <input id="ticker" v-model="ticker" name="ticker" autocomplete="off" />
        </label>
        <label for="market">
          <span>市场 <small>选填</small></span>
          <input id="market" v-model="market" name="market" autocomplete="off" />
        </label>
      </div>

      <button class="primary-action" type="submit" :disabled="busy || !name.trim()">保存公司</button>
    </form>
  </aside>
</template>
