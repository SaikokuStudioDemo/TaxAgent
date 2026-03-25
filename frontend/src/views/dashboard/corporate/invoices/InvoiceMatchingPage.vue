<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
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
import { useInvoices } from '@/composables/useInvoices';
import { useTransactions } from '@/composables/useTransactions';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

// --- TYPES (template-compatible) ---
interface InvoiceDisplay {
    id: string;
    issueDate: string;
    dueDate: string;
    clientName: string;
    amount: number;
    status: 'sent' | 'overdue';
    matched: boolean;
    lineItems?: { id: string; description: string; amount: number; accountSubject: string }[];
}

interface TransactionDisplay {
    id: string;
    date: string;
    description: string;
    amount: number;
    type: 'bank' | 'card';
    matched: boolean;
}

// --- COMPOSABLES ---
const { invoices: apiInvoices, fetchInvoices } = useInvoices();
const { transactions: apiTransactions, matches, fetchTransactions, fetchMatches, createMatch, deleteMatch } = useTransactions();

// --- LOCAL STATE (built from API) ---
const rawInvoices = ref<InvoiceDisplay[]>([]);
const rawTransactions = ref<TransactionDisplay[]>([]);

const mapInvoice = (inv: any): InvoiceDisplay => {
    const isOverdue = inv.due_date && new Date(inv.due_date) < new Date();
    return {
        id: inv.id ?? inv._id,
        issueDate: inv.issue_date ?? inv.issueDate ?? '',
        dueDate: inv.due_date ?? inv.dueDate ?? '',
        clientName: inv.client_name ?? inv.clientName ?? '不明',
        amount: inv.total_amount ?? inv.amount ?? 0,
        status: isOverdue ? 'overdue' : 'sent',
        matched: false,
        lineItems: inv.line_items?.map((li: any, i: number) => ({
            id: li.id ?? `li-${i}`,
            description: li.description,
            amount: li.amount,
            accountSubject: li.category ?? li.account_subject ?? '売上高',
        })),
    };
};

const mapTransaction = (t: any): TransactionDisplay => ({
    id: t.id ?? t._id,
    date: t.transaction_date ?? t.date ?? '',
    description: t.description,
    amount: t.amount,
    type: t.source_type === 'card' ? 'card' : 'bank',
    matched: false,
});

const applyMatchStatus = () => {
    rawInvoices.value.forEach(i => { i.matched = false; });
    rawTransactions.value.forEach(t => { t.matched = false; });
    matches.value.forEach((m: any) => {
        if (m.match_type !== 'invoice') return;
        (m.document_ids ?? []).forEach((did: string) => {
            const inv = rawInvoices.value.find(i => i.id === did);
            if (inv) inv.matched = true;
        });
        (m.transaction_ids ?? []).forEach((tid: string) => {
            const tx = rawTransactions.value.find(t => t.id === tid);
            if (tx) tx.matched = true;
        });
    });
};

onMounted(async () => {
    await Promise.all([
        fetchInvoices({ document_type: 'issued' }),
        fetchTransactions({ source_type: 'bank' }),
        fetchMatches({ match_type: 'invoice' }),
    ]);
    rawInvoices.value = apiInvoices.value.map(mapInvoice);
    rawTransactions.value = apiTransactions.value.map(mapTransaction);
    applyMatchStatus();
});

// --- STATE ---
const activeTab = ref<'unmatched' | 'candidates' | 'matched'>('unmatched');
const invoiceSearch = ref('');
const transactionSearch = ref('');
const selectedInvoiceIds = ref<string[]>([]);
const selectedTransactionIds = ref<string[]>([]);
const expandedInvoiceIds = ref<string[]>([]);

const matchedFromDB = computed(() => {
    return matches.value
        .map((m: any) => {
            const inv = rawInvoices.value.find(i => m.document_ids?.includes(i.id));
            const tx = rawTransactions.value.find(t => m.transaction_ids?.includes(t.id));
            if (!inv || !tx) return null;
            return {
                matchId: m.id as string,
                invoice: inv,
                tx,
                timestamp: new Date(m.matched_at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
            };
        })
        .filter((item): item is NonNullable<typeof item> => item !== null);
});
const showConfirmMatch = ref(false);
const confirmMatchResolve = ref<((value: boolean) => void) | null>(null);
const confirmMatchAmount = ref(0);

// --- COMPUTED ---
const unmatchedInvoices = computed(() => {
    let list = rawInvoices.value.filter(i => !i.matched);
    if (invoiceSearch.value) list = list.filter(i => i.clientName.includes(invoiceSearch.value) || i.id.includes(invoiceSearch.value));
    return list;
});

const unmatchedTransactions = computed(() => {
    let list = rawTransactions.value.filter(t => !t.matched);
    if (transactionSearch.value) list = list.filter(t => t.description.includes(transactionSearch.value));
    return list;
});

const selectedTransactionSum = computed(() =>
    unmatchedTransactions.value.filter(t => selectedTransactionIds.value.includes(t.id)).reduce((s, t) => s + t.amount, 0)
);

const selectedInvoiceSum = computed(() =>
    unmatchedInvoices.value.filter(i => selectedInvoiceIds.value.includes(i.id)).reduce((s, i) => s + i.amount, 0)
);

const matchingDifference = computed(() => Math.abs(selectedTransactionSum.value - selectedInvoiceSum.value));

const suggestedInvoiceIds = computed(() => {
    if (selectedTransactionIds.value.length === 0) return [];
    return unmatchedInvoices.value.filter(i => !i.matched && i.amount === selectedTransactionSum.value).map(i => i.id);
});

const candidatePairs = computed(() => {
    const pairs: { invoice: InvoiceDisplay, transaction: TransactionDisplay }[] = [];
    const usedIds = new Set<string>();
    rawTransactions.value.filter(t => !t.matched).forEach(tx => {
        const match = rawInvoices.value.find(i => !i.matched && !usedIds.has(i.id) && i.amount === tx.amount);
        if (match) { pairs.push({ invoice: match, transaction: tx }); usedIds.add(match.id); }
    });
    return pairs;
});

const selectedCandidateIds = ref<string[]>([]);
const toggleCandidate = (txId: string) => {
    if (selectedCandidateIds.value.includes(txId)) selectedCandidateIds.value = selectedCandidateIds.value.filter(id => id !== txId);
    else selectedCandidateIds.value.push(txId);
};
const toggleAllCandidates = () => {
    if (selectedCandidateIds.value.length === candidatePairs.value.length) selectedCandidateIds.value = [];
    else selectedCandidateIds.value = candidatePairs.value.map(p => p.transaction.id);
};

// --- METHODS ---
const toggleInvoiceExpansion = (id: string) => {
    if (expandedInvoiceIds.value.includes(id)) expandedInvoiceIds.value = expandedInvoiceIds.value.filter(i => i !== id);
    else expandedInvoiceIds.value.push(id);
};

const selectInvoice = (id: string) => {
    if (selectedInvoiceIds.value.includes(id)) selectedInvoiceIds.value = selectedInvoiceIds.value.filter(i => i !== id);
    else selectedInvoiceIds.value.push(id);
};

const selectTransaction = (id: string) => {
    if (selectedTransactionIds.value.includes(id)) selectedTransactionIds.value = selectedTransactionIds.value.filter(i => i !== id);
    else selectedTransactionIds.value.push(id);
};


const handleMatch = async () => {
    if (selectedInvoiceIds.value.length === 0 || selectedTransactionIds.value.length === 0) return;
    if (matchingDifference.value > 1000) {
        confirmMatchAmount.value = matchingDifference.value;
        showConfirmMatch.value = true;
        const confirmed = await new Promise<boolean>(resolve => { confirmMatchResolve.value = resolve; });
        showConfirmMatch.value = false;
        if (!confirmed) return;
    }
    const period = new Date().toISOString().slice(0, 7);
    await createMatch({
        match_type: 'invoice',
        transaction_ids: [...selectedTransactionIds.value],
        document_ids: [...selectedInvoiceIds.value],
        fiscal_period: period,
    });
    await fetchMatches({ match_type: 'invoice' });
    applyMatchStatus();
    selectedInvoiceIds.value = [];
    selectedTransactionIds.value = [];
};

const handleBulkMatch = async () => {
    for (const txId of selectedCandidateIds.value) {
        const pair = candidatePairs.value.find(p => p.transaction.id === txId);
        if (!pair) continue;
        const period = new Date().toISOString().slice(0, 7);
        await createMatch({
            match_type: 'invoice',
            transaction_ids: [txId],
            document_ids: [pair.invoice.id],
            fiscal_period: period,
        });
    }
    selectedCandidateIds.value = [];
    await fetchMatches({ match_type: 'invoice' });
    applyMatchStatus();
};

const unmatch = async (invId: string, txId: string) => {
    const m = matches.value.find((mx: any) => mx.transaction_ids?.includes(txId) && mx.document_ids?.includes(invId));
    if (m) await deleteMatch(m.id);
    await fetchMatches({ match_type: 'invoice' });
    applyMatchStatus();
};
</script>


<template>
  <div class="h-full flex flex-col bg-slate-50">
    <header class="bg-white border-b border-gray-200 px-8 py-6 shrink-0 z-10">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">マッチング確認 (入金消込)</h1>
          <p class="text-sm text-gray-500 mt-1">システム内で作成した請求書データと、銀行口座等への入金データを突合（マッチング）します。</p>
        </div>
      </div>
 
      <div class="mt-6 flex flex-col md:flex-row gap-4 items-center justify-between">
        <div class="flex bg-gray-100/80 p-1.5 rounded-xl w-full overflow-x-auto shrink-0 border border-gray-200/50 shadow-inner">
          <button 
            @click="activeTab = 'unmatched'" 
            class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all relative flex items-center justify-center gap-1.5"
            :class="activeTab === 'unmatched' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50'"
          >
            未結合 ({{ unmatchedInvoices.length }})
          </button>
          
          <button 
            @click="activeTab = 'candidates'" 
            class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all relative flex items-center justify-center gap-1.5"
            :class="activeTab === 'candidates' ? 'bg-amber-50 text-amber-700 shadow-sm ring-1 ring-amber-500/20' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50'"
          >
            <div v-if="candidatePairs.length > 0" class="absolute top-2 right-4 md:right-auto md:-top-1 md:-right-1 w-3 h-3 bg-red-500 rounded-full border-2 border-white animate-pulse"></div>
            <span class="mr-1">✨</span> 自動結合候補 ({{ candidatePairs.length }})
          </button>
 
          <button
            @click="activeTab = 'matched'"
            class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all relative flex items-center justify-center gap-1.5"
            :class="activeTab === 'matched' ? 'bg-white text-emerald-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50'"
          >
            <CheckCircle v-if="matchedFromDB.length > 0" class="h-4 w-4 text-emerald-500" />
            結合済 ({{ matchedFromDB.length }})
          </button>
        </div>
      </div>
    </header>

    <main class="flex-1 overflow-hidden p-8">
    
    <!-- Unmatched Tab Content (Left: Invoices, Right: AP/Bank Tx) -->
    <template v-if="activeTab === 'unmatched'">
      
      <!-- Sticky Action Banner -->
      <div class="h-[72px] mb-6 relative">
          <!-- 1. Ready to Match Banner (Both selected && exact sum) -->
          <div v-if="selectedTransactionIds.length > 0 && selectedInvoiceIds.length > 0 && matchingDifference === 0" class="absolute inset-0 bg-blue-600 text-white p-4 rounded-xl shadow-lg flex items-center justify-between animate-in slide-in-from-top-2 z-20">
              <div class="flex items-center gap-3">
                  <div class="bg-blue-500 rounded-full p-2"><Link2 class="h-5 w-5 text-white" /></div>
                  <div>
                      <div class="flex items-center gap-2">
                          <p class="font-bold">結合準備完了</p>
                          <span class="text-[10px] font-bold bg-green-400 text-green-900 px-2 py-0.5 rounded-full shadow-sm">金額ピタリ一致</span>
                      </div>
                      <p class="text-blue-100 text-xs mt-0.5">対象: 入金 {{ selectedTransactionIds.length }}件 × 請求書 {{ selectedInvoiceIds.length }}件</p>
                      <div class="text-[11px] font-medium text-blue-200 mt-1 flex items-center gap-2">
                          <span>入金: ¥{{ formatAmount(selectedTransactionSum) }}</span>
                          <span>-</span>
                          <span>請求: ¥{{ formatAmount(selectedInvoiceSum) }}</span>
                          <span class="font-bold text-white">= 差額: ¥0</span>
                      </div>
                  </div>
              </div>
              <button @click="handleMatch" class="bg-white text-blue-600 font-bold px-6 py-2.5 rounded-lg shadow-sm hover:bg-blue-50 transition-colors flex items-center gap-2">
                  <CheckCircle class="w-4 h-4" />
                  この内容で結合する
              </button>
          </div>

          <!-- 2. Discrepancy Banner (Both selected but sums differ) -->
          <div v-else-if="selectedTransactionIds.length > 0 && selectedInvoiceIds.length > 0 && matchingDifference !== 0" class="absolute inset-0 bg-slate-800 text-white p-4 rounded-xl shadow-lg flex items-center justify-between animate-in slide-in-from-top-2 z-20">
              <div class="flex items-center gap-3">
                  <div class="bg-amber-500 rounded-full p-2"><AlertCircle class="h-5 w-5 text-amber-900" /></div>
                  <div>
                      <div class="flex items-center gap-2">
                          <p class="font-bold">金額の確認が必要です</p>
                          <span class="text-[10px] font-bold bg-amber-400 text-amber-900 px-2 py-0.5 rounded-full shadow-sm">差額あり</span>
                      </div>
                      <p class="text-gray-300 text-xs mt-0.5">対象: 入金 {{ selectedTransactionIds.length }}件 × 請求書 {{ selectedInvoiceIds.length }}件</p>
                      <div class="text-[11px] font-medium text-gray-400 mt-1 flex items-center gap-2">
                          <span>入金: ¥{{ formatAmount(selectedTransactionSum) }}</span>
                          <span>-</span>
                          <span>請求: ¥{{ formatAmount(selectedInvoiceSum) }}</span>
                          <span class="font-bold text-amber-400">= 差額: ¥{{ formatAmount(matchingDifference) }}</span>
                      </div>
                  </div>
              </div>
              <div class="flex items-center gap-2">
                  <button @click="handleMatch" class="bg-amber-500 text-amber-950 font-bold px-6 py-2.5 rounded-lg shadow-sm hover:bg-amber-400 transition-colors flex items-center gap-2">
                      <Link2 class="w-4 h-4" />
                      差額を許容して強制結合
                  </button>
              </div>
          </div>

          <!-- 3. Guidance Banner (Only one side selected) -->
          <div v-else-if="selectedTransactionIds.length > 0 || selectedInvoiceIds.length > 0" class="absolute inset-0 bg-blue-50 text-blue-900 p-4 rounded-xl shadow-md flex items-center gap-3 animate-in fade-in slide-in-from-top-2 border border-blue-200 z-10">
              <div class="bg-blue-100 rounded-full p-1.5"><ArrowRightLeft class="h-4 w-4 text-blue-600" /></div>
              <div>
                  <p class="font-bold text-sm">もう一方のリストから対応するデータを選択してください。</p>
                  <p class="text-[11px] text-blue-600 font-medium">現在選択中: {{ selectedTransactionIds.length > 0 ? `入金データ ${selectedTransactionIds.length}件 (¥${formatAmount(selectedTransactionSum)})` : '' }} {{ selectedInvoiceIds.length > 0 ? `請求書データ ${selectedInvoiceIds.length}件 (¥${formatAmount(selectedInvoiceSum)})` : '' }}</p>
              </div>
          </div>

          <!-- 4. Default Empty Banner -->
          <div v-else class="absolute inset-0 bg-gray-50 text-gray-500 p-4 rounded-xl border border-dashed border-gray-300 flex items-center justify-center gap-2 animate-in fade-in transition-all">
              <Link2 class="h-5 w-5 opacity-50" />
              <p class="font-medium text-sm">結合を開始するには、左の請求書リストまたは右の明細リストから対象を選択してください。</p>
          </div>
      </div>
      
      <!-- Main Split Layout for Invoices Matching -->
      <div class="flex h-[calc(100%-96px)] flex-col lg:flex-row gap-6">
        
        <!-- Left Pane: Issued Invoices -->
        <div class="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden">
            <div class="p-4 border-b border-gray-200 bg-blue-50/50 flex items-center justify-between shrink-0">
                <div class="flex items-center gap-2">
                    <FileText class="text-blue-700 h-5 w-5" />
                    <h2 class="font-bold text-gray-800 text-base">作成データ (請求書)</h2>
                    <span class="bg-blue-100 text-blue-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedInvoices.length }}</span>
                </div>
            </div>
            
            <div class="p-3 border-b border-gray-100 shrink-0">
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input v-model="invoiceSearch" type="text" placeholder="取引先名・請求書番号で検索..." class="w-full pl-9 pr-4 py-2 border border-blue-200 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500 bg-blue-50/30" />
                </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-blue-50/10 relative">
                    <div 
                    v-for="inv in unmatchedInvoices" :key="inv.id"
                    @click="selectInvoice(inv.id)"
                    class="bg-white border rounded-lg p-4 cursor-pointer transition-all hover:shadow-md relative overflow-hidden flex flex-col justify-between"
                    :class="[
                        selectedInvoiceIds.includes(inv.id) ? 'border-blue-500 ring-2 ring-blue-500 shadow-sm bg-blue-50/30' : 'border-gray-200 hover:border-gray-300',
                        suggestedInvoiceIds.includes(inv.id) && !selectedInvoiceIds.includes(inv.id) ? 'bg-amber-50 border-amber-300 ring-1 ring-amber-300' : ''
                    ]"
                >
                    <div v-if="selectedInvoiceIds.includes(inv.id)" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
                    
                    <div v-if="selectedInvoiceIds.includes(inv.id)" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                        <CheckCircle class="w-4 h-4" />
                    </div>

                    <div v-if="suggestedInvoiceIds.includes(inv.id) && !selectedInvoiceIds.includes(inv.id)" class="absolute top-0 right-0 bg-amber-400 text-amber-900 text-[10px] font-bold px-2 py-1 rounded-bl-lg shadow-sm flex items-center shadow-amber-500/20">
                        ✨ 金額一致 <span class="ml-2 font-black bg-amber-600 text-amber-50 px-1.5 py-0.5 rounded text-[9px] animate-pulse">クリックして一致を確認 ▸</span>
                    </div>
                    
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-50 text-gray-600 border-gray-200">
                                {{ inv.id }}
                            </span>
                            <span v-if="inv.status === 'overdue'" class="text-[10px] font-bold text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">期限超過</span>
                        </div>
                        <p class="text-lg font-bold tracking-tight text-gray-900 whitespace-nowrap ml-4">¥{{ formatAmount(inv.amount) }}</p>
                    </div>

                    <div class="flex justify-between items-end">
                        <div class="min-w-0 pr-4">
                            <p class="text-sm font-bold text-gray-900 leading-tight truncate w-[220px]" :title="inv.clientName">{{ inv.clientName }}</p>
                            <p class="text-[11px] text-gray-500 mt-1 font-medium">期日: {{ inv.dueDate }}</p>
                        </div>
                        <div class="shrink-0 flex flex-col items-end gap-2">
                            <!-- Accordion Toggle Button -->
                            <button 
                                v-if="inv.lineItems && inv.lineItems.length > 0"
                                @click.stop="toggleInvoiceExpansion(inv.id)"
                                class="text-gray-400 hover:text-blue-600 p-1 rounded transition-colors flex items-center justify-center bg-gray-50 hover:bg-blue-50 border border-gray-200"
                            >
                                <ChevronUp v-if="expandedInvoiceIds.includes(inv.id)" class="w-4 h-4" />
                                <ChevronDown v-else class="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                    
                    <!-- Line Items Accordion Panel -->
                    <div v-if="expandedInvoiceIds.includes(inv.id) && inv.lineItems && inv.lineItems.length > 0" class="mt-4 pt-3 border-t border-gray-100/50 bg-gray-50/50 -mx-2 px-2 rounded-lg">
                        <p class="text-[11px] font-bold text-gray-500 mb-2 flex items-center">
                            <FileText class="w-3 h-3 mr-1" /> 請求明細 ({{ inv.lineItems.length }}件)
                        </p>
                        <div class="space-y-2">
                            <div v-for="item in inv.lineItems" :key="item.id" class="flex items-start justify-between text-xs bg-white p-2 rounded border border-gray-100 shadow-sm">
                                <div class="break-words w-2/3 pr-2">
                                    <div class="font-bold text-gray-700 mb-0.5">{{ item.description }}</div>
                                    <div class="text-[10px] bg-gray-100 text-gray-600 px-1 py-0.5 rounded inline-block">{{ item.accountSubject }}</div>
                                </div>
                                <div class="font-bold text-gray-900 whitespace-nowrap mt-0.5">
                                    ¥{{ formatAmount(item.amount) }}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Center Divider (Desktop) -->
        <div class="hidden lg:flex flex-col items-center justify-center -mx-2 z-10 shrink-0">
            <div class="bg-gray-100 rounded-full p-2.5 border border-gray-200 shadow-sm shadow-blue-500/10">
                <Link2 class="h-5 w-5 text-blue-500" />
            </div>
        </div>

        <!-- Right Pane: Bank Deposit Transactions -->
        <div class="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col overflow-hidden">
            <div class="p-4 border-b border-gray-200 bg-slate-50 flex items-center justify-between shrink-0">
                <div class="flex items-center gap-2">
                    <Building2 class="text-slate-600 h-5 w-5" />
                    <h2 class="font-bold text-gray-800 text-base">入金データ</h2>
                    <span class="bg-slate-200 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedTransactions.length }}</span>
                </div>
            </div>
            
            <div class="p-3 border-b border-gray-100 shrink-0">
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input v-model="transactionSearch" type="text" placeholder="振込名義・金額で検索..." class="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500 bg-gray-50/50" />
                </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50/30">
                <div 
                    v-for="t in unmatchedTransactions" :key="t.id"
                    @click="selectTransaction(t.id)"
                    class="bg-white border rounded-lg p-4 cursor-pointer transition-all hover:shadow-md relative overflow-hidden flex flex-col justify-between"
                    :class="selectedTransactionIds.includes(t.id) ? 'border-blue-500 ring-2 ring-blue-500 shadow-sm bg-blue-50/30' : 'border-gray-200 hover:border-gray-300'"
                >
                    <div v-if="selectedTransactionIds.includes(t.id)" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
                    <div v-if="selectedTransactionIds.includes(t.id)" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                        <CheckCircle class="w-4 h-4" />
                    </div>
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full border" 
                                :class="t.type === 'card' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'">
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

    <!-- Candidate Tab -->
    <template v-else-if="activeTab === 'candidates'">
      <div class="h-full relative flex flex-col">
        <div class="flex-1 overflow-y-auto pb-24 space-y-4">
            <div v-for="pair in candidatePairs" :key="pair.transaction.id"
                @click="toggleCandidate(pair.transaction.id)"
                class="bg-indigo-50/30 rounded-xl border transition-shadow relative overflow-hidden flex items-center cursor-pointer hover:shadow-md"
                :class="selectedCandidateIds.includes(pair.transaction.id) ? 'border-indigo-400 ring-1 ring-indigo-400 shadow-sm bg-indigo-50/60' : 'border-indigo-200'"
            >
                <div class="pl-4 pr-2 py-6 shrink-0 flex items-center justify-center">
                    <div class="w-5 h-5 rounded border border-indigo-400 flex items-center justify-center transition-colors" :class="selectedCandidateIds.includes(pair.transaction.id) ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-white'">
                        <CheckCircle v-if="selectedCandidateIds.includes(pair.transaction.id)" class="w-4 h-4" />
                    </div>
                </div>
                <!-- Logic omitted for brevity, identical concepts to Receipt Matching just showing Invoices <-> Deposits -->
                <div class="flex-1 flex flex-col md:flex-row p-4 gap-4 items-center pl-2">
                    <div class="flex-1 bg-white border border-gray-200 rounded-lg p-3 w-full shadow-sm">
                        <div class="text-[10px] text-gray-400 font-bold mb-1 uppercase tracking-wider flex items-center gap-1"><FileText class="w-3 h-3"/> 請求書</div>
                        <p class="text-sm font-bold text-gray-900 truncate mb-1">{{ pair.invoice.clientName }}</p>
                        <div class="flex justify-between items-center text-xs text-gray-500">
                            <span>{{ pair.invoice.id }}</span>
                            <span class="font-bold text-gray-900">¥{{ formatAmount(pair.invoice.amount) }}</span>
                        </div>
                    </div>
                    <ArrowRightLeft class="text-indigo-300 shrink-0 w-5 h-5 hidden md:block" />
                    <div class="flex-1 bg-white border border-gray-200 rounded-lg p-3 w-full shadow-sm">
                        <div class="text-[10px] text-gray-400 font-bold mb-1 uppercase tracking-wider flex items-center gap-1"><Building2 class="w-3 h-3"/> 入金明細</div>
                        <p class="text-sm font-bold text-gray-900 truncate mb-1">{{ pair.transaction.description }}</p>
                        <div class="flex justify-between items-center text-xs text-gray-500">
                            <span>{{ pair.transaction.date }}</span>
                            <span class="font-bold text-gray-900">¥{{ formatAmount(pair.transaction.amount) }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div v-if="candidatePairs.length > 0" class="absolute bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4 shadow-[0_-10px_30px_rgba(0,0,0,0.05)] flex items-center justify-between z-10 rounded-t-xl">
            <div class="flex items-center gap-4">
                <button @click="toggleAllCandidates" class="text-sm font-bold text-indigo-600 hover:text-indigo-800 transition-colors px-2 py-1 rounded hover:bg-indigo-50">
                    {{ selectedCandidateIds.length === candidatePairs.length ? '全選択を解除' : 'すべて選択' }}
                </button>
                <span class="text-sm font-medium text-gray-600 border-l border-gray-300 pl-4">
                    <span class="font-bold text-gray-900">{{ selectedCandidateIds.length }}件</span> を選択中
                </span>
            </div>
            
            <button @click="handleBulkMatch" :disabled="selectedCandidateIds.length === 0" class="bg-indigo-600 text-white font-bold px-8 py-2.5 rounded-lg shadow-sm hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
                <CheckCircle class="w-5 h-5" />
                選択項目を消込する
            </button>
        </div>
      </div>
    </template>

    <!-- Matched Tab -->
    <template v-else-if="activeTab === 'matched'">
        <div class="h-full overflow-y-auto space-y-3 pb-8">
            <div v-if="matchedFromDB.length === 0" class="flex flex-col items-center justify-center py-20 bg-white rounded-xl border border-gray-200 shadow-sm text-gray-400 w-full h-full">
                <CheckCircle class="w-16 h-16 mb-4 text-gray-200" />
                <p class="font-medium">消込済データはありません</p>
            </div>

            <div v-for="item in matchedFromDB" :key="item.matchId" class="bg-emerald-50/30 border border-emerald-200 rounded-xl p-4 flex items-center justify-between group shadow-sm">
                <div class="flex items-center gap-6 flex-1">
                    <div class="bg-emerald-100 text-emerald-700 p-2 rounded-full shrink-0">
                        <CheckCircle class="w-5 h-5" />
                    </div>
                    <div class="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="flex flex-col">
                            <span class="text-[10px] text-gray-500 font-bold mb-0.5">作成データ (請求書)</span>
                            <span class="text-sm font-bold text-gray-900">{{ item.invoice.clientName }}</span>
                            <span class="text-[11px] text-gray-500">{{ item.invoice.id }}</span>
                        </div>
                        <div class="flex flex-col border-l border-emerald-200/50 pl-4">
                            <span class="text-[10px] text-gray-500 font-bold mb-0.5">入金データ</span>
                            <span class="text-sm font-bold text-gray-900">{{ item.tx.description }}</span>
                            <span class="text-[11px] text-gray-500">{{ item.tx.date }}</span>
                        </div>
                    </div>
                    <div class="text-right px-8 border-l border-emerald-200/50">
                        <span class="block text-[10px] text-gray-500 font-bold mb-0.5">消込金額</span>
                        <span class="text-xl font-black text-gray-900 tracking-tight">¥{{ formatAmount(item.invoice.amount) }}</span>
                    </div>
                </div>
                
                <div class="shrink-0 flex items-center gap-4">
                    <span class="text-[11px] text-gray-400 font-medium">{{ item.timestamp }} に消込</span>
                    <button @click="unmatch(item.invoice.id, item.tx.id)" class="px-3 py-1.5 bg-white border border-gray-300 rounded text-xs font-bold text-gray-600 hover:text-red-600 hover:border-red-300 hover:bg-red-50 transition-colors shadow-sm">
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
    <!-- Custom Confirmation Modal -->
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
