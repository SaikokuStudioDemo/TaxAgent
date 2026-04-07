<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { Plus, Wallet, Edit, Trash2, Save, X } from 'lucide-vue-next'
import { useCash, type CashAccount, type CashTransaction } from '@/composables/useCash'

const { accounts, transactions, isLoading, fetchAccounts, createAccount, fetchTransactions, createTransaction, updateTransaction, deleteTransaction } = useCash()

// ── 口座セレクター ─────────────────────────────────────────────
const selectedAccountId = ref<string>('all')

const selectedAccount = computed<CashAccount | null>(() =>
  selectedAccountId.value === 'all'
    ? null
    : accounts.value.find(a => a.id === selectedAccountId.value) ?? null
)

// ── 勘定科目マスタ ─────────────────────────────────────────────
const ACCOUNT_SUBJECTS = [
  '売上高', '売上返品', '受取利息', '受取配当金', '雑収入',
  '仕入高', '外注費', '給与手当', '役員報酬', '賞与', '法定福利費',
  '福利厚生費', '交際費', '会議費', '旅費交通費', '通信費',
  '消耗品費', '事務用品費', '新聞図書費', '広告宣伝費',
  '支払手数料', '地代家賃', '水道光熱費', '修繕費',
  '減価償却費', 'リース料', '保険料', '租税公課',
  '支払利息', '雑損失', '貸倒損失', '現金',
]

// ── 残高累積計算 ───────────────────────────────────────────────
const transactionsWithBalance = computed(() => {
  const filtered = selectedAccountId.value === 'all'
    ? transactions.value
    : transactions.value.filter(t => t.cash_account_id === selectedAccountId.value)

  // 口座ごとに独立して残高計算
  const accountMap = new Map<string, number>()

  // initial_balance をセット
  if (selectedAccountId.value === 'all') {
    accounts.value.forEach(a => accountMap.set(a.id, a.initial_balance))
  } else if (selectedAccount.value) {
    accountMap.set(selectedAccount.value.id, selectedAccount.value.initial_balance)
  }

  // transaction_date 昇順で累積計算（APIはすでに昇順）
  const result = filtered.map(tx => {
    const prev = accountMap.get(tx.cash_account_id) ?? 0
    const next = tx.direction === 'income' ? prev + tx.amount : prev - tx.amount
    accountMap.set(tx.cash_account_id, next)
    return { ...tx, runningBalance: next }
  })

  // 表示は降順（新しい順）
  return [...result].reverse()
})

// ── サマリー ───────────────────────────────────────────────────
const currentBalance = computed(() => {
  if (selectedAccountId.value === 'all') {
    return accounts.value.reduce((s, a) => s + a.current_balance, 0)
  }
  return selectedAccount.value?.current_balance ?? 0
})

const thisMonth = new Date().toISOString().slice(0, 7)

const monthlyIncome = computed(() =>
  transactionsWithBalance.value
    .filter(t => t.fiscal_period === thisMonth && t.direction === 'income')
    .reduce((s, t) => s + t.amount, 0)
)

const monthlyExpense = computed(() =>
  transactionsWithBalance.value
    .filter(t => t.fiscal_period === thisMonth && t.direction === 'expense')
    .reduce((s, t) => s + t.amount, 0)
)

const formatMoney = (n: number) => '¥' + n.toLocaleString()

// ── 口座作成モーダル ───────────────────────────────────────────
const showAccountModal = ref(false)
const newAccountName = ref('')
const newAccountBalance = ref(0)
const isSavingAccount = ref(false)

const openAccountModal = () => {
  newAccountName.value = ''
  newAccountBalance.value = 0
  showAccountModal.value = true
}

const saveAccount = async () => {
  if (!newAccountName.value.trim()) return
  isSavingAccount.value = true
  const ok = await createAccount({ name: newAccountName.value, initial_balance: newAccountBalance.value })
  isSavingAccount.value = false
  if (ok) {
    showAccountModal.value = false
    await loadAll()
  }
}

// ── 取引モーダル ──────────────────────────────────────────────
const showTxModal = ref(false)
const isEditingTx = ref(false)
const isSavingTx = ref(false)

type TxForm = {
  id: string
  cash_account_id: string
  transaction_date: string
  direction: 'income' | 'expense'
  amount: number
  description: string
  category: string
  fiscal_period: string
  note: string
}

const txForm = ref<TxForm>({
  id: '',
  cash_account_id: '',
  transaction_date: new Date().toISOString().slice(0, 10),
  direction: 'expense',
  amount: 0,
  description: '',
  category: '消耗品費',
  fiscal_period: thisMonth,
  note: '',
})

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
const onCategoryInput = () => { isTypingCategory.value = true; txForm.value.category = categoryQuery.value; showCategoryDropdown.value = true }
const onCategoryBlur = () => { setTimeout(() => { showCategoryDropdown.value = false }, 150) }
const selectCategory = (s: string) => {
  txForm.value.category = s
  categoryQuery.value = s
  showCategoryDropdown.value = false
  isTypingCategory.value = false
}

const openNewTx = () => {
  const defaultAccountId = selectedAccountId.value === 'all'
    ? (accounts.value[0]?.id ?? '')
    : selectedAccountId.value
  txForm.value = {
    id: '',
    cash_account_id: defaultAccountId,
    transaction_date: new Date().toISOString().slice(0, 10),
    direction: 'expense',
    amount: 0,
    description: '',
    category: '消耗品費',
    fiscal_period: thisMonth,
    note: '',
  }
  categoryQuery.value = '消耗品費'
  isEditingTx.value = false
  showTxModal.value = true
}

const openEditTx = (tx: CashTransaction) => {
  txForm.value = {
    id: tx.id,
    cash_account_id: tx.cash_account_id,
    transaction_date: tx.transaction_date,
    direction: tx.direction,
    amount: tx.amount,
    description: tx.description,
    category: tx.category,
    fiscal_period: tx.fiscal_period,
    note: tx.note ?? '',
  }
  categoryQuery.value = tx.category
  isEditingTx.value = true
  showTxModal.value = true
}

const saveTx = async () => {
  if (!txForm.value.cash_account_id || txForm.value.amount <= 0) return
  isSavingTx.value = true
  try {
    const { id, ...payload } = txForm.value
    if (isEditingTx.value) {
      await updateTransaction(id, payload)
    } else {
      await createTransaction({ ...payload, source: 'manual' })
    }
    showTxModal.value = false
    await loadAll()
  } finally {
    isSavingTx.value = false
  }
}

const handleDeleteTx = async (id: string) => {
  if (!confirm('この取引を削除しますか？')) return
  await deleteTransaction(id)
  await loadAll()
}

// ── データロード ──────────────────────────────────────────────
const loadAll = async () => {
  await fetchAccounts()
  const params = selectedAccountId.value === 'all' ? {} : { cash_account_id: selectedAccountId.value }
  await fetchTransactions(params)
}

const onAccountChange = async () => {
  const params = selectedAccountId.value === 'all' ? {} : { cash_account_id: selectedAccountId.value }
  await fetchTransactions(params)
}

onMounted(loadAll)
</script>

<template>
  <div class="p-6 md:p-8 max-w-7xl mx-auto">

    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
      <div class="flex items-center gap-3">
        <Wallet class="w-6 h-6 text-blue-600" />
        <h1 class="text-2xl font-bold text-slate-900">現金出納帳</h1>
      </div>
      <div class="flex items-center gap-3 flex-wrap">
        <!-- 口座セレクター -->
        <select
          v-model="selectedAccountId"
          @change="onAccountChange"
          class="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="all">全口座</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <button @click="openAccountModal"
          class="flex items-center gap-2 border border-slate-300 hover:bg-slate-50 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors">
          <Plus class="w-4 h-4" /> 口座を追加
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!isLoading && accounts.length === 0"
      class="text-center py-20 bg-white rounded-xl border border-slate-200">
      <Wallet class="w-12 h-12 text-slate-300 mx-auto mb-4" />
      <p class="text-slate-600 font-medium mb-2">現金口座がありません</p>
      <p class="text-slate-400 text-sm mb-6">「口座を追加」から現金口座を作成してください。</p>
      <button @click="openAccountModal"
        class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg text-sm font-bold transition-colors">
        <Plus class="w-4 h-4" /> 口座を追加
      </button>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div class="bg-white rounded-xl border border-slate-200 p-4">
          <p class="text-xs text-slate-500 mb-1">現在残高</p>
          <p class="text-2xl font-bold text-slate-900">{{ formatMoney(currentBalance) }}</p>
        </div>
        <div class="bg-white rounded-xl border border-slate-200 p-4">
          <p class="text-xs text-slate-500 mb-1">今月収入</p>
          <p class="text-2xl font-bold text-emerald-600">{{ formatMoney(monthlyIncome) }}</p>
        </div>
        <div class="bg-white rounded-xl border border-slate-200 p-4">
          <p class="text-xs text-slate-500 mb-1">今月支出</p>
          <p class="text-2xl font-bold text-red-500">{{ formatMoney(monthlyExpense) }}</p>
        </div>
      </div>

      <!-- Table -->
      <div class="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50 border-b border-slate-200">
              <tr>
                <th class="text-left px-4 py-3 font-semibold text-slate-700 whitespace-nowrap">日付</th>
                <th class="text-left px-4 py-3 font-semibold text-slate-700">摘要</th>
                <th class="text-left px-4 py-3 font-semibold text-slate-700 whitespace-nowrap">勘定科目</th>
                <th v-if="selectedAccountId === 'all'" class="text-left px-4 py-3 font-semibold text-slate-700 whitespace-nowrap">口座</th>
                <th class="text-right px-4 py-3 font-semibold text-emerald-700 whitespace-nowrap">収入</th>
                <th class="text-right px-4 py-3 font-semibold text-red-600 whitespace-nowrap">支出</th>
                <th class="text-right px-4 py-3 font-semibold text-slate-700 whitespace-nowrap">残高</th>
                <th class="text-left px-4 py-3 font-semibold text-slate-700 whitespace-nowrap">種別</th>
                <th class="text-left px-4 py-3 font-semibold text-slate-700 whitespace-nowrap">消込</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr
                @click="openNewTx"
                class="cursor-pointer hover:bg-blue-50 transition-colors border-b border-dashed border-blue-200"
              >
                <td :colspan="selectedAccountId === 'all' ? 10 : 9" class="px-4 py-3 text-center">
                  <div class="flex items-center justify-center gap-2 text-blue-500 font-medium text-sm">
                    <Plus :size="16" />
                    新規取引を追加
                  </div>
                </td>
              </tr>
              <tr v-if="isLoading">
                <td colspan="10" class="px-4 py-10 text-center text-slate-400">読み込み中...</td>
              </tr>
              <tr v-else-if="transactionsWithBalance.length === 0">
                <td colspan="10" class="px-4 py-10 text-center text-slate-400">取引がありません</td>
              </tr>
              <tr v-for="tx in transactionsWithBalance" :key="tx.id"
                class="hover:bg-slate-50 transition-colors group">
                <td class="px-4 py-3 text-slate-700 whitespace-nowrap">{{ tx.transaction_date }}</td>
                <td class="px-4 py-3 text-slate-800 max-w-xs truncate">{{ tx.description }}</td>
                <td class="px-4 py-3">
                  <span class="inline-flex items-center px-2 py-0.5 rounded bg-purple-50 text-purple-700 text-xs font-medium border border-purple-100">
                    {{ tx.category }}
                  </span>
                </td>
                <td v-if="selectedAccountId === 'all'" class="px-4 py-3 text-slate-600 whitespace-nowrap text-xs">
                  {{ accounts.find(a => a.id === tx.cash_account_id)?.name ?? '-' }}
                </td>
                <td class="px-4 py-3 text-right font-medium whitespace-nowrap">
                  <span v-if="tx.direction === 'income'" class="text-emerald-600">
                    {{ formatMoney(tx.amount) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-right font-medium whitespace-nowrap">
                  <span v-if="tx.direction === 'expense'" class="text-red-500">
                    {{ formatMoney(tx.amount) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-right font-bold whitespace-nowrap"
                  :class="tx.runningBalance >= 0 ? 'text-slate-800' : 'text-red-600'">
                  {{ formatMoney(tx.runningBalance) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap">
                  <span v-if="tx.source === 'bank_import'"
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600">
                    自動取込
                  </span>
                  <span v-else
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                    手入力
                  </span>
                </td>
                <td class="px-4 py-3 whitespace-nowrap">
                  <span v-if="tx.status === 'matched'"
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
                    消込済
                  </span>
                  <span v-else
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500">
                    未消込
                  </span>
                </td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button @click="openEditTx(tx)"
                      class="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors">
                      <Edit class="w-4 h-4" />
                    </button>
                    <button @click="handleDeleteTx(tx.id)"
                      class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- 取引登録・編集モーダル -->
    <div v-if="showTxModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" @click="showTxModal = false"></div>
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md relative z-10 overflow-hidden">
        <div class="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h2 class="text-lg font-bold text-slate-800">{{ isEditingTx ? '取引の編集' : '取引を追加' }}</h2>
          <button @click="showTxModal = false" class="text-slate-400 hover:text-slate-600 p-1">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="p-6 space-y-4">
          <!-- 口座 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">口座</label>
            <select v-model="txForm.cash_account_id"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
              <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
          </div>
          <!-- 日付 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">日付</label>
            <input type="date" v-model="txForm.transaction_date"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 収入/支出 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">種類</label>
            <div class="flex gap-2">
              <button @click="txForm.direction = 'expense'"
                :class="txForm.direction === 'expense' ? 'bg-red-600 text-white' : 'border border-slate-300 text-slate-600 hover:bg-slate-50'"
                class="flex-1 py-2 rounded-lg text-sm font-medium transition-colors">支出</button>
              <button @click="txForm.direction = 'income'"
                :class="txForm.direction === 'income' ? 'bg-emerald-600 text-white' : 'border border-slate-300 text-slate-600 hover:bg-slate-50'"
                class="flex-1 py-2 rounded-lg text-sm font-medium transition-colors">収入</button>
            </div>
          </div>
          <!-- 金額 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">金額</label>
            <input type="number" v-model.number="txForm.amount" min="0"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 摘要 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">摘要</label>
            <input type="text" v-model="txForm.description" placeholder="例: 文具購入"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
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
                  <li v-for="s in filteredCategories" :key="s"
                    @mousedown.prevent="selectCategory(s)"
                    class="px-3 py-2 text-sm cursor-pointer hover:bg-slate-50"
                    :class="s === txForm.category ? 'bg-blue-50 text-blue-700 font-medium' : 'text-slate-700'">
                    {{ s }}
                  </li>
                </ul>
              </Teleport>
            </div>
          </div>
          <!-- 備考 -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">備考</label>
            <input type="text" v-model="txForm.note" placeholder="任意"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
        </div>
        <div class="px-6 py-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3">
          <button @click="showTxModal = false"
            class="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">
            キャンセル
          </button>
          <button @click="saveTx" :disabled="isSavingTx"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-bold rounded-lg flex items-center gap-2 transition-colors">
            <Save class="w-4 h-4" /> {{ isSavingTx ? '保存中...' : '保存する' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 口座作成モーダル -->
    <div v-if="showAccountModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" @click="showAccountModal = false"></div>
      <div class="bg-white rounded-xl shadow-xl w-full max-w-sm relative z-10 overflow-hidden">
        <div class="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h2 class="text-lg font-bold text-slate-800">口座を追加</h2>
          <button @click="showAccountModal = false" class="text-slate-400 hover:text-slate-600 p-1">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="p-6 space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">口座名</label>
            <input type="text" v-model="newAccountName" placeholder="例: 本社現金"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">初期残高</label>
            <input type="number" v-model.number="newAccountBalance" min="0"
              class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
        </div>
        <div class="px-6 py-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3">
          <button @click="showAccountModal = false"
            class="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">
            キャンセル
          </button>
          <button @click="saveAccount" :disabled="isSavingAccount"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-bold rounded-lg flex items-center gap-2 transition-colors">
            <Save class="w-4 h-4" /> {{ isSavingAccount ? '作成中...' : '作成する' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>
