<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { 
  FileText, 
  CheckCircle, 
  Search,
  Upload,
  Link2,
  Clock,
  ChevronDown,
  ChevronUp
} from 'lucide-vue-next';
import { useTransactions, type Transaction as ApiTransaction } from '@/composables/useTransactions';
import { useReceipts } from '@/composables/useReceipts';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

// --- TYPES (keep for template compatibility) ---
interface Transaction {
  id: string;
  date: string;
  description: string;
  amount: number;
  type: 'card' | 'bank';
  status: 'unmatched' | 'candidate' | 'matched';
  matchedReceiptId?: string;
}

interface LineItem {
  id: string;
  description: string;
  amount: number;
  accountSubject: string;
}

interface MatchingReceipt {
  id: string;
  submitterName: string;
  date: string;
  issuer: string;
  amount: number;
  paymentMethod: string;
  status: 'pending' | 'approved' | 'rejected';
  matchStatus: 'unmatched' | 'candidate' | 'matched';
  matchedTransactionId?: string;
  lineItems?: LineItem[];
}

// --- COMPOSABLES ---
const { transactions: apiTransactions, matches, fetchTransactions, fetchMatches, createMatch, deleteMatch } = useTransactions();
const { receipts: apiReceipts, fetchReceipts } = useReceipts();

// --- LOCAL STATE (computed from API data) ---
const transactions = ref<Transaction[]>([]);
const receiptsMock = ref<MatchingReceipt[]>([]);

const mapApiToTransaction = (t: ApiTransaction): Transaction => ({
  id: t.id,
  date: t.transaction_date,
  description: t.description,
  amount: t.amount,
  type: t.source_type,
  status: 'unmatched',
  matchedReceiptId: undefined,
});

const mapApiToReceipt = (r: any): MatchingReceipt => ({
  id: r.id ?? r._id,
  submitterName: r.submitter_name ?? r.created_by ?? '不明',
  date: r.date,
  issuer: r.payee ?? r.issuer ?? '不明',
  amount: r.amount,
  paymentMethod: r.payment_method ?? '法人カード',
  status: r.approval_status === 'approved' || r.approval_status === 'auto_approved' ? 'approved' : r.approval_status === 'rejected' ? 'rejected' : 'pending',
  matchStatus: 'unmatched',
  matchedTransactionId: undefined,
  lineItems: r.line_items?.map((li: any) => ({
    id: li.id ?? li._id ?? Math.random().toString(),
    description: li.description,
    amount: li.amount,
    accountSubject: li.category ?? li.account_subject ?? '未分類',
  })),
});

const applyMatches = () => {
  // Reset all statuses first
  transactions.value.forEach(t => { t.status = 'unmatched'; t.matchedReceiptId = undefined; });
  receiptsMock.value.forEach(r => { r.matchStatus = 'unmatched'; r.matchedTransactionId = undefined; });

  // Apply matches from API
  matches.value.forEach((m: any) => {
    const tid = m.bank_transaction_id;
    const rid = m.document_id;
    const t = transactions.value.find(tx => tx.id === tid);
    const r = receiptsMock.value.find(rc => rc.id === rid);
    if (t) { t.status = 'matched'; t.matchedReceiptId = rid; }
    if (r) { r.matchStatus = 'matched'; r.matchedTransactionId = tid; }
  });
};

const loadData = async () => {
  await Promise.all([
    fetchTransactions({}),
    fetchReceipts({}),
    fetchMatches(),
  ]);
  transactions.value = apiTransactions.value.map(mapApiToTransaction);
  receiptsMock.value = apiReceipts.value
    .filter(r => ['法人カード', '銀行振込', 'corporate_card', 'bank_transfer'].includes(r.payment_method))
    .map(mapApiToReceipt);
  applyMatches();
};

onMounted(loadData);

// --- STATE ---
const activeTab = ref<'unmatched' | 'candidate' | 'matched'>('unmatched');
const selectedTransactionIds = ref<string[]>([]);
const selectedReceiptIds = ref<string[]>([]);
const selectedCandidateIds = ref<string[]>([]);
const expandedReceiptIds = ref<string[]>([]);

// Custom Confirm Modal State
const showConfirmMatch = ref(false);
const confirmMatchResolve = ref<((value: boolean) => void) | null>(null);
const confirmMatchAmount = ref(0);

// Search & Filter
const transactionSearch = ref('');
const receiptSearch = ref('');

// --- COMPUTED ---
const unmatchedTransactions = computed(() => {
  return transactions.value
    .filter(t => t.status === 'unmatched')
    .filter(t => t.description.includes(transactionSearch.value) || t.amount.toString().includes(transactionSearch.value));
});

const unmatchedReceipts = computed(() => {
  let list = receiptsMock.value
    .filter(r => r.matchStatus === 'unmatched')
    .filter(r => r.issuer.includes(receiptSearch.value) || r.submitterName.includes(receiptSearch.value) || r.amount.toString().includes(receiptSearch.value));

  if (selectedTransactionIds.value.length > 0) {
    const targetSum = selectedTransactionSum.value;
    list.sort((a, b) => {
      const aMatch = a.amount === targetSum;
      const bMatch = b.amount === targetSum;
      if (aMatch && !bMatch) return -1;
      if (!aMatch && bMatch) return 1;
      return 0;
    });
  }

  return list;
});

const selectedTransactionSum = computed(() =>
  transactions.value
    .filter(t => selectedTransactionIds.value.includes(t.id))
    .reduce((sum, t) => sum + t.amount, 0)
);

const selectedReceiptSum = computed(() =>
  receiptsMock.value
    .filter(r => selectedReceiptIds.value.includes(r.id))
    .reduce((sum, r) => sum + r.amount, 0)
);

const matchingDifference = computed(() => selectedTransactionSum.value - selectedReceiptSum.value);

const suggestedReceiptIds = computed(() => {
  if (selectedTransactionIds.value.length === 0) return [];
  const targetSum = selectedTransactionSum.value;
  return receiptsMock.value
    .filter(r => r.matchStatus === 'unmatched' && r.amount === targetSum)
    .map(r => r.id);
});

const candidatePairs = computed(() =>
  transactions.value
    .filter(t => t.status === 'candidate' && t.matchedReceiptId)
    .map(t => ({
      transaction: t,
      receipt: receiptsMock.value.find(r => r.id === t.matchedReceiptId),
    }))
);

const matchedPairs = computed(() =>
  transactions.value
    .filter(t => t.status === 'matched' && t.matchedReceiptId)
    .map(t => ({
      transaction: t,
      receipt: receiptsMock.value.find(r => r.id === t.matchedReceiptId),
    }))
);

const matchedCount = computed(() => transactions.value.filter(t => t.status === 'matched').length);

// --- ACTIONS ---

const toggleCandidate = (id: string) => {
  const idx = selectedCandidateIds.value.indexOf(id);
  if (idx > -1) selectedCandidateIds.value.splice(idx, 1);
  else selectedCandidateIds.value.push(id);
};

const handleBulkMatch = async () => {
  for (const tId of selectedCandidateIds.value) {
    const t = transactions.value.find(tx => tx.id === tId);
    if (!t || !t.matchedReceiptId) continue;
    const currentPeriod = new Date().toISOString().slice(0, 7);
    await createMatch({
      match_type: 'receipt',
      transaction_ids: [tId],
      document_ids: [t.matchedReceiptId],
      fiscal_period: currentPeriod,
    });
  }
  await fetchMatches();
  applyMatches();
  selectedCandidateIds.value = [];
  activeTab.value = 'matched';
};

const revertToUnmatched = async (transactionId: string) => {
  const m = matches.value.find((mx: any) => mx.transaction_ids?.includes(transactionId));
  if (m) await deleteMatch(m.id);
  await fetchMatches();
  applyMatches();
  const selectedIdx = selectedCandidateIds.value.indexOf(transactionId);
  if (selectedIdx > -1) selectedCandidateIds.value.splice(selectedIdx, 1);
};

const selectTransaction = (id: string) => {
  const idx = selectedTransactionIds.value.indexOf(id);
  if (idx > -1) selectedTransactionIds.value.splice(idx, 1);
  else selectedTransactionIds.value.push(id);
};

const selectReceipt = (id: string) => {
  const idx = selectedReceiptIds.value.indexOf(id);
  if (idx > -1) selectedReceiptIds.value.splice(idx, 1);
  else selectedReceiptIds.value.push(id);
};

const toggleReceiptExpansion = (id: string) => {
  const idx = expandedReceiptIds.value.indexOf(id);
  if (idx > -1) expandedReceiptIds.value.splice(idx, 1);
  else expandedReceiptIds.value.push(id);
};

const handleMatch = async () => {
  if (selectedTransactionIds.value.length === 0 || selectedReceiptIds.value.length === 0) return;

  if (Math.abs(matchingDifference.value) > 1000) {
    confirmMatchAmount.value = Math.abs(matchingDifference.value);
    showConfirmMatch.value = true;
    const confirmed = await new Promise<boolean>(resolve => { confirmMatchResolve.value = resolve; });
    showConfirmMatch.value = false;
    if (!confirmed) return;
  }

  // Create single match record linking all selected transactions to all selected receipts
  const currentPeriod = new Date().toISOString().slice(0, 7);
  await createMatch({
    match_type: 'receipt',
    transaction_ids: [...selectedTransactionIds.value],
    document_ids: [...selectedReceiptIds.value],
    fiscal_period: currentPeriod,
  });

  await fetchMatches();
  applyMatches();
  selectedTransactionIds.value = [];
  selectedReceiptIds.value = [];
};
</script>

<template>
  <div class="space-y-6 h-full flex flex-col">
    <!-- Header -->
    <div class="flex flex-col gap-4 shrink-0">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">口座・カード明細マッチング</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          「データアップロード」画面で取り込まれた明細データと、提出された領収書データを突合（マッチング）し、仕訳を確定します。<br/>
          ※ 領収書の承認ステータスに関わらず、決済手段が「法人カード」「銀行振込」のデータがマッチング対象となります。
        </p>
      </div>
      <!-- Tabs -->
      <div class="flex w-full items-center gap-1 bg-gray-100 p-1.5 rounded-xl shadow-inner shrink-0">
        <button 
            @click="activeTab = 'unmatched'"
            :class="activeTab === 'unmatched' ? 'bg-white text-gray-900 shadow-sm font-bold' : 'text-gray-500 hover:text-gray-700 font-medium'"
            class="flex-1 justify-center px-6 py-2.5 rounded-lg text-sm transition-all"
        >
            未結合 ({{ unmatchedTransactions.length }})
        </button>
        <button 
            @click="activeTab = 'candidate'"
            :class="activeTab === 'candidate' ? 'bg-white text-gray-900 shadow-sm font-bold ring-1 ring-blue-500/20' : 'text-gray-500 hover:text-gray-700 font-medium'"
            class="flex-1 justify-center px-6 py-2.5 rounded-lg text-sm transition-all flex items-center gap-1.5 relative"
        >
            <div v-if="candidatePairs.length > 0" class="absolute top-2 right-4 md:right-auto md:-top-1 md:-right-1 w-3 h-3 bg-red-500 rounded-full border-2 border-white animate-pulse"></div>
            ✨ 自動結合候補 ({{ candidatePairs.length }})
        </button>
        <button 
            @click="activeTab = 'matched'"
            :class="activeTab === 'matched' ? 'bg-white text-gray-900 shadow-sm font-bold' : 'text-gray-500 hover:text-gray-700 font-medium'"
            class="flex-1 justify-center px-6 py-2.5 rounded-lg text-sm transition-all flex items-center gap-1.5"
        >
            <CheckCircle v-if="matchedCount > 0" class="h-4 w-4 text-emerald-500" />
            結合済 ({{ matchedCount }})
        </button>
      </div>
    </div>

    <!-- Unmatched Tab Content -->
    <template v-if="activeTab === 'unmatched'">
      <!-- Interactive Action / Guidance Bar Area -->
      <div class="shrink-0 transition-all relative">
          <!-- 1. Match Action Bar (Transaction AND Receipt selected) -->
          <div v-if="selectedTransactionIds.length > 0 && selectedReceiptIds.length > 0" class="bg-blue-600 text-white p-4 rounded-xl shadow-lg flex flex-col md:flex-row items-center justify-between animate-in slide-in-from-top-2 fade-in border border-blue-500 z-20 gap-4">
              <div class="flex items-start gap-3 w-full md:w-auto">
                  <div class="bg-white/20 p-2 rounded-full hidden sm:block mt-1"><Link2 class="h-5 w-5" /></div>
                  <div class="flex-1">
                      <div class="flex items-center gap-2 mb-1">
                           <p class="font-bold text-lg">結合準備完了</p>
                           <span v-if="matchingDifference !== 0" class="text-xs bg-amber-500 text-white px-2 py-0.5 rounded-full font-bold">差額あり</span>
                           <span v-else class="text-xs bg-emerald-500 text-white px-2 py-0.5 rounded-full font-bold">金額ピタリ一致</span>
                      </div>
                      
                      <div class="text-blue-50 text-sm space-y-1">
                          <p>
                              対象: <span class="font-bold">入金 {{ selectedTransactionIds.length }}件</span> 
                              × <span class="font-bold">領収書 {{ selectedReceiptIds.length }}件</span>
                          </p>
                          <div class="flex items-center gap-3 bg-black/10 px-3 py-1.5 rounded-lg border border-white/10 mt-2 text-white">
                              <div>入金: <strong>¥{{ formatAmount(selectedTransactionSum) }}</strong></div>
                              <div>-</div>
                              <div>請求: <strong>¥{{ formatAmount(selectedReceiptSum) }}</strong></div>
                              <div>=</div>
                              <div :class="matchingDifference !== 0 ? 'text-amber-300' : 'text-emerald-300'">
                                 差額: <strong>¥{{ formatAmount(matchingDifference) }}</strong>
                              </div>
                          </div>
                          
                          <p v-if="matchingDifference !== 0" class="text-xs text-amber-200 mt-2 font-medium bg-black/20 p-2 rounded border border-amber-500/30">
                              ※差額分は「振込手数料等」として自動処理（仕訳）されます。
                          </p>
                      </div>
                  </div>
              </div>
              <button @click="handleMatch" class="w-full md:w-auto bg-white text-blue-600 font-bold px-8 py-3 rounded-lg shadow-sm hover:bg-blue-50 transition-colors shrink-0 flex justify-center items-center gap-2 text-base">
                  <CheckCircle class="w-5 h-5" />
                  <span>この内容で結合する</span>
              </button>
          </div>

          <!-- 2. Guidance Banner (Transaction selected, NO receipt selected) -->
          <div v-else-if="selectedTransactionIds.length > 0 && selectedReceiptIds.length === 0" class="bg-amber-50 text-amber-900 p-4 rounded-xl shadow-md flex items-center gap-3 animate-in fade-in slide-in-from-top-2 border border-amber-300 z-10">
              <span class="flex h-6 w-6 items-center justify-center rounded-full bg-amber-200 text-amber-900 text-sm font-bold border border-amber-400 shrink-0 shadow-sm animate-pulse">!</span>
              <div>
                  <p class="font-bold">右の明細 (計 ¥{{ formatAmount(selectedTransactionSum) }}) に対応する領収書を、左のリストから選択してください。</p>
              </div>
          </div>

          <!-- 3. Default Empty Banner (NO transaction selected) -->
          <div v-else class="bg-gray-50 text-gray-500 p-4 rounded-xl border border-dashed border-gray-300 flex items-center justify-center gap-2 animate-in fade-in transition-all">
              <Link2 class="h-5 w-5 opacity-50" />
              <p class="font-medium text-sm">マッチングを開始するには、左のリストから領収書を選択してください（または右の明細を選択）。</p>
          </div>
      </div>
      


      <!-- Main Split Layout -->
      <div class="flex-1 flex flex-col lg:flex-row gap-6 min-h-0">
        
        <!-- Left Pane: Receipts -->
        <div class="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col min-h-[400px] overflow-hidden">
            <div class="p-4 border-b border-gray-200 bg-blue-50/50 flex items-center justify-between shrink-0">
                <div class="flex items-center gap-2">
                    <FileText class="text-blue-700 h-5 w-5" />
                    <h2 class="font-bold text-gray-800 text-base">領収書データ (要マッチング)</h2>
                    <span class="bg-blue-100 text-blue-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedReceipts.length }}</span>
                </div>
            </div>
            
            <div class="p-3 border-b border-gray-100 shrink-0">
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input v-model="receiptSearch" type="text" placeholder="発行元・提出者・金額で検索..." class="w-full pl-9 pr-4 py-2 border border-blue-200 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500 bg-blue-50/30" />
                </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-blue-50/10 relative">
                <!-- Receipt Cards -->
                <div 
                    v-for="r in unmatchedReceipts" :key="r.id"
                    @click="selectReceipt(r.id)"
                    class="bg-white border rounded-lg p-4 cursor-pointer transition-all hover:shadow-md relative overflow-hidden flex flex-col justify-between min-h-[105px] select-none"
                    :class="[
                        selectedReceiptIds.includes(r.id) ? 'border-blue-500 ring-2 ring-blue-500 shadow-sm bg-blue-50/30' : 'border-gray-200 hover:border-gray-300',
                        suggestedReceiptIds.includes(r.id) && !selectedReceiptIds.includes(r.id) ? 'bg-amber-50 border-amber-300 ring-1 ring-amber-300' : ''
                    ]"
                >
                    <div v-if="selectedReceiptIds.includes(r.id)" class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
                    
                    <div v-if="selectedReceiptIds.includes(r.id)" class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                        <CheckCircle class="w-4 h-4" />
                    </div>

                    <div v-if="suggestedReceiptIds.includes(r.id) && !selectedReceiptIds.includes(r.id)" class="absolute top-0 right-0 bg-amber-400 text-amber-900 text-[10px] font-bold px-2 py-1 rounded-bl-lg shadow-sm flex items-center shadow-amber-500/20">
                        ✨ 推奨 <span class="ml-2 font-black bg-amber-600 text-amber-50 px-1.5 py-0.5 rounded text-[9px] animate-pulse">クリックして一致 ▸</span>
                    </div>
                    
                    <div class="flex justify-between items-start mb-2">
                        <div class="flex items-center gap-2">
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-50 text-gray-600 border-gray-200">
                                {{ r.paymentMethod }}
                            </span>
                            <span class="text-xs text-gray-500 font-medium">{{ r.date }}</span>
                        </div>
                        <p class="text-lg font-bold tracking-tight text-gray-900 whitespace-nowrap ml-4">¥{{ formatAmount(r.amount) }}</p>
                    </div>

                    <div class="flex justify-between items-end">
                        <div class="min-w-0 pr-4">
                            <p class="text-sm font-bold text-gray-900 leading-tight truncate w-[220px]" :title="r.issuer">{{ r.issuer }}</p>
                            
                            <div class="flex items-center gap-2 mt-2">
                                <div class="h-5 w-5 rounded-full bg-slate-200 flex items-center justify-center text-[9px] font-bold text-slate-600">
                                    {{ r.submitterName.charAt(0) }}
                                </div>
                                <p class="text-[13px] text-gray-600 font-medium">{{ r.submitterName }}</p>
                            </div>
                        </div>
                        <div class="shrink-0 flex flex-col items-end gap-2">
                            <span v-if="r.status === 'approved'" class="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-1 rounded border border-emerald-200">承認済</span>
                            <span v-else-if="r.status === 'pending'" class="text-[11px] font-bold text-blue-700 bg-blue-50 px-2 py-1 rounded border border-blue-200 flex items-center"><Clock class="w-3.5 h-3.5 mr-1 text-blue-500"/>承認進行中</span>
                            
                            <!-- Accordion Toggle Button -->
                            <button 
                                v-if="r.lineItems && r.lineItems.length > 0"
                                @click.stop="toggleReceiptExpansion(r.id)"
                                class="text-gray-400 hover:text-blue-600 p-1 rounded transition-colors flex items-center justify-center bg-gray-50 hover:bg-blue-50 border border-gray-200"
                            >
                                <ChevronUp v-if="expandedReceiptIds.includes(r.id)" class="w-4 h-4" />
                                <ChevronDown v-else class="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                    
                    <!-- Line Items Accordion Panel -->
                    <div v-if="expandedReceiptIds.includes(r.id) && r.lineItems && r.lineItems.length > 0" class="mt-4 pt-3 border-t border-gray-100/50 bg-gray-50/50 -mx-2 px-2 rounded-lg">
                        <p class="text-[11px] font-bold text-gray-500 mb-2 flex items-center">
                            <FileText class="w-3 h-3 mr-1" /> 内訳 ({{ r.lineItems.length }}件)
                        </p>
                        <div class="space-y-2">
                            <div v-for="item in r.lineItems" :key="item.id" class="flex items-start justify-between text-xs bg-white p-2 rounded border border-gray-100 shadow-sm">
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
                
                <div v-if="unmatchedReceipts.length === 0" class="text-center py-12 text-sm text-gray-500">
                    マッチング対象の領収書がありません
                </div>
            </div>
        </div>

        <!-- Center Divider (Desktop only visual cue) -->
        <div class="hidden lg:flex flex-col items-center justify-center -mx-2 z-10 shrink-0">
            <div class="bg-gray-100 rounded-full p-2.5 border border-gray-200 shadow-sm shadow-blue-500/10">
                <Link2 class="h-5 w-5 text-blue-500" />
            </div>
        </div>

        <!-- Right Pane: Transactions -->
        <div class="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col min-h-[400px] overflow-hidden">
            <div class="p-4 border-b border-gray-200 bg-slate-50 flex items-center justify-between shrink-0">
                <div class="flex items-center gap-2">
                    <Building2 class="text-slate-600 h-5 w-5" />
                    <h2 class="font-bold text-gray-800 text-base">口座・カード明細 (未結合)</h2>
                    <span class="bg-slate-200 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedTransactions.length }}</span>
                </div>
            </div>
            
            <div class="p-3 border-b border-gray-100 shrink-0">
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input v-model="transactionSearch" type="text" placeholder="摘要・金額で検索..." class="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500 bg-gray-50/50" />
                </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50/30">
                <div v-if="transactions.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400 py-12">
                    <Upload class="h-12 w-12 mb-3 text-gray-300" />
                    <p class="text-sm font-medium text-gray-600">明細データが存在しません</p>
                    <p class="text-xs mt-1">上部の取得ボタンからデータを取り込んでください</p>
                </div>
                
                <!-- Transaction Cards -->
                <div 
                    v-for="t in unmatchedTransactions" :key="t.id"
                    @click="selectTransaction(t.id)"
                    class="bg-white border rounded-lg p-4 cursor-pointer transition-all hover:shadow-md relative overflow-hidden flex flex-col justify-between min-h-[90px] select-none"
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
                                {{ t.type === 'card' ? 'カード' : '銀行振込' }}
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

    <!-- Candidate Tab Content -->
    <template v-else-if="activeTab === 'candidate'">
      <div class="flex flex-col h-full relative">
        <div class="flex-1 overflow-y-auto no-scrollbar pb-24">
            <div v-if="candidatePairs.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400 py-20 bg-white rounded-xl border border-gray-200 shadow-sm">
                <Link2 class="h-16 w-16 mb-4 text-gray-200" />
                <p class="text-base font-medium text-gray-500">自動結合できる候補はありません。</p>
            </div>

            <div v-else class="space-y-4">
                <div 
                    v-for="pair in candidatePairs" :key="pair.transaction.id"
                    @click="toggleCandidate(pair.transaction.id)"
                    class="bg-indigo-50/30 rounded-xl border transition-shadow relative overflow-hidden flex items-center cursor-pointer hover:shadow-md"
                    :class="selectedCandidateIds.includes(pair.transaction.id) ? 'border-indigo-400 ring-1 ring-indigo-400 shadow-sm bg-indigo-50/60' : 'border-indigo-200'"
                >
                    <!-- Checkbox Area -->
                    <div class="pl-4 pr-2 py-6 shrink-0 flex items-center justify-center">
                        <div class="w-5 h-5 rounded border border-indigo-400 flex items-center justify-center transition-colors" :class="selectedCandidateIds.includes(pair.transaction.id) ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-white'">
                            <CheckCircle v-if="selectedCandidateIds.includes(pair.transaction.id)" class="w-4 h-4" />
                        </div>
                    </div>

                    <!-- Main Content -->
                    <div class="flex-1 flex flex-col md:flex-row p-4 pl-2 items-center gap-6 pointer-events-none">
                        <!-- Transaction Details (Left side) -->
                        <div class="flex-1 min-w-0 pr-4 md:border-r border-indigo-200 border-dashed w-full md:w-auto">
                            <div class="flex items-center justify-between mb-2">
                                <div class="flex items-center gap-2">
                                    <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-white text-indigo-700 border-indigo-200">
                                        {{ pair.transaction.type === 'card' ? 'カード明細' : '銀行明細' }}
                                    </span>
                                    <span class="text-xs text-gray-500 font-medium">{{ pair.transaction.date }}</span>
                                </div>
                            </div>
                            <p class="text-base font-bold text-gray-900 truncate" :title="pair.transaction.description">{{ pair.transaction.description }}</p>
                        </div>

                        <!-- Center Link Icon -->
                        <div class="shrink-0 flex-col items-center justify-center hidden md:flex">
                            <div class="bg-indigo-100 text-indigo-600 rounded-full p-2 mb-1 shadow-sm font-bold text-xs ring-2 ring-white">
                                <Link2 class="h-5 w-5" />
                            </div>
                            <p class="text-[10px] font-bold text-indigo-700 tracking-wider mt-1">自動マッチ</p>
                        </div>

                        <!-- Receipt Details (Right side) -->
                        <div class="flex-1 min-w-0 md:pl-4 w-full md:w-auto mt-2 md:mt-0">
                            <div class="flex items-center justify-between mb-2">
                                <div class="flex items-center gap-2">
                                    <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-white text-indigo-700 border-indigo-200">
                                        {{ pair.receipt?.paymentMethod || '提出領収書' }}
                                    </span>
                                    <span class="text-xs text-gray-500 font-medium">{{ pair.receipt?.date }}</span>
                                </div>
                            </div>
                            <p class="text-base font-bold text-gray-900 truncate" :title="pair.receipt?.issuer">{{ pair.receipt?.issuer }}</p>
                            <p class="text-xs text-gray-500 mt-1 flex items-center gap-1">
                                <FileText class="h-3 w-3" /> {{ pair.receipt?.submitterName }}
                            </p>
                        </div>

                        <!-- Amount (Far right) -->
                        <div class="shrink-0 md:w-40 flex flex-col items-end md:items-end mt-2 md:mt-0 gap-2 pointer-events-auto">
                            <p class="text-xl font-bold tracking-tight text-indigo-900 border-b-2 border-indigo-200 pb-1 inline-block">¥{{ formatAmount(pair.transaction.amount) }}</p>
                            <button 
                                @click.stop="revertToUnmatched(pair.transaction.id)"
                                class="text-xs text-red-600 hover:text-red-800 hover:bg-red-50 px-2 py-1 rounded transition-colors"
                            >
                                候補から外す
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Floating Bulk Action Bar -->
        <div v-if="candidatePairs.length > 0" class="absolute bottom-4 left-0 right-0 bg-gray-900 text-white p-4 rounded-xl shadow-xl flex flex-col md:flex-row items-center justify-between gap-4 animate-in slide-in-from-bottom border border-gray-700 z-20">
            <div class="flex items-center gap-4">
                <span class="bg-gray-800 text-gray-300 text-sm font-bold px-3 py-1.5 rounded-lg border border-gray-700">
                    選択中: <span class="text-white text-base">{{ selectedCandidateIds.length }}</span> 件
                </span>
                <p class="text-sm text-gray-300 hidden md:block">選択した内容で一括結合を実行します</p>
            </div>
            <button 
                @click="handleBulkMatch" 
                :disabled="selectedCandidateIds.length === 0"
                class="bg-blue-600 text-white font-bold px-8 py-3 rounded-lg shadow-sm hover:bg-blue-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
                <CheckCircle class="h-5 w-5" /> 一括結合を実行
            </button>
        </div>
      </div>
    </template>

    <!-- Matched Tab Content -->
    <template v-else>
      <div class="flex-1 overflow-y-auto no-scrollbar pb-8">
        <div v-if="matchedPairs.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400 py-20 bg-white rounded-xl border border-gray-200 shadow-sm">
            <Link2 class="h-16 w-16 mb-4 text-gray-200" />
            <p class="text-base font-medium text-gray-500">結合済みのデータはありません。</p>
            <p class="text-sm mt-1 text-gray-400">「未結合」タブで明細と領収書をマッチングしてください。</p>
        </div>

        <div v-else class="space-y-4">
            <div 
                v-for="pair in matchedPairs" :key="pair.transaction.id"
                class="bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex items-center gap-6 hover:shadow-md transition-shadow relative overflow-hidden"
            >
                <!-- Left Line Decoration -->
                <div class="absolute left-0 top-0 bottom-0 w-1.5 bg-emerald-500"></div>

                <!-- Transaction Details (Left side) -->
                <div class="flex-1 min-w-0 pr-4 border-r border-gray-200 border-dashed">
                    <div class="flex items-center justify-between mb-2">
                         <div class="flex items-center gap-2">
                             <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-slate-50 text-slate-700 border-slate-200">
                                {{ pair.transaction.type === 'card' ? 'カード明細' : '銀行明細' }}
                            </span>
                             <span class="text-xs text-gray-500 font-medium">{{ pair.transaction.date }}</span>
                         </div>
                    </div>
                    <p class="text-base font-bold text-gray-900 truncate" :title="pair.transaction.description">{{ pair.transaction.description }}</p>
                </div>

                <!-- Center Link Icon -->
                <div class="shrink-0 flex flex-col items-center justify-center">
                    <div class="bg-emerald-100 text-emerald-600 rounded-full p-2 mb-1 shadow-sm font-bold text-xs ring-2 ring-white">
                        <CheckCircle class="h-5 w-5" />
                    </div>
                    <p class="text-[10px] font-bold text-emerald-700 uppercase tracking-widest">結合済</p>
                </div>

                <!-- Receipt Details (Right side) -->
                <div class="flex-1 min-w-0 pl-4">
                    <div class="flex items-center justify-between mb-2">
                         <div class="flex items-center gap-2">
                             <span class="text-xs font-medium px-2 py-0.5 rounded-full border bg-gray-50 text-gray-600 border-gray-200">
                                {{ pair.receipt?.paymentMethod || '提出領収書' }}
                            </span>
                             <span class="text-xs text-gray-500 font-medium">{{ pair.receipt?.date }}</span>
                         </div>
                    </div>
                    <p class="text-base font-bold text-gray-900 truncate" :title="pair.receipt?.issuer">{{ pair.receipt?.issuer }}</p>
                    <p class="text-xs text-gray-500 mt-1 flex items-center gap-1">
                        <FileText class="h-3 w-3" /> {{ pair.receipt?.submitterName }}
                    </p>
                </div>

                <!-- Amount (Far right) -->
                <div class="shrink-0 w-32 flex flex-col items-end gap-2">
                     <p class="text-xl font-bold tracking-tight text-gray-900 border-b-2 border-emerald-100 pb-1 inline-block">¥{{ formatAmount(pair.transaction.amount) }}</p>
                     
                     <div class="flex items-center gap-2">
                        <CheckCircle class="h-3.5 w-3.5 text-emerald-600" /> 
                        <span class="text-xs font-bold text-emerald-700">突合一致</span>
                     </div>
                     
                     <button 
                        @click="revertToUnmatched(pair.transaction.id)"
                        class="text-xs text-gray-400 hover:text-red-600 hover:bg-red-50 px-2 py-1 rounded transition-colors mt-1"
                     >
                        未結合に戻す
                     </button>
                </div>
            </div>
        </div>
      </div>
    </template>
    <!-- Custom Confirmation Modal -->
    <div v-if="showConfirmMatch" class="fixed inset-0 z-[110] flex items-center justify-center p-4">
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
