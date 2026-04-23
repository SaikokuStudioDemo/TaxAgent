<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'
import { useSystemSettings } from '@/composables/useSystemSettings'

// ── 手数料率 ──────────────────────────────────────────────────────────────────
const currentRate = ref<number | null>(null)
const inputRate = ref<string>('')
const isLoading = ref(true)
const isSaving = ref(false)
const error = ref<string | null>(null)
const successMsg = ref<string | null>(null)
const showConfirm = ref(false)
const pendingRate = ref<number | null>(null)

const fetchFeeRate = async () => {
  isLoading.value = true
  error.value = null
  try {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
    const res = await fetch(`${apiUrl}/system-settings/fee-rate`)
    const data = await res.json()
    currentRate.value = data.platform_fee_rate
    inputRate.value = String(Math.round(data.platform_fee_rate * 100))
  } catch {
    error.value = '手数料率の取得に失敗しました'
  } finally {
    isLoading.value = false
  }
}

const requestSave = () => {
  error.value = null
  const parsed = parseFloat(inputRate.value)
  if (isNaN(parsed) || parsed < 0 || parsed > 100) {
    error.value = '0〜100 の範囲で入力してください'
    return
  }
  pendingRate.value = parsed / 100
  showConfirm.value = true
}

const confirmSave = async () => {
  if (pendingRate.value === null) return
  showConfirm.value = false
  isSaving.value = true
  error.value = null
  try {
    await api.put('/system-settings/fee-rate', { platform_fee_rate: pendingRate.value })
    currentRate.value = pendingRate.value
    successMsg.value = `手数料率を ${Math.round(pendingRate.value * 100)}% に更新しました`
    setTimeout(() => { successMsg.value = null }, 4000)
  } catch (e: any) {
    error.value = e.message || '保存に失敗しました'
  } finally {
    isSaving.value = false
    pendingRate.value = null
  }
}

const cancelConfirm = () => {
  showConfirm.value = false
  pendingRate.value = null
}

const currentRatePercent = () =>
  currentRate.value !== null ? Math.round(currentRate.value * 100) : '—'

// ── 税率設定 ──────────────────────────────────────────────────────────────────
const { taxRates, fetchTaxRates } = useSystemSettings()
const inputStandard = ref<string>('10')
const inputReduced = ref<string>('8')
const inputExempt = ref<string>('0')
const isTaxRateLoading = ref(true)
const isTaxRateSaving = ref(false)
const taxRateError = ref<string | null>(null)
const taxRateSuccess = ref<string | null>(null)

const loadTaxRates = async () => {
  isTaxRateLoading.value = true
  taxRateError.value = null
  try {
    await fetchTaxRates()
    inputStandard.value = String(taxRates.value.standard)
    inputReduced.value = String(taxRates.value.reduced)
    inputExempt.value = String(taxRates.value.exempt)
  } catch {
    taxRateError.value = '税率設定の取得に失敗しました'
  } finally {
    isTaxRateLoading.value = false
  }
}

const saveTaxRates = async () => {
  taxRateError.value = null
  const standard = parseInt(inputStandard.value, 10)
  const reduced = parseInt(inputReduced.value, 10)
  const exempt = parseInt(inputExempt.value, 10)
  for (const [label, v] of [['標準税率', standard], ['軽減税率', reduced], ['非課税', exempt]] as [string, number][]) {
    if (isNaN(v) || v < 0 || v > 100) {
      taxRateError.value = `${label} は 0〜100 の整数で入力してください`
      return
    }
  }
  isTaxRateSaving.value = true
  try {
    await api.put('/system-settings/tax-rates', { standard, reduced, exempt })
    taxRates.value = { standard, reduced, exempt }
    taxRateSuccess.value = '税率設定を更新しました'
    setTimeout(() => { taxRateSuccess.value = null }, 4000)
  } catch (e: any) {
    taxRateError.value = e.message || '保存に失敗しました'
  } finally {
    isTaxRateSaving.value = false
  }
}

// ── Law Agent URL ─────────────────────────────────────────────────────────────
const currentLawAgentUrl = ref<string | null>(null)
const inputLawAgentUrl = ref<string>('')
const isLawUrlLoading = ref(true)
const isLawUrlSaving = ref(false)
const lawUrlError = ref<string | null>(null)
const lawUrlSuccess = ref<string | null>(null)
const showLawUrlConfirm = ref(false)
const pendingLawUrl = ref<string | null>(null)

const fetchLawAgentUrl = async () => {
  isLawUrlLoading.value = true
  lawUrlError.value = null
  try {
    const data = await api.get('/system-settings/law-agent-url')
    currentLawAgentUrl.value = data.law_agent_url
    inputLawAgentUrl.value = data.law_agent_url
  } catch {
    lawUrlError.value = 'Law Agent URL の取得に失敗しました'
  } finally {
    isLawUrlLoading.value = false
  }
}

const requestSaveLawUrl = () => {
  lawUrlError.value = null
  const url = inputLawAgentUrl.value.trim()
  if (!url) {
    lawUrlError.value = 'URL を入力してください'
    return
  }
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    lawUrlError.value = 'http:// または https:// で始まるURLを入力してください'
    return
  }
  pendingLawUrl.value = url
  showLawUrlConfirm.value = true
}

const confirmSaveLawUrl = async () => {
  if (!pendingLawUrl.value) return
  showLawUrlConfirm.value = false
  isLawUrlSaving.value = true
  lawUrlError.value = null
  try {
    await api.put('/system-settings/law-agent-url', { law_agent_url: pendingLawUrl.value })
    currentLawAgentUrl.value = pendingLawUrl.value
    lawUrlSuccess.value = 'Law Agent URL を更新しました'
    setTimeout(() => { lawUrlSuccess.value = null }, 4000)
  } catch (e: any) {
    lawUrlError.value = e.message || '保存に失敗しました'
  } finally {
    isLawUrlSaving.value = false
    pendingLawUrl.value = null
  }
}

const cancelLawUrlConfirm = () => {
  showLawUrlConfirm.value = false
  pendingLawUrl.value = null
}

onMounted(() => {
  fetchFeeRate()
  fetchLawAgentUrl()
  loadTaxRates()
})
</script>

<template>
  <div class="p-8 max-w-2xl">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-slate-900 mb-1">システム設定</h1>
      <p class="text-slate-500 text-sm">プラットフォーム全体の設定を管理します。</p>
    </div>

    <div v-if="successMsg" class="mb-6 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg px-4 py-3 text-sm">
      {{ successMsg }}
    </div>

    <!-- 手数料率設定 -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
      <h2 class="text-base font-bold text-slate-800 mb-1">手数料率設定</h2>
      <p class="text-sm text-slate-500 mb-5">プラットフォームが税理士法人から徴収する手数料率（売上に対する割合）です。</p>

      <div v-if="isLoading" class="text-slate-400 text-sm">読み込み中...</div>
      <div v-else class="space-y-4">
        <div class="flex items-center gap-3 text-sm text-slate-600 bg-slate-50 rounded-lg px-4 py-3">
          <span>現在の手数料率：</span>
          <span class="text-xl font-bold text-slate-900">{{ currentRatePercent() }}%</span>
        </div>

        <div class="flex items-end gap-3">
          <div class="flex-1">
            <label class="block text-sm font-medium text-slate-700 mb-1">新しい手数料率（%）</label>
            <div class="flex items-center border border-slate-300 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-sky-500">
              <input
                v-model="inputRate"
                type="number"
                min="0"
                max="100"
                step="0.1"
                class="flex-1 px-3 py-2 text-sm outline-none"
                placeholder="例：20"
              />
              <span class="bg-slate-50 border-l border-slate-300 px-3 py-2 text-sm text-slate-500 font-medium">%</span>
            </div>
          </div>
          <button
            @click="requestSave"
            :disabled="isSaving"
            class="px-5 py-2 bg-sky-500 hover:bg-sky-400 disabled:bg-slate-300 text-white font-bold text-sm rounded-lg transition-colors whitespace-nowrap"
          >
            {{ isSaving ? '保存中...' : '変更を保存' }}
          </button>
        </div>

        <div v-if="error" class="text-red-600 text-sm">{{ error }}</div>
      </div>
    </section>

    <!-- 税率設定 -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
      <h2 class="text-base font-bold text-slate-800 mb-1">税率設定</h2>
      <p class="text-sm text-slate-500 mb-5">新規登録時のデフォルト税率を設定します。既存のデータには影響しません。</p>

      <div v-if="taxRateSuccess" class="mb-4 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg px-4 py-3 text-sm">
        {{ taxRateSuccess }}
      </div>

      <div v-if="isTaxRateLoading" class="text-slate-400 text-sm">読み込み中...</div>
      <div v-else class="space-y-4">
        <div class="grid grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">標準税率</label>
            <div class="flex items-center border border-slate-300 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-sky-500">
              <input v-model="inputStandard" type="number" min="0" max="100" step="1"
                class="flex-1 px-3 py-2 text-sm outline-none" placeholder="10" />
              <span class="bg-slate-50 border-l border-slate-300 px-3 py-2 text-sm text-slate-500 font-medium">%</span>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">軽減税率</label>
            <div class="flex items-center border border-slate-300 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-sky-500">
              <input v-model="inputReduced" type="number" min="0" max="100" step="1"
                class="flex-1 px-3 py-2 text-sm outline-none" placeholder="8" />
              <span class="bg-slate-50 border-l border-slate-300 px-3 py-2 text-sm text-slate-500 font-medium">%</span>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">非課税</label>
            <div class="flex items-center border border-slate-300 rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-sky-500">
              <input v-model="inputExempt" type="number" min="0" max="100" step="1"
                class="flex-1 px-3 py-2 text-sm outline-none" placeholder="0" />
              <span class="bg-slate-50 border-l border-slate-300 px-3 py-2 text-sm text-slate-500 font-medium">%</span>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between">
          <p class="text-xs text-slate-400">※ 税率変更は新規登録時のデフォルト値に反映されます。既存のデータには影響しません。</p>
          <button
            @click="saveTaxRates"
            :disabled="isTaxRateSaving"
            class="px-5 py-2 bg-sky-500 hover:bg-sky-400 disabled:bg-slate-300 text-white font-bold text-sm rounded-lg transition-colors whitespace-nowrap"
          >
            {{ isTaxRateSaving ? '保存中...' : '保存する' }}
          </button>
        </div>

        <div v-if="taxRateError" class="text-red-600 text-sm">{{ taxRateError }}</div>
      </div>
    </section>

    <!-- Law Agent URL 設定 -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
      <h2 class="text-base font-bold text-slate-800 mb-1">Law Agent URL 設定</h2>
      <p class="text-sm text-slate-500 mb-5">税務QA機能が使用する外部AIサービスの接続先URLです。</p>

      <div v-if="lawUrlSuccess" class="mb-4 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg px-4 py-3 text-sm">
        {{ lawUrlSuccess }}
      </div>

      <div v-if="isLawUrlLoading" class="text-slate-400 text-sm">読み込み中...</div>
      <div v-else class="space-y-4">
        <div class="flex items-center gap-3 text-sm text-slate-600 bg-slate-50 rounded-lg px-4 py-3">
          <span class="shrink-0">現在のURL：</span>
          <span class="font-mono text-slate-900 truncate">{{ currentLawAgentUrl || '—' }}</span>
        </div>

        <div class="flex items-end gap-3">
          <div class="flex-1">
            <label class="block text-sm font-medium text-slate-700 mb-1">新しいURL</label>
            <input
              v-model="inputLawAgentUrl"
              type="url"
              class="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-sky-500 font-mono"
              placeholder="https://law-agent.example.com"
            />
          </div>
          <button
            @click="requestSaveLawUrl"
            :disabled="isLawUrlSaving"
            class="px-5 py-2 bg-sky-500 hover:bg-sky-400 disabled:bg-slate-300 text-white font-bold text-sm rounded-lg transition-colors whitespace-nowrap"
          >
            {{ isLawUrlSaving ? '保存中...' : '変更を保存' }}
          </button>
        </div>

        <div v-if="lawUrlError" class="text-red-600 text-sm">{{ lawUrlError }}</div>
      </div>
    </section>

    <!-- Law Agent URL 確認ダイアログ -->
    <Teleport to="body">
      <div v-if="showLawUrlConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
          <h3 class="text-base font-bold text-slate-900 mb-3">Law Agent URL の変更確認</h3>
          <p class="text-sm text-slate-600 mb-6 leading-relaxed">
            Law Agent URL を変更します。<br />
            接続先のAIサービスが変わります。<br />
            よろしいですか？
          </p>
          <div class="flex justify-end gap-3">
            <button @click="cancelLawUrlConfirm" class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 font-medium transition-colors">
              キャンセル
            </button>
            <button @click="confirmSaveLawUrl" class="px-5 py-2 text-sm bg-sky-500 hover:bg-sky-400 text-white font-bold rounded-lg transition-colors">
              変更する
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 手数料率 確認ダイアログ -->
    <Teleport to="body">
      <div v-if="showConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6">
          <h3 class="text-base font-bold text-slate-900 mb-3">手数料率の変更確認</h3>
          <p class="text-sm text-slate-600 mb-6 leading-relaxed">
            手数料率を <span class="font-bold text-slate-900">{{ currentRatePercent() }}%</span> から
            <span class="font-bold text-sky-600">{{ Math.round((pendingRate ?? 0) * 100) }}%</span> に変更します。<br />
            既存の課金設定には影響しません。よろしいですか？
          </p>
          <div class="flex justify-end gap-3">
            <button @click="cancelConfirm" class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 font-medium transition-colors">
              キャンセル
            </button>
            <button @click="confirmSave" class="px-5 py-2 text-sm bg-sky-500 hover:bg-sky-400 text-white font-bold rounded-lg transition-colors">
              変更する
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
