<script setup lang="ts">
import { ref, watch } from 'vue'

import type { Company, CompanyInput } from '../types'

const props = defineProps<{
  companies: Company[]
  selectedId: string
  busy?: boolean
  creating?: boolean
  createSuccessKey: number
}>()

const emit = defineEmits<{
  select: [companyId: string]
  create: [input: CompanyInput]
  reorder: [companyIds: string[]]
}>()

const showingForm = ref(false)
const name = ref('')
const ticker = ref('')
const market = ref('')
const statusMessage = ref('')

function move(companyId: string, offset: -1 | 1) {
  if (props.busy) return
  const companyIds = props.companies.map((company) => company.id)
  const currentIndex = companyIds.indexOf(companyId)
  const nextIndex = currentIndex + offset
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= companyIds.length) return

  const currentCompanyId = companyIds[currentIndex]!
  companyIds[currentIndex] = companyIds[nextIndex]!
  companyIds[nextIndex] = currentCompanyId
  statusMessage.value = `已移到第 ${nextIndex + 1} 项，正在保存`
  emit('reorder', companyIds)
}

function submitCompany() {
  const trimmedName = name.value.trim()
  if (!trimmedName || props.creating) return

  emit('create', {
    name: trimmedName,
    ticker: ticker.value.trim() || null,
    market: market.value.trim() || null,
  })
}

watch(
  () => props.createSuccessKey,
  () => {
    name.value = ''
    ticker.value = ''
    market.value = ''
    showingForm.value = false
  },
)
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
      <div v-for="(company, index) in companies" :key="company.id" class="folio-tab-row">
        <button
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
        <span class="company-order-actions" role="group" :aria-label="`调整 ${company.name} 的顺序`">
          <button
            class="company-order-button"
            type="button"
            title="上移"
            :aria-label="`上移 ${company.name}`"
            :disabled="busy || index === 0"
            @click="move(company.id, -1)"
          >
            ↑
          </button>
          <button
            class="company-order-button"
            type="button"
            title="下移"
            :aria-label="`下移 ${company.name}`"
            :disabled="busy || index === companies.length - 1"
            @click="move(company.id, 1)"
          >
            ↓
          </button>
        </span>
      </div>
    </nav>

    <span class="company-order-status visually-hidden" role="status" aria-live="polite">
      {{ statusMessage }}
    </span>

    <button
      class="text-action company-form-toggle"
      name="show-company-form"
      type="button"
      :aria-expanded="showingForm"
      aria-controls="new-company-form"
      :disabled="creating"
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
      <input
        id="company-name"
        v-model="name"
        name="company-name"
        required
        autocomplete="organization"
        :disabled="creating"
      />

      <div class="paired-fields">
        <label for="ticker">
          <span>股票代码 <small>选填</small></span>
          <input id="ticker" v-model="ticker" name="ticker" autocomplete="off" :disabled="creating" />
        </label>
        <label for="market">
          <span>市场 <small>选填</small></span>
          <input id="market" v-model="market" name="market" autocomplete="off" :disabled="creating" />
        </label>
      </div>

      <button class="primary-action" type="submit" :disabled="busy || creating || !name.trim()">
        {{ creating ? '正在保存…' : '保存公司' }}
      </button>
    </form>
  </aside>
</template>
