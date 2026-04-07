<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Zap, X, AlertCircle } from 'lucide-vue-next'
import { api } from '@/lib/api'
import { formatNumber as formatAmount } from '@/lib/utils/formatters'

interface AutoMatch {
  id: string
  transaction_ids: string[]
  transaction_date?: string
  transaction_description?: string
  total_transaction_amount: number
  account_subject: string
  tax_division: string
  no_document_reason: string
  auto_rule_key: string
  fiscal_period: string
  matched_at: string
}

// --- STATE ---
const matches = ref<AutoMatch[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const filterFiscalPeriod = ref('')
const filterRule = ref('')
const revokingId = ref<string | null>(null)

// --- FETCH ---
const fetchMatches = async () => {
  isLoading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ match_type: 'auto_expense' })
    if (filterFiscalPeriod.value) params.append('fiscal_period', filterFiscalPeriod.value)
    matches.value = await api.get<AutoMatch[]>(`/matches?${params.toString()}`)
  } catch (e: any) {
    error.value = e.message
  } finally {
    isLoading.value = false
  }
}

onMounted(fetchMatches)

// --- COMPUTED ---
const ruleOptions = computed(() => {
  const keys = [...new Set(matches.value.map(m => m.no_document_reason).filter(Boolean))]
  return keys.sort()
})

const filtered = computed(() => {
  return matches.value.filter(m => {
    if (filterRule.value && m.no_document_reason !== filterRule.value) return false
    return true
  })
})

// --- REVOKE ---
const handleRevoke = async (match: AutoMatch) => {
  if (!confirm('この自動消込を解除しますか？解除すると未消込データとして戻ります。')) return
  revokingId.value = match.id
  try {
    await api.delete(`/matches/${match.id}`)
    await fetchMatches()
  } catch (e: any) {
    alert(`解除に失敗しました: ${e.message}`)
  } finally {
    revokingId.value = null
  }
}

const formatDate = (iso: string) =>
  iso ? new Date(iso).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  }) : '—'
</script>

<template>
  <div class="space-y-6 h-full flex flex-col">
    <!-- Header -->
    <div class="shrink-0">
      <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">自動消込履歴</h1>
      <p class="text-sm text-gray-500 mt-2">振込手数料・利息・ATM出入金など、自動で消込処理されたデータの一覧です。</p>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 shrink-0">
      <div>
        <label class="block text-xs font-semibold text-gray-600 mb-1">会計期間</label>
        <input
          v-model="filterFiscalPeriod"
          type="month"
          @change="fetchMatches"
          class="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
      </div>
      <div>
        <label class="block text-xs font-semibold text-gray-600 mb-1">種別</label>
        <select
          v-model="filterRule"
          class="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
          <option value="">すべて</option>
          <option v-for="r in ruleOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>
      <div class="flex items-end">
        <button
          @click="filterFiscalPeriod = ''; filterRule = ''; fetchMatches()"
          class="text-xs text-gray-500 hover:text-gray-700 px-3 py-2 border border-gray-200 rounded-lg transition-colors">
          クリア
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex-1 flex items-center justify-center text-gray-400 text-sm">
      読み込み中...
    </div>

    <!-- Error -->
    <div v-else-if="error"
      class="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 shrink-0">
      <AlertCircle class="h-4 w-4 shrink-0" />
      {{ error }}
    </div>

    <!-- Empty -->
    <div v-else-if="filtered.length === 0"
      class="flex-1 flex flex-col items-center justify-center bg-white rounded-xl border border-gray-200 shadow-sm py-20">
      <Zap class="h-16 w-16 text-gray-200 mb-4" />
      <p class="text-base font-medium text-gray-500">自動消込されたデータはありません</p>
    </div>

    <!-- Table -->
    <div v-else class="flex-1 overflow-y-auto min-h-0">
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 flex items-center gap-2 bg-gray-50 shrink-0">
          <Zap class="h-4 w-4 text-amber-500" />
          <span class="text-sm font-bold text-gray-700">{{ filtered.length }}件</span>
          <span class="text-xs text-gray-400">自動消込済み</span>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 border-b border-gray-200">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-[110px]">日付</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">摘要</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider w-[110px]">金額</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-[120px]">勘定科目</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-[90px]">税区分</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-[110px]">ルール</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-[140px]">処理日時</th>
              <th class="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-[70px]">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="m in filtered" :key="m.id" class="hover:bg-gray-50 transition-colors">
              <td class="px-4 py-3 text-gray-600 whitespace-nowrap text-xs">
                {{ m.transaction_date ?? '—' }}
              </td>
              <td class="px-4 py-3 text-gray-800 max-w-[200px] truncate" :title="m.transaction_description">
                {{ m.transaction_description ?? '—' }}
              </td>
              <td class="px-4 py-3 text-right font-medium text-gray-900 whitespace-nowrap">
                ¥{{ formatAmount(m.total_transaction_amount) }}
              </td>
              <td class="px-4 py-3 text-gray-700 text-xs whitespace-nowrap">
                {{ m.account_subject ?? '—' }}
              </td>
              <td class="px-4 py-3 text-xs">
                <span class="bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-medium">
                  {{ m.tax_division ?? '—' }}
                </span>
              </td>
              <td class="px-4 py-3 text-xs">
                <span class="inline-flex items-center gap-1 bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                  <Zap class="h-3 w-3" />
                  {{ m.no_document_reason }}
                </span>
              </td>
              <td class="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                {{ formatDate(m.matched_at) }}
              </td>
              <td class="px-4 py-3 text-center">
                <button
                  @click="handleRevoke(m)"
                  :disabled="revokingId === m.id"
                  class="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                  <X class="h-3 w-3" />
                  {{ revokingId === m.id ? '解除中' : '解除' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
