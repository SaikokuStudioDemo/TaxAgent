<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import {
    Search,
    Link2,
    Building2,
    FileText,
    CheckCircle,
    AlertCircle,
    ArrowRightLeft,
    MonitorSmartphone,
    ChevronDown,
    ChevronUp
} from 'lucide-vue-next';
import { useInvoices, type Invoice } from '@/composables/useInvoices';
import { useDocumentMatching, type MatchableDocument } from '@/composables/useDocumentMatching';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import { MATCHING_STYLES } from '@/constants/matchingStyles';

// ── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{ mode: 'income' | 'payment' }>();

// ── Mode config ──────────────────────────────────────────────────────────────
// All Tailwind class strings must appear as complete literals for the JIT scanner
const CONFIGS = {
    income: {
        title: '入金消込',
        description: '発行した請求書データと、銀行口座等への入金データを突合（マッチング）します。',
        documentType: 'issued' as const,
        txFilter: 'credit' as const,
        txLabel: '入金',
        txDataLabel: '入金データ',
        txMatchLabel: '入金明細',
        docLabel: '作成データ (請求書)',
        docMatchLabel: '請求書',
        dueLabel: '期日',
        displayStatusDefault: 'sent' as const,
        docHeaderBg:    'bg-blue-50/50',
        docIconColor:   'text-blue-700',
        docBadge:       'bg-blue-100 text-blue-700',
        docSearch:      'border-blue-200 focus:ring-blue-500 focus:border-blue-500 bg-blue-50/30',
        docScrollBg:    'bg-blue-50/10',
        docCardSel:     'border-blue-500 ring-2 ring-blue-500 shadow-sm bg-blue-50/30',
        docBar:         'bg-blue-500',
        docCheck:       'bg-blue-600',
        docChevron:     'hover:text-blue-600 hover:bg-blue-50',
        centerIcon:     'text-blue-500',
        centerShadow:   'shadow-blue-500/10',
        txCardSel:      'border-blue-500 ring-2 ring-blue-500 shadow-sm bg-blue-50/30',
        txBar:          'bg-blue-500',
        txCheck:        'bg-blue-600',
        txSearch:       'focus:ring-blue-500 focus:border-blue-500',
        txBankBadge:    'bg-emerald-50 text-emerald-700 border-emerald-200',
    },
    payment: {
        title: '支払消込',
        description: '受領した請求書データと、銀行口座からの出金データを突合（マッチング）します。',
        documentType: 'received' as const,
        txFilter: 'debit' as const,
        txLabel: '出金',
        txDataLabel: '出金データ',
        txMatchLabel: '出金明細',
        docLabel: '受領請求書',
        docMatchLabel: '受領請求書',
        dueLabel: '支払期限',
        displayStatusDefault: 'unpaid' as const,
        docHeaderBg:    'bg-orange-50/50',
        docIconColor:   'text-orange-700',
        docBadge:       'bg-orange-100 text-orange-700',
        docSearch:      'border-orange-200 focus:ring-orange-500 focus:border-orange-500 bg-orange-50/30',
        docScrollBg:    'bg-orange-50/10',
        docCardSel:     'border-orange-500 ring-2 ring-orange-500 shadow-sm bg-orange-50/30',
        docBar:         'bg-orange-500',
        docCheck:       'bg-orange-600',
        docChevron:     'hover:text-orange-600 hover:bg-orange-50',
        centerIcon:     'text-orange-500',
        centerShadow:   'shadow-orange-500/10',
        txCardSel:      'border-orange-500 ring-2 ring-orange-500 shadow-sm bg-orange-50/30',
        txBar:          'bg-orange-500',
        txCheck:        'bg-orange-600',
        txSearch:       'focus:ring-orange-500 focus:border-orange-500',
        txBankBadge:    'bg-rose-50 text-rose-700 border-rose-200',
    },
} as const;

const cfg = computed(() => CONFIGS[props.mode]);

// ── Data ─────────────────────────────────────────────────────────────────────
interface MatchingInvoice extends Invoice, MatchableDocument {
    displayStatus: 'sent' | 'overdue' | 'unpaid';
}

const { invoices: apiInvoices, fetchInvoices } = useInvoices();
const rawInvoices = ref<MatchingInvoice[]>([]);

const mapInvoice = (inv: Invoice): MatchingInvoice => {
    const isOverdue = inv.due_date && new Date(inv.due_date) < new Date();
    return { ...inv, matched: false, displayStatus: isOverdue ? 'overdue' : cfg.value.displayStatusDefault };
};

const fetchAndMapInvoices = async () => {
    await fetchInvoices({ document_type: cfg.value.documentType });
    rawInvoices.value = apiInvoices.value.map(mapInvoice);
};

// ── Composable ───────────────────────────────────────────────────────────────
// txTypeFilter は computed なので reactive（mode 変更に追従）
const txTypeFilter = computed(() => cfg.value.txFilter);

const {
    activeTab,
    documentSearch: invoiceSearch,
    transactionSearch,
    selectedDocumentIds: selectedInvoiceIds,
    selectedTransactionIds,
    selectedCandidateIds,
    showConfirmMatch,
    confirmMatchResolve,
    confirmMatchAmount,
    unmatchedTransactions,
    unmatchedDocuments: unmatchedInvoices,
    selectedTransactionSum,
    selectedDocumentSum: selectedInvoiceSum,
    matchingDifference,
    suggestedDocumentIds: suggestedInvoiceIds,
    candidatePairs: baseCandidatePairs,
    matchedPairs: baseMatchedPairs,
    loadData,
    selectTransaction,
    selectDocument: selectInvoice,
    toggleCandidate,
    toggleAllCandidates,
    handleMatch,
    handleBulkMatch,
    revertToUnmatched: unmatch,
} = useDocumentMatching({
    fetchDocumentsFn: fetchAndMapInvoices,
    documents: rawInvoices,
    matchType: 'invoice',
    getAmount: i => i.total_amount,
    getDescription: i => [i.client_name, i.vendor_name, i.invoice_number, i.total_amount?.toString()].filter(Boolean).join(' '),
    transactionTypeFilter: txTypeFilter,
});

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(loadData);

// mode 切り替え時（同一コンポーネント再利用）にデータを再取得
watch(() => props.mode, async () => {
    rawInvoices.value = [];
    await loadData();
});

// ── Local state ───────────────────────────────────────────────────────────────
const expandedInvoiceIds = ref<string[]>([]);

const toggleInvoiceExpansion = (id: string) => {
    const idx = expandedInvoiceIds.value.indexOf(id);
    if (idx > -1) expandedInvoiceIds.value.splice(idx, 1);
    else expandedInvoiceIds.value.push(id);
};

// ── Local computed ────────────────────────────────────────────────────────────
const candidatePairs = computed(() =>
    baseCandidatePairs.value.map(p => ({ ...p, invoice: p.document as MatchingInvoice }))
);

const matchedFromDB = computed(() =>
    baseMatchedPairs.value.map(p => ({
        ...p,
        invoice: p.document as MatchingInvoice,
        tx: p.transaction,
        timestamp: p.matchedAt
            ? new Date(p.matchedAt).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
            : '',
    }))
);
</script>

<template>
  <div class="h-full flex flex-col bg-slate-50">
    <header class="bg-white border-b border-gray-200 px-8 py-6 shrink-0 z-10">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">{{ cfg.title }}</h1>
        <p class="text-sm text-gray-500 mt-1">{{ cfg.description }}</p>
      </div>

      <div :class="['mt-6', MATCHING_STYLES.tabContainer]">
        <button
          @click="activeTab = 'unmatched'"
          :class="[MATCHING_STYLES.tabBase, 'flex items-center justify-center gap-1.5', activeTab === 'unmatched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]"
        >
          未結合 ({{ unmatchedInvoices.length }})
        </button>

        <button
          @click="activeTab = 'candidates'"
          :class="[MATCHING_STYLES.tabBase, 'flex items-center justify-center gap-1.5 relative', activeTab === 'candidates' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]"
        >
          <div v-if="candidatePairs.length > 0" class="absolute top-2 right-4 md:right-auto md:-top-1 md:-right-1 w-3 h-3 bg-red-500 rounded-full border-2 border-white animate-pulse"></div>
          <span class="mr-1">✨</span> 自動結合候補 ({{ candidatePairs.length }})
        </button>

        <button
          @click="activeTab = 'matched'"
          :class="[MATCHING_STYLES.tabBase, 'flex items-center justify-center gap-1.5', activeTab === 'matched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]"
        >
          <CheckCircle v-if="matchedFromDB.length > 0" class="h-4 w-4 text-emerald-500" />
          結合済 ({{ matchedFromDB.length }})
        </button>
      </div>
    </header>

    <main class="flex-1 overflow-hidden p-8">

      <!-- ── Unmatched Tab ── -->
      <template v-if="activeTab === 'unmatched'">

        <!-- Action Banner -->
        <div class="h-[72px] mb-6 relative">
          <!-- 1. Exact match -->
          <div v-if="selectedTransactionIds.length > 0 && selectedInvoiceIds.length > 0 && matchingDifference === 0"
               :class="['absolute inset-0 z-20 flex items-center justify-between', MATCHING_STYLES.guidanceBarActive]">
            <div class="flex items-center gap-3">
              <div class="bg-blue-500 rounded-full p-2"><Link2 class="h-5 w-5 text-white" /></div>
              <div>
                <div class="flex items-center gap-2">
                  <p class="font-bold">結合準備完了</p>
                  <span class="text-[10px] font-bold bg-green-400 text-green-900 px-2 py-0.5 rounded-full shadow-sm">金額ピタリ一致</span>
                </div>
                <p class="text-blue-100 text-xs mt-0.5">対象: {{ cfg.txLabel }} {{ selectedTransactionIds.length }}件 × 請求書 {{ selectedInvoiceIds.length }}件</p>
                <div class="text-[11px] font-medium text-blue-200 mt-1 flex items-center gap-2">
                  <span>{{ cfg.txLabel }}: ¥{{ formatAmount(selectedTransactionSum) }}</span>
                  <span>-</span>
                  <span>請求: ¥{{ formatAmount(selectedInvoiceSum) }}</span>
                  <span class="font-bold text-white">= 差額: ¥0</span>
                </div>
              </div>
            </div>
            <button @click="handleMatch" :class="MATCHING_STYLES.matchButton">
              <CheckCircle class="w-4 h-4" /> この内容で結合する
            </button>
          </div>

          <!-- 2. Discrepancy -->
          <div v-else-if="selectedTransactionIds.length > 0 && selectedInvoiceIds.length > 0 && matchingDifference !== 0"
               :class="['absolute inset-0 z-20 flex items-center justify-between', MATCHING_STYLES.guidanceBarActive]">
            <div class="flex items-center gap-3">
              <div class="bg-amber-500 rounded-full p-2"><AlertCircle class="h-5 w-5 text-amber-900" /></div>
              <div>
                <div class="flex items-center gap-2">
                  <p class="font-bold">金額の確認が必要です</p>
                  <span class="text-[10px] font-bold bg-amber-400 text-amber-900 px-2 py-0.5 rounded-full shadow-sm">差額あり</span>
                </div>
                <p class="text-gray-300 text-xs mt-0.5">対象: {{ cfg.txLabel }} {{ selectedTransactionIds.length }}件 × 請求書 {{ selectedInvoiceIds.length }}件</p>
                <div class="text-[11px] font-medium text-gray-400 mt-1 flex items-center gap-2">
                  <span>{{ cfg.txLabel }}: ¥{{ formatAmount(selectedTransactionSum) }}</span>
                  <span>-</span>
                  <span>請求: ¥{{ formatAmount(selectedInvoiceSum) }}</span>
                  <span class="font-bold text-amber-400">= 差額: ¥{{ formatAmount(matchingDifference) }}</span>
                </div>
              </div>
            </div>
            <button @click="handleMatch" class="bg-amber-500 text-amber-950 font-bold px-6 py-2.5 rounded-lg shadow-sm hover:bg-amber-400 transition-colors flex items-center gap-2">
              <Link2 class="w-4 h-4" /> 差額を許容して強制結合
            </button>
          </div>

          <!-- 3. Guidance -->
          <div v-else-if="selectedTransactionIds.length > 0 || selectedInvoiceIds.length > 0"
               :class="['absolute inset-0 z-10', MATCHING_STYLES.guidanceBarWarning]">
            <div class="bg-blue-100 rounded-full p-1.5"><ArrowRightLeft class="h-4 w-4 text-blue-600" /></div>
            <div>
              <p class="font-bold text-sm">もう一方のリストから対応するデータを選択してください。</p>
              <p class="text-[11px] text-blue-600 font-medium">
                現在選択中:
                {{ selectedTransactionIds.length > 0 ? `${cfg.txDataLabel} ${selectedTransactionIds.length}件 (¥${formatAmount(selectedTransactionSum)})` : '' }}
                {{ selectedInvoiceIds.length > 0 ? `${cfg.docMatchLabel} ${selectedInvoiceIds.length}件 (¥${formatAmount(selectedInvoiceSum)})` : '' }}
              </p>
            </div>
          </div>

          <!-- 4. Default -->
          <div v-else :class="['absolute inset-0', MATCHING_STYLES.guidanceBarDefault]">
            <Link2 class="h-5 w-5 opacity-50" />
            <p class="font-medium text-sm">結合を開始するには、左の{{ cfg.docMatchLabel }}リストまたは右の明細リストから対象を選択してください。</p>
          </div>
        </div>

        <!-- Split Layout -->
        <div class="flex h-[calc(100%-96px)] flex-col lg:flex-row gap-6">

          <!-- Left: Invoices -->
          <div :class="MATCHING_STYLES.paneBase">
            <div :class="[MATCHING_STYLES.paneHeaderBase, cfg.docHeaderBg]">
              <div class="flex items-center gap-2">
                <FileText class="h-5 w-5" :class="cfg.docIconColor" />
                <h2 class="font-bold text-gray-800 text-base">{{ cfg.docLabel }}</h2>
                <span class="text-xs font-bold px-2 py-0.5 rounded-full" :class="cfg.docBadge">{{ unmatchedInvoices.length }}</span>
              </div>
            </div>

            <div class="p-3 border-b border-gray-100 shrink-0">
              <div class="relative">
                <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input v-model="invoiceSearch" type="text" :placeholder="`${cfg.docMatchLabel}・請求書番号で検索...`"
                  :class="MATCHING_STYLES.searchInput" />
              </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 relative" :class="cfg.docScrollBg">
              <div
                v-for="inv in unmatchedInvoices" :key="inv.id"
                @click="selectInvoice(inv.id)"
                :class="[
                  MATCHING_STYLES.cardBase, 'flex flex-col justify-between',
                  selectedInvoiceIds.includes(inv.id) ? MATCHING_STYLES.cardSelected : '',
                  suggestedInvoiceIds.includes(inv.id) && !selectedInvoiceIds.includes(inv.id) ? MATCHING_STYLES.cardSuggested : ''
                ]"
              >
                <div v-if="selectedInvoiceIds.includes(inv.id)" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
                <div v-if="selectedInvoiceIds.includes(inv.id)" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                  <CheckCircle class="w-4 h-4" />
                </div>
                <div v-if="suggestedInvoiceIds.includes(inv.id) && !selectedInvoiceIds.includes(inv.id)"
                     class="absolute top-0 right-0 bg-amber-400 text-amber-900 text-[10px] font-bold px-2 py-1 rounded-bl-lg shadow-sm flex items-center shadow-amber-500/20">
                  ✨ 金額一致 <span class="ml-2 font-black bg-amber-600 text-amber-50 px-1.5 py-0.5 rounded text-[9px] animate-pulse">クリックして一致を確認 ▸</span>
                </div>

                <div class="flex justify-between items-start mb-2">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-50 text-gray-600 border-gray-200">{{ inv.id }}</span>
                    <span v-if="inv.displayStatus === 'overdue'" class="text-[10px] font-bold text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">期限超過</span>
                  </div>
                  <p class="text-lg font-bold tracking-tight text-gray-900 whitespace-nowrap ml-4">¥{{ formatAmount(inv.total_amount) }}</p>
                </div>

                <div class="flex justify-between items-end">
                  <div class="min-w-0 pr-4">
                    <p class="text-sm font-bold text-gray-900 leading-tight truncate w-[220px]" :title="inv.client_name">{{ inv.client_name }}</p>
                    <p class="text-[11px] text-gray-500 mt-1 font-medium">{{ cfg.dueLabel }}: {{ inv.due_date }}</p>
                  </div>
                  <div class="shrink-0 flex flex-col items-end gap-2">
                    <button
                      v-if="inv.line_items && inv.line_items.length > 0"
                      @click.stop="toggleInvoiceExpansion(inv.id)"
                      class="text-gray-400 p-1 rounded transition-colors flex items-center justify-center bg-gray-50 border border-gray-200"
                      :class="cfg.docChevron"
                    >
                      <ChevronUp v-if="expandedInvoiceIds.includes(inv.id)" class="w-4 h-4" />
                      <ChevronDown v-else class="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <!-- Line Items Accordion -->
                <div v-if="expandedInvoiceIds.includes(inv.id) && inv.line_items && inv.line_items.length > 0"
                     class="mt-4 pt-3 border-t border-gray-100/50 bg-gray-50/50 -mx-2 px-2 rounded-lg">
                  <p class="text-[11px] font-bold text-gray-500 mb-2 flex items-center">
                    <FileText class="w-3 h-3 mr-1" /> 請求明細 ({{ inv.line_items.length }}件)
                  </p>
                  <div class="space-y-2">
                    <div v-for="(item, idx) in inv.line_items" :key="idx"
                         class="flex items-start justify-between text-xs bg-white p-2 rounded border border-gray-100 shadow-sm">
                      <div class="break-words w-2/3 pr-2">
                        <div class="font-bold text-gray-700 mb-0.5">{{ item.description }}</div>
                        <div class="text-[10px] bg-gray-100 text-gray-600 px-1 py-0.5 rounded inline-block">{{ item.category }}</div>
                      </div>
                      <div class="font-bold text-gray-900 whitespace-nowrap mt-0.5">¥{{ formatAmount(item.amount) }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Center Divider -->
          <div class="hidden lg:flex flex-col items-center justify-center -mx-2 z-10 shrink-0">
            <div :class="MATCHING_STYLES.centerIcon">
              <Link2 class="h-5 w-5" :class="cfg.centerIcon" />
            </div>
          </div>

          <!-- Right: Transactions -->
          <div :class="MATCHING_STYLES.paneBase">
            <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-slate-50']">
              <div class="flex items-center gap-2">
                <Building2 class="text-slate-600 h-5 w-5" />
                <h2 class="font-bold text-gray-800 text-base">{{ cfg.txDataLabel }}</h2>
                <span class="bg-slate-200 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedTransactions.length }}</span>
              </div>
            </div>

            <div class="p-3 border-b border-gray-100 shrink-0">
              <div class="relative">
                <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input v-model="transactionSearch" type="text" placeholder="振込名義・金額で検索..."
                  :class="MATCHING_STYLES.searchInput" />
              </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50/30">
              <div
                v-for="t in unmatchedTransactions" :key="t.id"
                @click="selectTransaction(t.id)"
                :class="[MATCHING_STYLES.cardBase, 'flex flex-col justify-between', selectedTransactionIds.includes(t.id) ? MATCHING_STYLES.cardSelected : '']"
              >
                <div v-if="selectedTransactionIds.includes(t.id)" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
                <div v-if="selectedTransactionIds.includes(t.id)" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                  <CheckCircle class="w-4 h-4" />
                </div>
                <div class="flex justify-between items-start mb-2">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-medium px-2 py-0.5 rounded-full border"
                          :class="t.type === 'card' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : cfg.txBankBadge">
                      <component :is="t.type === 'card' ? MonitorSmartphone : Building2" class="w-3 h-3 inline mr-1" />
                      {{ t.type === 'card' ? '決済代行' : '銀行振込' }}
                    </span>
                    <span class="text-xs text-gray-500 font-medium">{{ t.date }}</span>
                  </div>
                  <p class="text-lg font-bold tracking-tight text-gray-900 whitespace-nowrap">¥{{ formatAmount(t.amount) }}</p>
                </div>
                <div class="pr-8">
                  <p class="text-sm font-bold text-gray-800 leading-tight">{{ t.description }}</p>
                </div>
              </div>
            </div>
          </div>

        </div>
      </template>

      <!-- ── Candidates Tab ── -->
      <template v-else-if="activeTab === 'candidates'">
        <div class="h-full relative flex flex-col">
          <div class="flex-1 overflow-y-auto pb-24 space-y-4">
            <div v-for="pair in candidatePairs" :key="pair.transaction.id"
                 @click="toggleCandidate(pair.transaction.id)"
                 class="bg-indigo-50/30 rounded-xl border transition-shadow relative overflow-hidden flex items-center cursor-pointer hover:shadow-md"
                 :class="selectedCandidateIds.includes(pair.transaction.id) ? 'border-indigo-400 ring-1 ring-indigo-400 shadow-sm bg-indigo-50/60' : 'border-indigo-200'"
            >
              <div class="pl-4 pr-2 py-6 shrink-0 flex items-center justify-center">
                <div class="w-5 h-5 rounded border border-indigo-400 flex items-center justify-center transition-colors"
                     :class="selectedCandidateIds.includes(pair.transaction.id) ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-white'">
                  <CheckCircle v-if="selectedCandidateIds.includes(pair.transaction.id)" class="w-4 h-4" />
                </div>
              </div>
              <div class="flex-1 flex flex-col md:flex-row p-4 gap-4 items-center pl-2">
                <div class="flex-1 bg-white border border-gray-200 rounded-lg p-3 w-full shadow-sm">
                  <div class="text-[10px] text-gray-400 font-bold mb-1 uppercase tracking-wider flex items-center gap-1">
                    <FileText class="w-3 h-3" /> {{ cfg.docMatchLabel }}
                  </div>
                  <p class="text-sm font-bold text-gray-900 truncate mb-1">{{ pair.invoice.client_name }}</p>
                  <div class="flex justify-between items-center text-xs text-gray-500">
                    <span>{{ pair.invoice.id }}</span>
                    <span class="font-bold text-gray-900">¥{{ formatAmount(pair.invoice.total_amount) }}</span>
                  </div>
                </div>
                <ArrowRightLeft class="text-indigo-300 shrink-0 w-5 h-5 hidden md:block" />
                <div class="flex-1 bg-white border border-gray-200 rounded-lg p-3 w-full shadow-sm">
                  <div class="text-[10px] text-gray-400 font-bold mb-1 uppercase tracking-wider flex items-center gap-1">
                    <Building2 class="w-3 h-3" /> {{ cfg.txMatchLabel }}
                  </div>
                  <p class="text-sm font-bold text-gray-900 truncate mb-1">{{ pair.transaction.description }}</p>
                  <div class="flex justify-between items-center text-xs text-gray-500">
                    <span>{{ pair.transaction.date }}</span>
                    <span class="font-bold text-gray-900">¥{{ formatAmount(pair.transaction.amount) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="candidatePairs.length > 0"
               class="absolute bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4 shadow-[0_-10px_30px_rgba(0,0,0,0.05)] flex items-center justify-between z-10 rounded-t-xl">
            <div class="flex items-center gap-4">
              <button @click="toggleAllCandidates" class="text-sm font-bold text-indigo-600 hover:text-indigo-800 transition-colors px-2 py-1 rounded hover:bg-indigo-50">
                {{ selectedCandidateIds.length === candidatePairs.length ? '全選択を解除' : 'すべて選択' }}
              </button>
              <span class="text-sm font-medium text-gray-600 border-l border-gray-300 pl-4">
                <span class="font-bold text-gray-900">{{ selectedCandidateIds.length }}件</span> を選択中
              </span>
            </div>
            <button @click="handleBulkMatch" :disabled="selectedCandidateIds.length === 0"
                    class="bg-indigo-600 text-white font-bold px-8 py-2.5 rounded-lg shadow-sm hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
              <CheckCircle class="w-5 h-5" /> 選択項目を消込する
            </button>
          </div>
        </div>
      </template>

      <!-- ── Matched Tab ── -->
      <template v-else-if="activeTab === 'matched'">
        <div class="h-full overflow-y-auto space-y-3 pb-8">
          <div v-if="matchedFromDB.length === 0" class="flex flex-col items-center justify-center py-20 bg-white rounded-xl border border-gray-200 shadow-sm text-gray-400 w-full h-full">
            <CheckCircle class="w-16 h-16 mb-4 text-gray-200" />
            <p class="font-medium">消込済データはありません</p>
          </div>

          <div v-for="item in matchedFromDB" :key="item.matchId"
               class="bg-emerald-50/30 border border-emerald-200 rounded-xl p-4 flex items-center justify-between group shadow-sm">
            <div class="flex items-center gap-6 flex-1">
              <div class="bg-emerald-100 text-emerald-700 p-2 rounded-full shrink-0">
                <CheckCircle class="w-5 h-5" />
              </div>
              <div class="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="flex flex-col">
                  <span class="text-[10px] text-gray-500 font-bold mb-0.5">{{ cfg.docMatchLabel }}</span>
                  <span class="text-sm font-bold text-gray-900">{{ item.invoice.client_name }}</span>
                  <span class="text-[11px] text-gray-500">{{ item.invoice.id }}</span>
                </div>
                <div class="flex flex-col border-l border-emerald-200/50 pl-4">
                  <span class="text-[10px] text-gray-500 font-bold mb-0.5">{{ cfg.txDataLabel }}</span>
                  <span class="text-sm font-bold text-gray-900">{{ item.tx.description }}</span>
                  <span class="text-[11px] text-gray-500">{{ item.tx.date }}</span>
                </div>
              </div>
              <div class="text-right px-8 border-l border-emerald-200/50">
                <span class="block text-[10px] text-gray-500 font-bold mb-0.5">消込金額</span>
                <span class="text-xl font-black text-gray-900 tracking-tight">¥{{ formatAmount(item.invoice.total_amount) }}</span>
              </div>
            </div>

            <div class="shrink-0 flex items-center gap-4">
              <span class="text-[11px] text-gray-400 font-medium">{{ item.timestamp }} に消込</span>
              <button @click="unmatch(item.invoice.id, item.tx.id)"
                      class="px-3 py-1.5 bg-white border border-gray-300 rounded text-xs font-bold text-gray-600 hover:text-red-600 hover:border-red-300 hover:bg-red-50 transition-colors shadow-sm">
                未消込に戻す
              </button>
              <button class="text-blue-600 hover:text-blue-800 text-xs font-bold bg-blue-50 px-3 py-1.5 rounded transition-colors shadow-sm">
                仕訳を確認
              </button>
            </div>
          </div>
        </div>
      </template>

    </main>

    <!-- Confirmation Modal -->
    <div v-if="showConfirmMatch" class="fixed inset-0 z-[110] flex items-center justify-center p-4 text-left">
      <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="confirmMatchResolve?.(false)"></div>
      <div class="bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden w-full max-w-sm relative z-10 p-6 text-center animate-in fade-in zoom-in-95 duration-200">
        <div class="w-12 h-12 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <AlertCircle class="w-6 h-6 text-amber-600" />
        </div>
        <h3 class="text-lg font-bold text-gray-900 mb-2">差額の確認</h3>
        <p class="text-sm text-gray-500 mb-6 font-medium leading-relaxed">
          差額が <span class="text-amber-600 font-bold">¥{{ formatAmount(confirmMatchAmount) }}</span> あります。<br>
          このまま結合を続行してもよろしいですか？<br>
          <span class="text-[11px] mt-2 block">※差額は振込手数料等の雑損失として処理されます。</span>
        </p>
        <div class="flex items-center gap-3">
          <button @click="confirmMatchResolve?.(false)" class="flex-1 px-4 py-2 border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg text-sm font-bold transition-colors">
            キャンセル
          </button>
          <button @click="confirmMatchResolve?.(true)" class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold transition-colors shadow-sm shadow-blue-600/20">
            結合する
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
