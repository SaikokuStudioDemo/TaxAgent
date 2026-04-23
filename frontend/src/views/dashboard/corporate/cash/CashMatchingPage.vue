<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { Link2, X, Save, CheckCircle2, Search, Wallet, FileSearch, CheckCircle } from 'lucide-vue-next'
import { useCash, type CashTransaction } from '@/composables/useCash'
import { api } from '@/lib/api'
import { MATCHING_STYLES } from '@/constants/matchingStyles'
import { getFiscalPeriod } from '@/lib/utils/formatters'

const { transactions: cashTxs, cashMatches, fetchTransactions, fetchCashMatches, createCashMatch, deleteCashMatch } = useCash()

// ── タブ ───────────────────────────────────────────────────────
const activeTab = ref<'unmatched' | 'matched'>('unmatched')

// ── 右ペイン データ ─────────────────────────────────────────────
interface RightItem {
  id: string
  kind: 'receipt' | 'invoice' | 'transaction'
  date: string
  description: string
  amount: number
  label: string
}

const rightItems = ref<RightItem[]>([])
const rightFilter = ref<'all' | 'receipt' | 'invoice' | 'transaction'>('all')
const rightSearch = ref('')

const filteredRightItems = computed(() => {
  let list = rightFilter.value === 'all'
    ? rightItems.value
    : rightItems.value.filter(i => i.kind === rightFilter.value)
  if (rightSearch.value) {
    const q = rightSearch.value.toLowerCase()
    list = list.filter(i => i.description.toLowerCase().includes(q) || i.amount.toString().includes(q))
  }
  return list
})

// ── 左ペイン（未消込 cash_transactions）──────────────────────────
const leftSearch = ref('')
const unmatchedCashTxs = computed(() => {
  let list = cashTxs.value.filter(t => t.status === 'unmatched')
  if (leftSearch.value) {
    const q = leftSearch.value.toLowerCase()
    list = list.filter(t => t.description.toLowerCase().includes(q) || t.amount.toString().includes(q))
  }
  return list
})

const matchedCashTxs = computed(() =>
  cashTxs.value.filter(t => t.status === 'matched')
)

// ── 選択状態 ──────────────────────────────────────────────────
const selectedCashTxId = ref<string | null>(null)
const selectedCashTx = computed<CashTransaction | null>(() =>
  selectedCashTxId.value ? cashTxs.value.find(t => t.id === selectedCashTxId.value) ?? null : null
)
const selectedRightIds = ref<string[]>([])

const getCashRemaining = (cashTx: CashTransaction) => {
  const matched = cashMatches.value
    .filter(m => m.cash_transaction_id === cashTx.id)
    .reduce((sum, m) => sum + (m.manual_amount ?? 0), 0)
  return cashTx.amount - matched
}

const selectedRightTotal = computed(() =>
  rightItems.value
    .filter(i => selectedRightIds.value.includes(i.id))
    .reduce((s, i) => s + i.amount, 0)
)

const matchDiff = computed(() =>
  selectedCashTx.value ? getCashRemaining(selectedCashTx.value) - selectedRightTotal.value : 0
)


// ── 消込済タブのマッチ詳細 ────────────────────────────────────
const matchedTabMatches = computed(() =>
  cashMatches.value.filter(m =>
    matchedCashTxs.value.some(t => t.id === m.cash_transaction_id)
  )
)

const getCashTxById = (id: string) =>
  cashTxs.value.find(t => t.id === id)

// ── 書類なし手動消込モーダル ──────────────────────────────────
const showManualModal = ref(false)
const isSavingManual = ref(false)

const ACCOUNT_SUBJECTS = [
  '売上高', '雑収入', '仕入高', '外注費', '給与手当', '役員報酬',
  '福利厚生費', '交際費', '会議費', '旅費交通費', '通信費',
  '消耗品費', '事務用品費', '広告宣伝費', '支払手数料', '地代家賃',
  '水道光熱費', '修繕費', '保険料', '租税公課', '支払利息', '雑損失', '現金',
]

const manualCategory = ref('消耗品費')
const manualDescription = ref('')
const manualAmount = ref(0)

// 勘定科目コンボボックス
const categoryQuery = ref('消耗品費')
const showCategoryDropdown = ref(false)
const isTypingCategory = ref(false)
const categoryInputRef = ref<HTMLInputElement | null>(null)
const dropdownStyle = ref<Record<string, string>>({})

const filteredCategories = computed(() =>
  isTypingCategory.value && categoryQuery.value.trim()
    ? ACCOUNT_SUBJECTS.filter(s => s.includes(categoryQuery.value))
    : ACCOUNT_SUBJECTS
)
const updateDropdownPos = () => {
  if (!categoryInputRef.value) return
  const r = categoryInputRef.value.getBoundingClientRect()
  dropdownStyle.value = { top: `${r.bottom + 4}px`, left: `${r.left}px`, width: `${r.width}px` }
}
const onCategoryFocus = () => {
  isTypingCategory.value = false
  nextTick(() => { updateDropdownPos(); showCategoryDropdown.value = true; categoryInputRef.value?.select() })
}
const onCategoryInput = () => { isTypingCategory.value = true; manualCategory.value = categoryQuery.value; showCategoryDropdown.value = true }
const onCategoryBlur = () => { setTimeout(() => { showCategoryDropdown.value = false }, 150) }
const selectCategory = (s: string) => {
  manualCategory.value = s; categoryQuery.value = s
  showCategoryDropdown.value = false; isTypingCategory.value = false
}

const openManualModal = () => {
  if (!selectedCashTx.value) return
  manualAmount.value = getCashRemaining(selectedCashTx.value)
  manualDescription.value = selectedCashTx.value.description
  manualCategory.value = '消耗品費'
  categoryQuery.value = '消耗品費'
  showManualModal.value = true
}

const saveManualMatch = async () => {
  if (!selectedCashTxId.value) return
  isSavingManual.value = true
  const ok = await createCashMatch({
    cash_transaction_id: selectedCashTxId.value,
    document_ids: [],
    transaction_ids: [],
    no_document_reason: '書類なし手動消込',
    manual_category: manualCategory.value,
    manual_description: manualDescription.value,
    manual_amount: manualAmount.value,
    fiscal_period: getFiscalPeriod(),
  })
  isSavingManual.value = false
  if (ok) {
    showManualModal.value = false
    selectedCashTxId.value = null
    selectedRightIds.value = []
    await loadAll()
  }
}

// ── 消込実行 ──────────────────────────────────────────────────
const isMatching = ref(false)

const handleMatch = async () => {
  if (!selectedCashTxId.value || selectedRightIds.value.length === 0) return
  isMatching.value = true

  const selected = rightItems.value.filter(i => selectedRightIds.value.includes(i.id))
  const docIds = selected.filter(i => i.kind === 'receipt' || i.kind === 'invoice').map(i => i.id)
  const txIds = selected.filter(i => i.kind === 'transaction').map(i => i.id)

  const ok = await createCashMatch({
    cash_transaction_id: selectedCashTxId.value,
    document_ids: docIds,
    transaction_ids: txIds,
    fiscal_period: getFiscalPeriod(),
  })
  isMatching.value = false
  if (ok) {
    selectedCashTxId.value = null
    selectedRightIds.value = []
    await loadAll()
  }
}

// ── 消込解除 ──────────────────────────────────────────────────
const handleUnmatch = async (matchId: string) => {
  if (!confirm('消込を解除しますか？')) return
  const ok = await deleteCashMatch(matchId)
  if (ok) await loadAll()
}

// ── データロード ──────────────────────────────────────────────
const isLoading = ref(false)

const loadAll = async () => {
  isLoading.value = true
  try {
    await Promise.all([
      fetchTransactions({}),
      fetchCashMatches(),
    ])

    const [receiptsData, invoicesData, txData] = await Promise.all([
      api.get<any[]>('/receipts?reconciliation_status=unreconciled'),
      api.get<any[]>('/invoices?reconciliation_status=unreconciled'),
      api.get<any[]>('/transactions?status=unmatched'),
    ])

    const items: RightItem[] = [
      ...receiptsData.map(r => ({
        id: r.id,
        kind: 'receipt' as const,
        date: r.date,
        description: `${r.payee ?? ''} ${r.submitter_name ?? ''}`.trim(),
        amount: r.amount,
        label: '領収書',
      })),
      ...invoicesData.map(inv => ({
        id: inv.id,
        kind: 'invoice' as const,
        date: inv.issue_date ?? inv.created_at?.slice(0, 10) ?? '',
        description: inv.payee ?? inv.client_name ?? '',
        amount: inv.total_amount ?? inv.amount ?? 0,
        label: '請求書',
      })),
      ...txData.map(t => ({
        id: t.id,
        kind: 'transaction' as const,
        date: t.transaction_date,
        description: t.description,
        amount: t.amount,
        label: t.source_type === 'bank' ? '銀行' : 'カード',
      })),
    ]
    rightItems.value = items
  } finally {
    isLoading.value = false
  }
}

const toggleRight = (id: string) => {
  const idx = selectedRightIds.value.indexOf(id)
  if (idx > -1) selectedRightIds.value.splice(idx, 1)
  else selectedRightIds.value.push(id)
}

const selectCashTx = (id: string) => {
  if (selectedCashTxId.value === id) {
    selectedCashTxId.value = null
    selectedRightIds.value = []
  } else {
    selectedCashTxId.value = id
    selectedRightIds.value = []
  }
}

const formatMoney = (n: number) => '¥' + n.toLocaleString()

onMounted(loadAll)
</script>

<template>
  <div class="space-y-6 h-full flex flex-col">

    <!-- Header -->
    <div class="flex flex-col gap-4 shrink-0">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">現金消込</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          現金出納帳のデータと、領収書・請求書・銀行/カードデータを照合して消込処理を行います。
        </p>
      </div>
    </div>

    <!-- Tabs -->
    <div :class="MATCHING_STYLES.tabContainer">
      <button @click="activeTab = 'unmatched'"
        :class="[MATCHING_STYLES.tabBase, activeTab === 'unmatched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]">
        未消込 ({{ unmatchedCashTxs.length }})
      </button>
      <button @click="activeTab = 'matched'"
        :class="[MATCHING_STYLES.tabBase, activeTab === 'matched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]">
        消込済 ({{ matchedCashTxs.length }})
      </button>
    </div>

    <!-- ── 未消込タブ ── -->
    <template v-if="activeTab === 'unmatched'">
      <div class="flex-1 flex flex-col min-h-0">

      <!-- ガイダンスバー（3状態） -->
      <div class="shrink-0 transition-all mb-4">
        <!-- 1. 両方選択済み → 消込準備完了 -->
        <div v-if="selectedCashTxId && selectedRightIds.length > 0" :class="MATCHING_STYLES.guidanceBarActive">
          <div class="flex items-start gap-3 w-full md:w-auto">
            <div class="bg-white/20 p-2 rounded-full hidden sm:block mt-1"><Link2 class="h-5 w-5" /></div>
            <div class="flex-1">
              <div class="flex items-center gap-2 mb-1">
                <p class="font-bold text-lg">消込準備完了</p>
                <span v-if="matchDiff === 0" class="text-xs bg-emerald-500 text-white px-2 py-0.5 rounded-full font-bold">金額ピタリ一致</span>
                <span v-else class="text-xs bg-amber-500 text-white px-2 py-0.5 rounded-full font-bold">差額あり</span>
              </div>
              <div class="text-blue-50 text-sm flex items-center gap-3 bg-black/10 px-3 py-1.5 rounded-lg border border-white/10 mt-2 text-white">
                <div>現金残高: <strong>{{ formatMoney(getCashRemaining(selectedCashTx!)) }}</strong></div>
                <div>-</div>
                <div>選択合計: <strong>{{ formatMoney(selectedRightTotal) }}</strong></div>
                <div>=</div>
                <div :class="matchDiff === 0 ? 'text-emerald-300' : 'text-amber-300'">
                  差額: <strong>{{ formatMoney(Math.abs(matchDiff)) }}</strong>
                </div>
              </div>
            </div>
          </div>
          <button @click="handleMatch" :disabled="isMatching"
            :class="['w-full md:w-auto disabled:opacity-50 disabled:cursor-not-allowed', MATCHING_STYLES.matchButton]">
            <CheckCircle2 class="w-5 h-5" />
            <span>{{ isMatching ? '処理中...' : 'この内容で消込する' }}</span>
          </button>
        </div>

        <!-- 2. 左（現金）のみ選択 → 右を選んでください -->
        <div v-else-if="selectedCashTxId && selectedRightIds.length === 0" :class="MATCHING_STYLES.guidanceBarWarning">
          <span class="flex h-6 w-6 items-center justify-center rounded-full bg-amber-200 text-amber-900 text-sm font-bold border border-amber-400 shrink-0 shadow-sm animate-pulse">!</span>
          <p class="font-bold">右の消込対象リスト (現金残高 {{ formatMoney(getCashRemaining(selectedCashTx!)) }}) に対応するデータを選択してください。</p>
        </div>

        <!-- 3. 何も選択していない → デフォルト -->
        <div v-else :class="MATCHING_STYLES.guidanceBarDefault">
          <Link2 class="h-5 w-5 opacity-50" />
          <p class="font-medium text-sm">消込を開始するには、左の現金取引リストから対象を選択してください。</p>
        </div>
      </div>

      <!-- 左右分割 -->
      <div class="flex-1 flex flex-col lg:flex-row gap-6 min-h-0">

        <!-- 左ペイン：現金出納帳 -->
        <div :class="MATCHING_STYLES.paneBase">
          <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-blue-50/50']">
            <div class="flex items-center gap-2">
              <Wallet class="text-blue-700 h-5 w-5" />
              <h2 class="font-bold text-gray-800 text-base">現金出納帳</h2>
              <span class="bg-blue-100 text-blue-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedCashTxs.length }}</span>
            </div>
          </div>
          <div class="p-3 border-b border-gray-100 shrink-0">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input v-model="leftSearch" type="text" placeholder="摘要・金額で検索..."
                :class="MATCHING_STYLES.searchInput" />
            </div>
          </div>
          <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-blue-50/10">
            <div v-if="isLoading" class="p-8 text-center text-gray-400 text-sm">読み込み中...</div>
            <div v-else-if="unmatchedCashTxs.length === 0" class="p-8 text-center text-gray-400 text-sm">未消込の現金取引がありません</div>
            <div v-for="tx in unmatchedCashTxs" :key="tx.id"
              @click="selectCashTx(tx.id)"
              :class="[MATCHING_STYLES.cardBase, 'flex flex-col justify-between min-h-[90px]', selectedCashTxId === tx.id ? MATCHING_STYLES.cardSelected : '']">
              <div v-if="selectedCashTxId === tx.id" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
              <div v-if="selectedCashTxId === tx.id" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                <CheckCircle class="w-4 h-4" />
              </div>
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs text-gray-500">{{ tx.transaction_date }}</span>
                <span class="text-xs px-2 py-0.5 rounded-full font-medium"
                  :class="tx.direction === 'income' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'">
                  {{ tx.direction === 'income' ? '収入' : '支出' }}
                </span>
              </div>
              <div class="pr-8">
                <p class="text-sm font-bold text-gray-800 leading-tight truncate">{{ tx.description }}</p>
                <p class="text-lg font-bold tracking-tight text-gray-900 mt-1">{{ formatMoney(tx.amount) }}</p>
              </div>
              <div class="mt-1 text-xs text-gray-400">
                残高: <span class="font-medium text-gray-600">{{ formatMoney(getCashRemaining(tx)) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 中央アイコン -->
        <div class="hidden lg:flex flex-col items-center justify-center -mx-2 z-10 shrink-0">
          <div :class="MATCHING_STYLES.centerIcon">
            <Link2 class="h-5 w-5 text-blue-500" />
          </div>
        </div>

        <!-- 右ペイン：消込対象データ -->
        <div :class="MATCHING_STYLES.paneBase">
          <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-slate-50']">
            <div class="flex items-center gap-2">
              <FileSearch class="text-slate-600 h-5 w-5" />
              <h2 class="font-bold text-gray-800 text-base">消込対象</h2>
              <span class="bg-slate-200 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ filteredRightItems.length }}</span>
            </div>
            <!-- フィルタータブ（現金固有） -->
            <div class="flex gap-1">
              <button v-for="f in ([['all','全て'],['receipt','領収書'],['invoice','請求書'],['transaction','銀行・カード']] as const)"
                :key="f[0]" @click="rightFilter = f[0]"
                :class="rightFilter === f[0] ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
                class="px-2.5 py-1 rounded text-xs font-medium transition-colors">
                {{ f[1] }}
              </button>
            </div>
          </div>
          <div class="p-3 border-b border-gray-100 shrink-0">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input v-model="rightSearch" type="text" placeholder="摘要・金額で検索..."
                :class="MATCHING_STYLES.searchInput" />
            </div>
          </div>
          <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50/30">
            <div v-if="filteredRightItems.length === 0" class="p-8 text-center text-gray-400 text-sm">データがありません</div>
            <div v-for="item in filteredRightItems" :key="item.id"
              @click="toggleRight(item.id)"
              :class="[MATCHING_STYLES.cardBase, 'flex flex-col justify-between min-h-[90px]', selectedRightIds.includes(item.id) ? MATCHING_STYLES.cardSelected : '']">
              <div v-if="selectedRightIds.includes(item.id)" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
              <div v-if="selectedRightIds.includes(item.id)" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                <CheckCircle class="w-4 h-4" />
              </div>
              <div class="flex justify-between items-start mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-50 text-gray-600 border-gray-200">{{ item.label }}</span>
                  <span class="text-xs text-gray-500 font-medium">{{ item.date }}</span>
                </div>
                <p class="text-lg font-bold tracking-tight text-gray-900 whitespace-nowrap ml-4">{{ formatMoney(item.amount) }}</p>
              </div>
              <div class="pr-8">
                <p class="text-sm font-bold text-gray-800 leading-tight">{{ item.description || '（摘要なし）' }}</p>
              </div>
            </div>
          </div>
          <!-- 書類なし手動消込（現金固有） -->
          <div class="px-4 py-3 border-t border-gray-200 bg-gray-50 shrink-0">
            <button @click="openManualModal" :disabled="!selectedCashTxId"
              class="w-full py-2 text-sm font-medium text-blue-600 hover:text-blue-800 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors border border-dashed border-blue-300 disabled:border-gray-200 rounded-lg">
              ＋ 書類なしで手動消込
            </button>
          </div>
        </div>
      </div>

      </div><!-- /flex-1 flex flex-col -->
    </template>

    <!-- ── 消込済タブ ── -->
    <template v-else>
      <div class="flex-1 overflow-y-auto min-h-0">
      <div v-if="matchedTabMatches.length === 0" class="flex flex-col items-center justify-center py-20 bg-white rounded-xl border border-gray-200 shadow-sm">
        <Link2 class="h-16 w-16 mb-4 text-gray-200" />
        <p class="text-base font-medium text-gray-500">消込済のデータがありません</p>
      </div>
      <div v-else class="space-y-3">
        <div v-for="m in matchedTabMatches" :key="m.id"
          class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-start justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-2">
              <span class="text-sm font-bold text-gray-900">
                {{ getCashTxById(m.cash_transaction_id)?.description ?? '（現金取引）' }}
              </span>
              <span v-if="m.no_document_reason"
                class="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
                手動処理済
              </span>
            </div>
            <div class="text-xs text-gray-500 space-y-0.5">
              <p>現金金額: <span class="font-medium text-gray-700">{{ formatMoney(getCashTxById(m.cash_transaction_id)?.amount ?? 0) }}</span></p>
              <p v-if="m.manual_description">摘要: {{ m.manual_description }}</p>
              <p v-if="m.manual_category">勘定科目: {{ m.manual_category }}</p>
              <p v-if="m.document_ids.length > 0">書類: {{ m.document_ids.length }}件</p>
              <p v-if="m.transaction_ids.length > 0">銀行/カード: {{ m.transaction_ids.length }}件</p>
              <p>消込日: {{ m.matched_at?.slice(0, 10) }}</p>
            </div>
          </div>
          <button @click="handleUnmatch(m.id)"
            class="shrink-0 text-xs px-3 py-1.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg transition-colors font-medium">
            消込解除
          </button>
        </div>
      </div>
      </div><!-- /flex-1 overflow-y-auto -->
    </template>

    <!-- 書類なし手動消込モーダル -->
    <div v-if="showManualModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" @click="showManualModal = false"></div>
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md relative z-10 overflow-hidden">
        <div class="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h2 class="text-lg font-bold text-slate-800">書類なしで手動消込</h2>
          <button @click="showManualModal = false" class="text-slate-400 hover:text-slate-600 p-1"><X class="w-5 h-5" /></button>
        </div>
        <div class="p-6 space-y-4">
          <!-- 勘定科目 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">勘定科目</label>
            <div class="relative">
              <input ref="categoryInputRef" type="text" v-model="categoryQuery"
                @input="onCategoryInput" @focus="onCategoryFocus" @blur="onCategoryBlur"
                autocomplete="off"
                class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
              <Teleport to="body">
                <ul v-if="showCategoryDropdown && filteredCategories.length > 0" :style="dropdownStyle"
                  class="fixed z-[9999] bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  <li v-for="s in filteredCategories" :key="s" @mousedown.prevent="selectCategory(s)"
                    class="px-3 py-2 text-sm cursor-pointer hover:bg-slate-50"
                    :class="s === manualCategory ? 'bg-blue-50 text-blue-700 font-medium' : 'text-slate-700'">
                    {{ s }}
                  </li>
                </ul>
              </Teleport>
            </div>
          </div>
          <!-- 摘要 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">摘要</label>
            <input type="text" v-model="manualDescription"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 金額 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">金額</label>
            <input type="number" v-model.number="manualAmount" min="0"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
        </div>
        <div class="px-6 py-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3">
          <button @click="showManualModal = false"
            class="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">キャンセル</button>
          <button @click="saveManualMatch" :disabled="isSavingManual"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-bold rounded-lg flex items-center gap-2 transition-colors">
            <Save class="w-4 h-4" />{{ isSavingManual ? '処理中...' : '処理済みにする' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>
