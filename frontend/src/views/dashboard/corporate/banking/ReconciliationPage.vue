<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  Link2, CheckCircle2, FileText, Receipt, ChevronRight,
  Loader2, AlertCircle, Check, X, Lock, Search, RotateCcw, Clock
} from 'lucide-vue-next';
import { formatCurrency } from '@/lib/utils/formatters';
import { useTransactions, type Transaction } from '@/composables/useTransactions';
import { useReceipts, type Receipt as ReceiptDoc } from '@/composables/useReceipts';
import { useInvoices, type Invoice } from '@/composables/useInvoices';
import { api } from '@/lib/api';

// ── 勘定科目マスタ ────────────────────────────────────────────
const ACCOUNT_SUBJECTS = [
  '売上高', '売上返品', '受取利息', '受取配当金', '雑収入',
  '仕入高', '外注費', '給与手当', '役員報酬', '賞与', '法定福利費',
  '福利厚生費', '交際費', '会議費', '旅費交通費', '通信費',
  '消耗品費', '事務用品費', '新聞図書費', '広告宣伝費',
  '支払手数料', '地代家賃', '水道光熱費', '修繕費',
  '減価償却費', 'リース料', '保険料', '租税公課',
  '支払利息', '雑損失', '貸倒損失', '現金',
];

// ── composables ──────────────────────────────────────────────
const { transactions, fetchTransactions } = useTransactions();
const { receipts, fetchReceipts } = useReceipts();
const { invoices, fetchInvoices } = useInvoices();

// ── state：共通 ───────────────────────────────────────────────
const txTab = ref<'bank' | 'card'>('bank');
const statusTab = ref<'unmatched' | 'matched' | 'transferred'>('unmatched');
const selectedTx = ref<Transaction | null>(null);
const isSubmitting = ref(false);
const successMessage = ref('');
const errorMessage = ref('');

// ── state：未消込フォーム用 ───────────────────────────────────
const accountSubject = ref('');
const memo = ref('');
const selectedDocumentId = ref<string | null>(null);
const selectedDocumentType = ref<'receipt' | 'invoice' | null>(null);
const showAccountDropdown = ref(false);

// ── state：消込済み詳細表示用 ─────────────────────────────────
const matchDetail = ref<any | null>(null);
const matchDocuments = ref<Array<{ type: 'receipt' | 'invoice'; doc: any }>>([]);
const isLoadingDetail = ref(false);
const auditEvents = ref<any[]>([]);
const isCancelling = ref(false);

// ── state：検索 ───────────────────────────────────────────────
const searchQuery    = ref('');
const searchDateMin  = ref('');
const searchDateMax  = ref('');
const searchAmountMin = ref<number | ''>('');
const searchAmountMax = ref<number | ''>('');
const hasSearch = computed(() =>
  !!(searchQuery.value || searchDateMin.value || searchDateMax.value ||
     searchAmountMin.value !== '' || searchAmountMax.value !== '')
);
const clearSearch = () => {
  searchQuery.value = '';
  searchDateMin.value = '';
  searchDateMax.value = '';
  searchAmountMin.value = '';
  searchAmountMax.value = '';
};

// ── filtered transactions ─────────────────────────────────────
const unmatchedTxs = computed(() =>
  transactions.value.filter(t => t.source_type === txTab.value && t.status === 'unmatched')
);
const matchedTxs = computed(() =>
  transactions.value.filter(t => t.source_type === txTab.value && t.status === 'matched')
);
const transferredTxs = computed(() =>
  transactions.value.filter(t => t.source_type === txTab.value && t.status === 'transferred')
);
const displayedTxs = computed(() => {
  let list = statusTab.value === 'matched' ? matchedTxs.value
           : statusTab.value === 'transferred' ? transferredTxs.value
           : unmatchedTxs.value;
  if (searchQuery.value)
    list = list.filter(t => (t.description || '').includes(searchQuery.value));
  if (searchDateMin.value)
    list = list.filter(t => t.transaction_date >= searchDateMin.value);
  if (searchDateMax.value)
    list = list.filter(t => t.transaction_date <= searchDateMax.value);
  if (searchAmountMin.value !== '')
    list = list.filter(t => t.amount >= Number(searchAmountMin.value));
  if (searchAmountMax.value !== '')
    list = list.filter(t => t.amount <= Number(searchAmountMax.value));
  return list;
});

// ── 紐付け候補（未消込フォーム用・金額近い順）────────────────
const candidateReceipts = computed<ReceiptDoc[]>(() => {
  if (!selectedTx.value) return [];
  const targetAmt = selectedTx.value.amount;
  return [...receipts.value]
    .filter(r =>
      r.receipt_type === 'payment_proof' &&
      (r.reconciliation_status === 'unreconciled' || !r.reconciliation_status) &&
      (r.approval_status === 'approved' || r.approval_status === 'auto_approved')
    )
    .sort((a, b) => Math.abs(a.amount - targetAmt) - Math.abs(b.amount - targetAmt));
});

const candidateInvoices = computed<Invoice[]>(() => {
  if (!selectedTx.value) return [];
  const targetAmt = selectedTx.value.amount;
  return [...invoices.value]
    .filter(inv =>
      inv.document_type === 'received' &&
      (inv.reconciliation_status === 'unreconciled' || !inv.reconciliation_status) &&
      (inv.approval_status === 'approved' || inv.approval_status === 'auto_approved')
    )
    .sort((a, b) =>
      Math.abs(a.total_amount - targetAmt) - Math.abs(b.total_amount - targetAmt)
    );
});

// ── 勘定科目フィルタ ──────────────────────────────────────────
const filteredAccounts = computed(() =>
  accountSubject.value
    ? ACCOUNT_SUBJECTS.filter(s => s.includes(accountSubject.value))
    : ACCOUNT_SUBJECTS
);

// ── 消込済み行のクリック：消込記録と紐付き書類を取得 ─────────
const selectMatchedTx = async (tx: Transaction) => {
  if (selectedTx.value?.id === tx.id) {
    selectedTx.value = null;
    matchDetail.value = null;
    matchDocuments.value = [];
    return;
  }
  selectedTx.value = tx;
  matchDetail.value = null;
  matchDocuments.value = [];
  isLoadingDetail.value = true;

  try {
    // transaction_id で消込記録を直接検索（match_type 問わず）
    const results = await api.get<any[]>(`/matches?transaction_id=${tx.id}`);
    const found = results[0] ?? null;
    if (!found) return;
    matchDetail.value = found;

    // match_type に応じて書類を取得
    const docs: typeof matchDocuments.value = [];
    const docIds: string[] = found.document_ids ?? [];

    if (docIds.length > 0) {
      const matchType = found.match_type as string;
      for (const docId of docIds) {
        if (matchType === 'receipt') {
          try {
            const r = await api.get<any>(`/receipts/${docId}`);
            docs.push({ type: 'receipt', doc: r });
          } catch { /* skip */ }
        } else if (matchType === 'invoice' || matchType === 'reconciliation') {
          // invoices が先、見つからなければ receipts
          let pushed = false;
          try {
            const inv = await api.get<any>(`/invoices/${docId}`);
            docs.push({ type: 'invoice', doc: inv });
            pushed = true;
          } catch { /* not an invoice */ }
          if (!pushed) {
            try {
              const r = await api.get<any>(`/receipts/${docId}`);
              docs.push({ type: 'receipt', doc: r });
            } catch { /* skip */ }
          }
        } else {
          // 不明タイプは receipts → invoices の順で試行
          let pushed = false;
          try {
            const r = await api.get<any>(`/receipts/${docId}`);
            docs.push({ type: 'receipt', doc: r });
            pushed = true;
          } catch { /* not a receipt */ }
          if (!pushed) {
            try {
              const inv = await api.get<any>(`/invoices/${docId}`);
              docs.push({ type: 'invoice', doc: inv });
            } catch { /* skip */ }
          }
        }
      }
    }
    matchDocuments.value = docs;

    // 書類に紐づく監査ログを取得
    const events: any[] = [];
    for (const docId of found.document_ids ?? []) {
      try {
        const evs = await api.get<any[]>(`/approvals/events?document_id=${docId}`);
        events.push(...evs);
      } catch { /* skip */ }
    }
    events.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    auditEvents.value = events;
  } catch (e: any) {
    errorMessage.value = '消込情報の取得に失敗しました';
  } finally {
    isLoadingDetail.value = false;
  }
};

// ── 消込取り消し ──────────────────────────────────────────────
const handleCancelMatch = async () => {
  if (!matchDetail.value) return;
  if (!confirm('この消込を取り消しますか？取引は未消込に戻ります。')) return;
  isCancelling.value = true;
  try {
    await api.delete(`/matches/${matchDetail.value.id}`);
    successMessage.value = '消込を取り消しました';
    await fetchTransactions({ source_type: txTab.value });
    selectedTx.value = null;
    matchDetail.value = null;
    matchDocuments.value = [];
    auditEvents.value = [];
  } catch (e: any) {
    errorMessage.value = '消込の取り消しに失敗しました';
  } finally {
    isCancelling.value = false;
  }
};

// ── 未消込行のクリック ────────────────────────────────────────
const selectTx = (tx: Transaction) => {
  if (selectedTx.value?.id === tx.id) {
    selectedTx.value = null;
  } else {
    selectedTx.value = tx;
    accountSubject.value = '';
    memo.value = '';
    selectedDocumentId.value = null;
    selectedDocumentType.value = null;
  }
};

const selectAccount = (subject: string) => {
  accountSubject.value = subject;
  showAccountDropdown.value = false;
};

const toggleDocument = (id: string, type: 'receipt' | 'invoice') => {
  if (selectedDocumentId.value === id) {
    selectedDocumentId.value = null;
    selectedDocumentType.value = null;
  } else {
    selectedDocumentId.value = id;
    selectedDocumentType.value = type;
  }
};

const hideAccountDropdown = () => {
  setTimeout(() => { showAccountDropdown.value = false; }, 150);
};

// ── 消込確定 ──────────────────────────────────────────────────
const canSubmit = computed(() =>
  !!selectedTx.value && !!accountSubject.value && !isSubmitting.value
);

const handleSubmit = async () => {
  if (!canSubmit.value || !selectedTx.value) return;
  isSubmitting.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const docIds = selectedDocumentId.value ? [selectedDocumentId.value] : [];
    await api.post('/matches', {
      match_type: 'reconciliation',
      transaction_ids: [selectedTx.value.id],
      document_ids: docIds,
      account_subject: accountSubject.value,
      memo: memo.value,
      matched_by: 'manual',
    });
    successMessage.value = `¥${selectedTx.value.amount.toLocaleString()} の照合を確定しました`;
    await fetchTransactions({ source_type: txTab.value });
    selectedTx.value = null;
    accountSubject.value = '';
    memo.value = '';
    selectedDocumentId.value = null;
    selectedDocumentType.value = null;
  } catch (e: any) {
    errorMessage.value = e.message ?? '照合に失敗しました';
  } finally {
    isSubmitting.value = false;
  }
};

const switchTab = async (tab: 'bank' | 'card') => {
  txTab.value = tab;
  selectedTx.value = null;
  matchDetail.value = null;
  matchDocuments.value = [];
  await fetchTransactions({ source_type: tab });
};

const switchStatusTab = (tab: 'unmatched' | 'matched' | 'transferred') => {
  statusTab.value = tab;
  selectedTx.value = null;
  matchDetail.value = null;
  matchDocuments.value = [];
  auditEvents.value = [];
};

// ── 監査イベントのラベル・スタイル ───────────────────────────
const eventLabel = (action: string) => ({
  submitted: '提出', approved: '承認', rejected: '差戻し',
  returned: '返却', matched: '消込', unmatched: '消込取り消し',
}[action] ?? action);

const eventStyle = (action: string) => ({
  submitted:  'bg-blue-100 text-blue-700',
  approved:   'bg-emerald-100 text-emerald-700',
  rejected:   'bg-rose-100 text-rose-700',
  returned:   'bg-amber-100 text-amber-700',
  matched:    'bg-violet-100 text-violet-700',
  unmatched:  'bg-slate-100 text-slate-600',
}[action] ?? 'bg-slate-100 text-slate-600');

// ── 日時フォーマット ──────────────────────────────────────────
const fmtDatetime = (iso: string) => {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ja-JP', {
    year: 'numeric', month: 'long', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
};

onMounted(async () => {
  await Promise.all([
    fetchTransactions({ source_type: 'bank' }),
    fetchReceipts({ receipt_type: 'payment_proof', reconciliation_status: 'unreconciled' }),
    fetchInvoices({ document_type: 'received' }),
  ]);
});
</script>

<template>
  <div class="h-full flex flex-col bg-slate-50">
    <!-- Header -->
    <header class="bg-white border-b border-slate-200 px-8 py-6 shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 bg-indigo-100 text-indigo-600 rounded-xl flex items-center justify-center">
          <Link2 :size="20" />
        </div>
        <div>
          <h1 class="text-2xl font-bold text-slate-900 tracking-tight">支払照合</h1>
          <p class="text-sm text-slate-500 mt-0.5">銀行・カード明細に勘定科目を紐付けて消込します</p>
        </div>
      </div>
    </header>

    <!-- Flash messages -->
    <div v-if="successMessage" class="mx-8 mt-4 flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 px-4 py-3 rounded-lg text-sm font-medium">
      <Check :size="16" /> {{ successMessage }}
      <button @click="successMessage = ''" class="ml-auto text-emerald-500 hover:text-emerald-700"><X :size="14" /></button>
    </div>
    <div v-if="errorMessage" class="mx-8 mt-4 flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm font-medium">
      <AlertCircle :size="16" /> {{ errorMessage }}
      <button @click="errorMessage = ''" class="ml-auto text-red-500 hover:text-red-700"><X :size="14" /></button>
    </div>

    <!-- Main 2-pane layout -->
    <div class="flex flex-1 min-h-0 gap-0">

      <!-- ── 左ペイン：明細一覧 ── -->
      <div class="w-[420px] shrink-0 flex flex-col border-r border-slate-200 bg-white">

        <!-- source_type タブ -->
        <div class="flex bg-gray-100/70 p-1.5 m-4 rounded-xl gap-1">
          <button @click="switchTab('bank')"
            class="flex-1 py-2 rounded-lg text-sm font-bold transition-all"
            :class="txTab === 'bank' ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-800'"
          >銀行</button>
          <button @click="switchTab('card')"
            class="flex-1 py-2 rounded-lg text-sm font-bold transition-all"
            :class="txTab === 'card' ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-800'"
          >カード</button>
        </div>

        <!-- ステータスタブ -->
        <div class="flex gap-3 px-4 pb-3 border-b border-slate-100 text-sm">
          <button
            @click="switchStatusTab('unmatched')"
            class="pb-1 font-bold border-b-2 transition-colors"
            :class="statusTab === 'unmatched' ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-slate-400 hover:text-slate-600'"
          >未消込 <span class="ml-1 text-xs bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded-full">{{ unmatchedTxs.length }}</span></button>
          <button
            @click="switchStatusTab('matched')"
            class="pb-1 font-bold border-b-2 transition-colors"
            :class="statusTab === 'matched' ? 'border-slate-600 text-slate-600' : 'border-transparent text-slate-400 hover:text-slate-600'"
          >消込済み <span class="ml-1 text-xs bg-slate-200 text-slate-500 px-1.5 py-0.5 rounded-full">{{ matchedTxs.length }}</span></button>
          <button
            @click="switchStatusTab('transferred')"
            class="pb-1 font-bold border-b-2 transition-colors"
            :class="statusTab === 'transferred' ? 'border-amber-600 text-amber-600' : 'border-transparent text-slate-400 hover:text-slate-600'"
          >資金移動 <span class="ml-1 text-xs bg-amber-100 text-amber-600 px-1.5 py-0.5 rounded-full">{{ transferredTxs.length }}</span></button>
        </div>

        <!-- 検索バー -->
        <div class="px-4 py-3 border-b border-slate-100 space-y-2">
          <div class="relative">
            <Search :size="14" class="absolute left-2.5 top-2.5 text-slate-400" />
            <input
              v-model="searchQuery"
              type="text"
              placeholder="摘要で検索..."
              class="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none"
            />
          </div>
          <div class="grid grid-cols-2 gap-1.5">
            <input v-model="searchDateMin" type="date" class="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg outline-none" />
            <input v-model="searchDateMax" type="date" class="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg outline-none" />
            <input v-model.number="searchAmountMin" type="number" placeholder="金額 下限" class="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg outline-none" />
            <input v-model.number="searchAmountMax" type="number" placeholder="金額 上限" class="w-full px-2 py-1.5 text-xs border border-slate-200 rounded-lg outline-none" />
          </div>
          <div class="flex justify-end">
            <button v-if="hasSearch" @click="clearSearch" class="flex items-center gap-1 text-xs text-slate-400 hover:text-red-500 transition-colors">
              <X :size="11" /> クリア
            </button>
          </div>
        </div>

        <!-- 明細リスト -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="displayedTxs.length === 0" class="flex flex-col items-center justify-center h-full text-slate-400 py-16">
            <CheckCircle2 :size="40" class="mb-3 opacity-30" />
            <p class="text-sm">
              {{ statusTab === 'matched' ? '消込済みの明細はありません' :
                 statusTab === 'transferred' ? '資金移動の明細はありません' :
                 '未消込の明細はありません' }}
            </p>
          </div>
          <button
            v-for="tx in displayedTxs"
            :key="tx.id"
            @click="statusTab === 'unmatched' ? selectTx(tx) : selectMatchedTx(tx)"
            class="w-full text-left px-4 py-3.5 border-b border-slate-100 transition-colors cursor-pointer hover:bg-slate-50"
            :class="selectedTx?.id === tx.id
              ? (statusTab === 'transferred' ? 'bg-amber-50 border-l-2 border-l-amber-400'
               : statusTab === 'matched' ? 'bg-slate-50 border-l-2 border-l-slate-400'
               : 'bg-indigo-50 border-l-2 border-l-indigo-500')
              : ''"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-slate-800 truncate">{{ tx.description }}</p>
                <p class="text-xs text-slate-400 mt-0.5">{{ tx.transaction_date }} · {{ tx.account_name }}</p>
              </div>
              <div class="text-right shrink-0">
                <p class="text-sm font-bold" :class="tx.transaction_type === 'credit' ? 'text-emerald-600' : 'text-slate-800'">
                  {{ tx.transaction_type === 'credit' ? '+' : '' }}{{ formatCurrency(tx.amount) }}
                </p>
                <span v-if="statusTab === 'matched'" class="text-[10px] text-emerald-600 font-bold">消込済み</span>
                <span v-else-if="statusTab === 'transferred'" class="text-[10px] text-amber-600 font-bold">資金移動</span>
                <ChevronRight v-else :size="14" class="ml-auto mt-0.5 text-slate-300"
                  :class="selectedTx?.id === tx.id ? 'text-indigo-400' : ''" />
              </div>
            </div>
          </button>
        </div>
      </div>

      <!-- ── 右ペイン ── -->
      <div class="flex-1 overflow-y-auto p-8">

        <!-- 未選択 -->
        <div v-if="!selectedTx" class="h-full flex flex-col items-center justify-center text-slate-400">
          <Link2 :size="48" class="mb-4 opacity-20" />
          <p class="text-base font-medium text-slate-500">左の明細を選択してください</p>
          <p class="text-sm mt-1">
            {{ statusTab === 'matched' ? '消込内容を確認できます' :
               statusTab === 'transferred' ? '資金移動の詳細を確認できます' :
               '勘定科目と書類を紐付けて消込します' }}
          </p>
        </div>

        <!-- ローディング -->
        <div v-else-if="isLoadingDetail" class="h-full flex flex-col items-center justify-center text-slate-400">
          <Loader2 :size="32" class="animate-spin mb-3 text-indigo-400" />
          <p class="text-sm">消込情報を取得中...</p>
        </div>

        <!-- ===== 消込済み / 振替：閲覧モード ===== -->
        <div v-else-if="statusTab !== 'unmatched' && matchDetail" class="max-w-2xl mx-auto space-y-6">

          <!-- 明細概要カード -->
          <div class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <div class="flex items-center justify-between mb-3">
              <p class="text-xs font-bold text-slate-400 uppercase tracking-wider">
                {{ statusTab === 'transferred' ? '資金移動明細' : '消込済み明細' }}
              </p>
              <div class="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold"
                :class="statusTab === 'transferred' ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'">
                <CheckCircle2 :size="12" />{{ statusTab === 'transferred' ? '資金移動' : '消込済み' }}
              </div>
            </div>
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-lg font-bold text-slate-900">{{ selectedTx.description }}</p>
                <p class="text-sm text-slate-500 mt-1">{{ selectedTx.transaction_date }} · {{ selectedTx.account_name }}</p>
              </div>
              <div class="text-right shrink-0">
                <p class="text-2xl font-bold text-slate-900">{{ formatCurrency(selectedTx.amount) }}</p>
                <span class="text-xs px-2 py-0.5 rounded-full font-bold"
                  :class="selectedTx.transaction_type === 'credit' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'"
                >{{ selectedTx.transaction_type === 'credit' ? '入金' : '出金' }}</span>
              </div>
            </div>
          </div>

          <!-- 消込情報（読み取り専用） -->
          <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
            <div class="flex items-center justify-between mb-1">
              <div class="flex items-center gap-2 text-slate-400 text-xs font-bold uppercase tracking-wider">
                <Lock :size="12" />消込情報（読み取り専用）
              </div>
              <!-- 消込タイプバッジ -->
              <span class="text-[10px] font-bold px-2 py-0.5 rounded-full"
                :class="{
                  'bg-violet-100 text-violet-700': matchDetail.match_type === 'reconciliation',
                  'bg-blue-100 text-blue-700': matchDetail.match_type === 'invoice',
                  'bg-emerald-100 text-emerald-700': matchDetail.match_type === 'receipt',
                  'bg-amber-100 text-amber-700': matchDetail.match_type === 'transfer',
                  'bg-orange-100 text-orange-700': matchDetail.match_type === 'auto_expense',
                  'bg-slate-100 text-slate-600': !['reconciliation','invoice','receipt','transfer','auto_expense'].includes(matchDetail.match_type),
                }"
              >{{
                matchDetail.match_type === 'reconciliation' ? '支払照合' :
                matchDetail.match_type === 'invoice' ? '請求書消込' :
                matchDetail.match_type === 'receipt' ? '経費消込' :
                matchDetail.match_type === 'transfer' ? '現金振替' :
                matchDetail.match_type === 'auto_expense' ? '自動経費' :
                matchDetail.match_type
              }}</span>
            </div>

            <!-- 勘定科目（reconciliation のみ） -->
            <div v-if="matchDetail.account_subject">
              <label class="block text-sm font-bold text-slate-500 mb-1.5">勘定科目</label>
              <div class="px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold text-slate-800">
                {{ matchDetail.account_subject }}
              </div>
            </div>

            <!-- 摘要 / メモ -->
            <div v-if="matchDetail.memo || matchDetail.difference_treatment">
              <label class="block text-sm font-bold text-slate-500 mb-1.5">摘要</label>
              <div class="px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 min-h-[40px]">
                {{ matchDetail.memo || matchDetail.difference_treatment || '（なし）' }}
              </div>
            </div>

            <!-- 消込日時 -->
            <div>
              <label class="block text-sm font-bold text-slate-500 mb-1.5">消込日時</label>
              <div class="px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-600">
                {{ fmtDatetime(matchDetail.matched_at) }}
              </div>
            </div>
          </div>

          <!-- 紐付き書類（読み取り専用） -->
          <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
            <div class="flex items-center gap-2 text-sm font-bold text-slate-700 mb-4">
              <Lock :size="14" class="text-slate-400" />
              紐付き書類
            </div>

            <div v-if="matchDocuments.length === 0" class="text-sm text-slate-400 italic py-2">
              書類の紐付けなし
            </div>

            <div
              v-for="item in matchDocuments"
              :key="item.doc.id"
              class="flex items-center justify-between px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 mb-1.5"
            >
              <div class="flex items-center gap-2 min-w-0">
                <div class="w-7 h-7 rounded-lg bg-slate-200 text-slate-500 flex items-center justify-center shrink-0">
                  <Receipt v-if="item.type === 'receipt'" :size="14" />
                  <FileText v-else :size="14" />
                </div>
                <div class="min-w-0">
                  <p class="text-sm font-medium text-slate-700 truncate">
                    {{ item.type === 'receipt'
                      ? (item.doc.payee || '（発行元不明）')
                      : (item.doc.vendor_name || item.doc.client_name || '（取引先不明）') }}
                  </p>
                  <p class="text-xs text-slate-400">
                    {{ item.type === 'receipt' ? item.doc.date : (item.doc.issue_date || item.doc.due_date) }}
                    · {{ item.type === 'receipt' ? '支払証明' : '受取請求書' }}
                  </p>
                </div>
              </div>
              <p class="text-sm font-bold text-slate-700 shrink-0 ml-2">
                {{ formatCurrency(item.type === 'receipt' ? item.doc.amount : item.doc.total_amount) }}
              </p>
            </div>
          </div>

          <!-- 消込取り消しボタン（消込済みタブのみ） -->
          <div v-if="statusTab === 'matched'" class="flex justify-end">
            <button
              @click="handleCancelMatch"
              :disabled="isCancelling"
              class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-rose-200 text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-40"
            >
              <Loader2 v-if="isCancelling" :size="14" class="animate-spin" />
              <RotateCcw v-else :size="14" />
              消込を取り消す
            </button>
          </div>

          <!-- 監査タイムライン -->
          <div v-if="auditEvents.length > 0" class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
            <div class="flex items-center gap-2 text-sm font-bold text-slate-700 mb-4">
              <Clock :size="14" class="text-slate-400" />
              承認・消込履歴
            </div>
            <div class="relative">
              <div class="absolute left-3 top-0 bottom-0 w-px bg-slate-200" />
              <div v-for="(ev, i) in auditEvents" :key="i" class="relative flex items-start gap-4 mb-4 last:mb-0">
                <div class="w-6 h-6 rounded-full bg-white border-2 border-slate-200 flex items-center justify-center shrink-0 z-10">
                  <div class="w-2 h-2 rounded-full bg-slate-400" />
                </div>
                <div class="flex-1 min-w-0 pt-0.5">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span :class="['text-[11px] font-bold px-2 py-0.5 rounded-full', eventStyle(ev.action)]">
                      {{ eventLabel(ev.action) }}
                    </span>
                    <span class="text-xs text-slate-500">{{ fmtDatetime(ev.timestamp) }}</span>
                  </div>
                  <p v-if="ev.comment" class="text-xs text-slate-500 mt-1">{{ ev.comment }}</p>
                </div>
              </div>
            </div>
          </div>

        </div>

        <!-- 消込済み/振替だが match 見つからない場合 -->
        <div v-else-if="statusTab !== 'unmatched' && !isLoadingDetail" class="h-full flex flex-col items-center justify-center text-slate-400">
          <AlertCircle :size="32" class="mb-3 opacity-40" />
          <p class="text-sm">この明細の消込情報が見つかりません</p>
        </div>

        <!-- ===== 未消込：登録フォーム ===== -->
        <div v-else-if="statusTab === 'unmatched' && selectedTx" class="max-w-2xl mx-auto space-y-6">

          <!-- 明細概要カード -->
          <div class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
            <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">選択中の明細</p>
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-lg font-bold text-slate-900">{{ selectedTx.description }}</p>
                <p class="text-sm text-slate-500 mt-1">{{ selectedTx.transaction_date }} · {{ selectedTx.account_name }}</p>
              </div>
              <div class="text-right shrink-0">
                <p class="text-2xl font-bold text-slate-900">{{ formatCurrency(selectedTx.amount) }}</p>
                <span class="text-xs px-2 py-0.5 rounded-full font-bold"
                  :class="selectedTx.transaction_type === 'credit' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'"
                >{{ selectedTx.transaction_type === 'credit' ? '入金' : '出金' }}</span>
              </div>
            </div>
          </div>

          <!-- フォーム -->
          <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">

            <!-- 勘定科目（必須） -->
            <div>
              <label class="block text-sm font-bold text-slate-700 mb-1.5">
                勘定科目 <span class="text-red-500">*</span>
              </label>
              <div class="relative">
                <input
                  v-model="accountSubject"
                  type="text"
                  placeholder="勘定科目を入力または選択..."
                  class="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none"
                  @focus="showAccountDropdown = true"
                  @blur="hideAccountDropdown"
                />
                <div
                  v-if="showAccountDropdown && filteredAccounts.length"
                  class="absolute z-20 w-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg max-h-52 overflow-y-auto"
                >
                  <button
                    v-for="s in filteredAccounts"
                    :key="s"
                    type="button"
                    @mousedown.prevent="selectAccount(s)"
                    class="w-full text-left px-4 py-2.5 text-sm hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                    :class="accountSubject === s ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-slate-700'"
                  >{{ s }}</button>
                </div>
              </div>
            </div>

            <!-- 摘要（任意） -->
            <div>
              <label class="block text-sm font-bold text-slate-700 mb-1.5">摘要 <span class="text-slate-400 font-normal text-xs ml-1">任意</span></label>
              <input
                v-model="memo"
                type="text"
                placeholder="補足メモを入力..."
                class="w-full px-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none"
              />
            </div>
          </div>

          <!-- 書類を紐付ける（任意） -->
          <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
            <p class="text-sm font-bold text-slate-700 mb-4">
              書類を紐付ける <span class="text-slate-400 font-normal text-xs ml-1">任意 · 1件まで</span>
            </p>

            <!-- 支払証明領収書 -->
            <div class="mb-4">
              <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">支払証明（領収書）</p>
              <div v-if="candidateReceipts.length === 0" class="text-sm text-slate-400 italic py-2">該当する支払証明はありません</div>
              <div
                v-for="r in candidateReceipts.slice(0, 5)"
                :key="r.id"
                @click="toggleDocument(r.id, 'receipt')"
                class="flex items-center justify-between px-3 py-2.5 rounded-lg border cursor-pointer transition-all mb-1.5"
                :class="selectedDocumentId === r.id
                  ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-400'
                  : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50'"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <div class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                    :class="selectedDocumentId === r.id ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-400'">
                    <Receipt :size="14" />
                  </div>
                  <div class="min-w-0">
                    <p class="text-sm font-medium text-slate-800 truncate">{{ r.payee || '（発行元不明）' }}</p>
                    <p class="text-xs text-slate-400">{{ r.date }}</p>
                  </div>
                </div>
                <div class="text-right shrink-0 ml-2">
                  <p class="text-sm font-bold text-slate-700">{{ formatCurrency(r.amount) }}</p>
                  <div v-if="selectedDocumentId === r.id" class="flex justify-end mt-0.5">
                    <CheckCircle2 :size="14" class="text-indigo-500" />
                  </div>
                </div>
              </div>
            </div>

            <!-- 受取請求書 -->
            <div>
              <p class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">受取請求書</p>
              <div v-if="candidateInvoices.length === 0" class="text-sm text-slate-400 italic py-2">未消込の受取請求書はありません</div>
              <div
                v-for="inv in candidateInvoices.slice(0, 5)"
                :key="inv.id"
                @click="toggleDocument(inv.id, 'invoice')"
                class="flex items-center justify-between px-3 py-2.5 rounded-lg border cursor-pointer transition-all mb-1.5"
                :class="selectedDocumentId === inv.id
                  ? 'border-indigo-400 bg-indigo-50 ring-1 ring-indigo-400'
                  : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50'"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <div class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                    :class="selectedDocumentId === inv.id ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-400'">
                    <FileText :size="14" />
                  </div>
                  <div class="min-w-0">
                    <p class="text-sm font-medium text-slate-800 truncate">{{ inv.vendor_name || inv.client_name || '（取引先不明）' }}</p>
                    <p class="text-xs text-slate-400">{{ inv.issue_date || inv.due_date }}</p>
                  </div>
                </div>
                <div class="text-right shrink-0 ml-2">
                  <p class="text-sm font-bold text-slate-700">{{ formatCurrency(inv.total_amount) }}</p>
                  <div v-if="selectedDocumentId === inv.id" class="flex justify-end mt-0.5">
                    <CheckCircle2 :size="14" class="text-indigo-500" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 確定ボタン -->
          <div class="flex justify-end">
            <button
              @click="handleSubmit"
              :disabled="!canSubmit"
              class="flex items-center gap-2 px-8 py-3 rounded-xl font-bold text-sm transition-all shadow-sm"
              :class="canSubmit
                ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-indigo-200'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'"
            >
              <Loader2 v-if="isSubmitting" :size="18" class="animate-spin" />
              <CheckCircle2 v-else :size="18" />
              消込を確定する
            </button>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>
