<script setup lang="ts">
import { ref, computed, onMounted, shallowRef } from 'vue';
import {
  FileText,
  CheckCircle,
  Search,
  Upload,
  Link2,
  Clock,
  ChevronDown,
  ChevronUp,
  User,
} from 'lucide-vue-next';
import { useReceipts, type Receipt } from '@/composables/useReceipts';
import { useDocumentMatching, type MatchableDocument } from '@/composables/useDocumentMatching';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import { MATCHING_STYLES } from '@/constants/matchingStyles';
import { api } from '@/lib/api';

// --- TYPES ---
interface MatchingEntry extends Receipt, MatchableDocument {}

// --- DATA SOURCE ---
const { receipts: apiReceipts, fetchReceipts } = useReceipts();
const receiptsMock = ref<MatchingEntry[]>([]);

const fetchAndMapReceipts = async () => {
  await fetchReceipts({});
  receiptsMock.value = apiReceipts.value
    .map(r => ({ ...r, matched: false }));
};

// --- COMPOSABLE ---
const {
  rawTransactions,
  activeTab,
  documentSearch: receiptSearch,
  transactionSearch,
  selectedDocumentIds: selectedReceiptIds,
  selectedTransactionIds,
  selectedCandidateIds,
  showConfirmMatch,
  confirmMatchResolve,
  confirmMatchAmount,
  unmatchedTransactions,
  unmatchedDocuments: baseUnmatchedReceipts,
  selectedTransactionSum,
  selectedDocumentSum: selectedReceiptSum,
  matchingDifference,
  suggestedDocumentIds: suggestedReceiptIds,
  candidatePairs: baseCandidatePairs,
  matchedPairs: baseMatchedPairs,
  matchedCount,
  loadData,
  selectTransaction,
  selectDocument: selectReceipt,
  toggleCandidate,
  handleMatch,
  handleBulkMatch,
  revertToUnmatched,
} = useDocumentMatching({
  fetchDocumentsFn: fetchAndMapReceipts,
  documents: receiptsMock,
  matchType: 'receipt',
  getAmount: r => r.amount,
  getDescription: r => `${r.payee ?? ''} ${r.submitter_name ?? r.submitted_by ?? ''} ${r.amount}`,
  transactionTypeFilter: shallowRef('debit' as const),
});

// --- APPLICANT CANDIDATES ---
interface ApplicantReceipt {
  id: string
  payee?: string
  amount: number
  date?: string
  submitter_name?: string
}
interface ApplicantCandidate {
  transaction: { id: string; date?: string; description?: string; amount: number; type?: string; transaction_date?: string }
  employee: { id: string; name: string; bank_display_name?: string } | null
  receipts: ApplicantReceipt[]
  confidence: number
  match_reason: string
}

const applicantCandidates = ref<ApplicantCandidate[]>([])
const isLoadingApplicants = ref(false)
const matchingApplicantId = ref<string | null>(null)

const fetchApplicantCandidates = async () => {
  isLoadingApplicants.value = true
  try {
    applicantCandidates.value = await api.get<ApplicantCandidate[]>('/matches/candidates/by-applicant')
  } catch {
    // silent — applicant matching is optional
  } finally {
    isLoadingApplicants.value = false
  }
}

const handleApplicantMatch = async (candidate: ApplicantCandidate) => {
  if (!confirm(`「${candidate.employee?.name ?? '不明'}」の取引明細と領収書 ${candidate.receipts.length} 件を消込しますか？`)) return
  matchingApplicantId.value = candidate.transaction.id
  try {
    await api.post('/matches', {
      match_type: 'receipt',
      transaction_ids: [candidate.transaction.id],
      document_ids: candidate.receipts.map((r: ApplicantReceipt) => r.id),
      matched_by: 'ai',
      auto_suggested: true,
    })
    await Promise.all([loadData(), fetchApplicantCandidates()])
  } catch (e: any) {
    alert(`消込に失敗しました: ${e.message}`)
  } finally {
    matchingApplicantId.value = null
  }
}

onMounted(() => {
  loadData()
  fetchApplicantCandidates()
});

// --- PAGE-LOCAL STATE ---
// 展開（アコーディオン）はUI固有のためページに残す
const expandedReceiptIds = ref<string[]>([]);

// --- LOCAL COMPUTED ---

// 金額が一致する領収書を先頭に並び替え（receipt 固有の UX）
const unmatchedReceipts = computed(() => {
  if (selectedTransactionIds.value.length === 0) return baseUnmatchedReceipts.value;
  const targetSum = selectedTransactionSum.value;
  return [...baseUnmatchedReceipts.value].sort((a, b) => {
    const aMatch = a.amount === targetSum;
    const bMatch = b.amount === targetSum;
    return aMatch === bMatch ? 0 : aMatch ? -1 : 1;
  });
});

// テンプレートで pair.receipt を参照するためのエイリアス
const displayCandidatePairs = computed(() =>
  baseCandidatePairs.value.map(p => ({ ...p, receipt: p.document as MatchingEntry }))
);
const displayMatchedPairs = computed(() =>
  baseMatchedPairs.value.map(p => ({ ...p, receipt: p.document as MatchingEntry }))
);

// --- ACTIONS ---
const toggleReceiptExpansion = (id: string) => {
  const idx = expandedReceiptIds.value.indexOf(id);
  if (idx > -1) expandedReceiptIds.value.splice(idx, 1);
  else expandedReceiptIds.value.push(id);
};
</script>

<template>
  <div class="space-y-6 h-full flex flex-col">
    <!-- Header -->
    <div class="flex flex-col gap-4 shrink-0">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">経費消込</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          「データアップロード」画面で取り込まれた明細データと、提出された領収書データを突合（マッチング）し、仕訳を確定します。<br/>
          ※ 銀行明細はすべての決済手段の領収書と、カード明細はカード払いの領収書と突合できます。
        </p>
      </div>
      <!-- Tabs -->
      <div :class="MATCHING_STYLES.tabContainer">
        <button
            @click="activeTab = 'unmatched'"
            :class="[MATCHING_STYLES.tabBase, activeTab === 'unmatched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]"
        >
            未結合 ({{ unmatchedTransactions.length }})
        </button>
        <button
            @click="activeTab = 'candidates'"
            :class="[MATCHING_STYLES.tabBase, activeTab === 'candidates' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive, 'flex items-center gap-1.5 relative']"
        >
            <div v-if="displayCandidatePairs.length > 0" class="absolute top-2 right-4 md:right-auto md:-top-1 md:-right-1 w-3 h-3 bg-red-500 rounded-full border-2 border-white animate-pulse"></div>
            ✨ 自動結合候補 ({{ displayCandidatePairs.length }})
        </button>
        <button
            @click="activeTab = 'matched'"
            :class="[MATCHING_STYLES.tabBase, activeTab === 'matched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive, 'flex items-center gap-1.5']"
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
          <div v-if="selectedTransactionIds.length > 0 && selectedReceiptIds.length > 0" :class="MATCHING_STYLES.guidanceBarActive">
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
              <button @click="handleMatch" :class="['w-full md:w-auto', MATCHING_STYLES.matchButton]">
                  <CheckCircle class="w-5 h-5" />
                  <span>この内容で結合する</span>
              </button>
          </div>

          <!-- 2. Guidance Banner (Transaction selected, NO receipt selected) -->
          <div v-else-if="selectedTransactionIds.length > 0 && selectedReceiptIds.length === 0" :class="MATCHING_STYLES.guidanceBarWarning">
              <span class="flex h-6 w-6 items-center justify-center rounded-full bg-amber-200 text-amber-900 text-sm font-bold border border-amber-400 shrink-0 shadow-sm animate-pulse">!</span>
              <div>
                  <p class="font-bold">右の明細 (計 ¥{{ formatAmount(selectedTransactionSum) }}) に対応する領収書を、左のリストから選択してください。</p>
              </div>
          </div>

          <!-- 3. Default Empty Banner (NO transaction selected) -->
          <div v-else :class="MATCHING_STYLES.guidanceBarDefault">
              <Link2 class="h-5 w-5 opacity-50" />
              <p class="font-medium text-sm">マッチングを開始するには、左のリストから領収書を選択してください（または右の明細を選択）。</p>
          </div>
      </div>
      


      <!-- Main Split Layout -->
      <div class="flex-1 flex flex-col lg:flex-row gap-6 min-h-0">
        
        <!-- Left Pane: Receipts -->
        <div :class="MATCHING_STYLES.paneBase">
            <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-blue-50/50']">
                <div class="flex items-center gap-2">
                    <FileText class="text-blue-700 h-5 w-5" />
                    <h2 class="font-bold text-gray-800 text-base">領収書データ (要マッチング)</h2>
                    <span class="bg-blue-100 text-blue-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedReceipts.length }}</span>
                </div>
            </div>
            
            <div class="p-3 border-b border-gray-100 shrink-0">
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input v-model="receiptSearch" type="text" placeholder="発行元・提出者・金額で検索..." :class="MATCHING_STYLES.searchInput" />
                </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-blue-50/10 relative">
                <!-- Receipt Cards -->
                <div
                    v-for="r in unmatchedReceipts" :key="r.id"
                    @click="selectReceipt(r.id)"
                    :class="[
                        MATCHING_STYLES.cardBase, 'flex flex-col justify-between min-h-[105px]',
                        selectedReceiptIds.includes(r.id) ? MATCHING_STYLES.cardSelected : '',
                        suggestedReceiptIds.includes(r.id) && !selectedReceiptIds.includes(r.id) ? MATCHING_STYLES.cardSuggested : ''
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
                                {{ r.payment_method }}
                            </span>
                            <span class="text-xs text-gray-500 font-medium">{{ r.date }}</span>
                        </div>
                        <p class="text-lg font-bold tracking-tight text-gray-900 whitespace-nowrap ml-4">¥{{ formatAmount(r.amount) }}</p>
                    </div>

                    <div class="flex justify-between items-end">
                        <div class="min-w-0 pr-4">
                            <p class="text-sm font-bold text-gray-900 leading-tight truncate w-[220px]" :title="r.payee">{{ r.payee }}</p>

                            <div class="flex items-center gap-2 mt-2">
                                <div class="h-5 w-5 rounded-full bg-slate-200 flex items-center justify-center text-[9px] font-bold text-slate-600">
                                    {{ (r.submitter_name ?? r.submitted_by ?? '?').charAt(0) }}
                                </div>
                                <p class="text-[13px] text-gray-600 font-medium">{{ r.submitter_name ?? r.submitted_by ?? '不明' }}</p>
                            </div>
                        </div>
                        <div class="shrink-0 flex flex-col items-end gap-2">
                            <span v-if="r.approval_status === 'approved' || r.approval_status === 'auto_approved'" class="text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2 py-1 rounded border border-emerald-200">承認済</span>
                            <span v-else-if="!['approved', 'auto_approved', 'rejected'].includes(r.approval_status)" class="text-[11px] font-bold text-blue-700 bg-blue-50 px-2 py-1 rounded border border-blue-200 flex items-center"><Clock class="w-3.5 h-3.5 mr-1 text-blue-500"/>承認進行中</span>
                            
                            <!-- Accordion Toggle Button -->
                            <button
                                v-if="r.line_items && r.line_items.length > 0"
                                @click.stop="toggleReceiptExpansion(r.id)"
                                class="text-gray-400 hover:text-blue-600 p-1 rounded transition-colors flex items-center justify-center bg-gray-50 hover:bg-blue-50 border border-gray-200"
                            >
                                <ChevronUp v-if="expandedReceiptIds.includes(r.id)" class="w-4 h-4" />
                                <ChevronDown v-else class="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                    
                    <!-- Line Items Accordion Panel -->
                    <div v-if="expandedReceiptIds.includes(r.id) && r.line_items && r.line_items.length > 0" class="mt-4 pt-3 border-t border-gray-100/50 bg-gray-50/50 -mx-2 px-2 rounded-lg">
                        <p class="text-[11px] font-bold text-gray-500 mb-2 flex items-center">
                            <FileText class="w-3 h-3 mr-1" /> 内訳 ({{ r.line_items.length }}件)
                        </p>
                        <div class="space-y-2">
                            <div v-for="(item, idx) in r.line_items" :key="item.id ?? idx" class="flex items-start justify-between text-xs bg-white p-2 rounded border border-gray-100 shadow-sm">
                                <div class="break-words w-2/3 pr-2">
                                    <div class="font-bold text-gray-700 mb-0.5">{{ item.description }}</div>
                                    <div class="text-[10px] bg-gray-100 text-gray-600 px-1 py-0.5 rounded inline-block">{{ item.category ?? item.account_subject ?? '未分類' }}</div>
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
            <div :class="MATCHING_STYLES.centerIcon">
                <Link2 class="h-5 w-5 text-blue-500" />
            </div>
        </div>

        <!-- Right Pane: Transactions -->
        <div :class="MATCHING_STYLES.paneBase">
            <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-slate-50']">
                <div class="flex items-center gap-2">
                    <Building2 class="text-slate-600 h-5 w-5" />
                    <h2 class="font-bold text-gray-800 text-base">口座・カード明細 (未結合)</h2>
                    <span class="bg-slate-200 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ unmatchedTransactions.length }}</span>
                </div>
            </div>
            
            <div class="p-3 border-b border-gray-100 shrink-0">
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input v-model="transactionSearch" type="text" placeholder="摘要・金額で検索..." :class="MATCHING_STYLES.searchInput" />
                </div>
            </div>

            <div class="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-50/30">
                <div v-if="rawTransactions.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400 py-12">
                    <Upload class="h-12 w-12 mb-3 text-gray-300" />
                    <p class="text-sm font-medium text-gray-600">明細データが存在しません</p>
                    <p class="text-xs mt-1">上部の取得ボタンからデータを取り込んでください</p>
                </div>
                
                <!-- Transaction Cards -->
                <div
                    v-for="t in unmatchedTransactions" :key="t.id"
                    @click="selectTransaction(t.id)"
                    :class="[MATCHING_STYLES.cardBase, 'flex flex-col justify-between min-h-[90px]', selectedTransactionIds.includes(t.id) ? MATCHING_STYLES.cardSelected : '']"
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
                        <p class="text-sm font-bold text-gray-800 leading-tight">{{ t.description }} <span v-if="t.type === 'card'" class="text-[10px] bg-purple-50 text-purple-600 border border-purple-200 px-1.5 py-0.5 rounded font-medium">カード</span><span v-else class="text-[10px] bg-blue-50 text-blue-600 border border-blue-200 px-1.5 py-0.5 rounded font-medium">銀行</span></p>
                    </div>
                </div>
            </div>
        </div>
      </div>
    </template>

    <!-- Candidate Tab Content -->
    <template v-else-if="activeTab === 'candidates'">
      <div class="flex flex-col h-full relative">
        <div class="flex-1 overflow-y-auto no-scrollbar pb-24">
            <div v-if="displayCandidatePairs.length === 0 && applicantCandidates.length === 0 && !isLoadingApplicants" class="flex flex-col items-center justify-center h-full text-gray-400 py-20 bg-white rounded-xl border border-gray-200 shadow-sm">
                <Link2 class="h-16 w-16 mb-4 text-gray-200" />
                <p class="text-base font-medium text-gray-500">自動結合できる候補はありません。</p>
            </div>

            <div v-else class="space-y-4">
                <div
                    v-for="pair in displayCandidatePairs" :key="pair.transaction.id"
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
                                        {{ pair.receipt?.payment_method || '提出領収書' }}
                                    </span>
                                    <span class="text-xs text-gray-500 font-medium">{{ pair.receipt?.date }}</span>
                                </div>
                            </div>
                            <p class="text-base font-bold text-gray-900 truncate" :title="pair.receipt?.payee">{{ pair.receipt?.payee }}</p>
                            <p class="text-xs text-gray-500 mt-1 flex items-center gap-1">
                                <FileText class="h-3 w-3" /> {{ pair.receipt?.submitter_name ?? pair.receipt?.submitted_by ?? '不明' }}
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

        <!-- Applicant-based Candidates Section -->
        <div v-if="applicantCandidates.length > 0 || isLoadingApplicants" class="mt-6">
            <div class="flex items-center gap-2 mb-3 px-1">
              <User class="h-4 w-4 text-violet-500" />
              <h3 class="text-sm font-bold text-gray-700">申請者マッチング候補</h3>
              <span class="text-xs text-gray-400">振込名義から申請者の領収書を紐付け</span>
              <span v-if="isLoadingApplicants" class="ml-2 text-xs text-gray-400">読み込み中...</span>
            </div>
            <div class="space-y-3">
              <div
                v-for="c in applicantCandidates" :key="c.transaction.id"
                class="bg-violet-50/40 rounded-xl border border-violet-200 p-4 flex flex-col md:flex-row items-start md:items-center gap-4"
              >
                <!-- Transaction -->
                <div class="flex-1 min-w-0">
                  <p class="text-xs text-gray-500 mb-0.5">{{ c.transaction.transaction_date ?? c.transaction.date ?? '—' }}</p>
                  <p class="text-sm font-bold text-gray-900 truncate" :title="c.transaction.description">{{ c.transaction.description }}</p>
                  <p class="text-lg font-bold text-violet-700 mt-1">¥{{ formatAmount(c.transaction.amount) }}</p>
                </div>

                <!-- Arrow + Employee -->
                <div class="shrink-0 flex flex-col items-center gap-1">
                  <div class="bg-violet-100 rounded-full p-1.5">
                    <User class="h-4 w-4 text-violet-600" />
                  </div>
                  <p class="text-xs font-bold text-violet-700">{{ c.employee?.name ?? '—' }}</p>
                  <p v-if="c.employee?.bank_display_name" class="text-[10px] text-gray-500">{{ c.employee.bank_display_name }}</p>
                  <span class="text-[10px] bg-violet-100 text-violet-700 px-1.5 py-0.5 rounded font-medium">
                    信頼度 {{ Math.round((c.confidence ?? 0) * 100) }}%
                  </span>
                </div>

                <!-- Receipts -->
                <div class="flex-1 min-w-0">
                  <p class="text-xs text-gray-500 mb-1">領収書 {{ c.receipts.length }} 件</p>
                  <div class="space-y-1">
                    <div v-for="r in c.receipts.slice(0, 3)" :key="r.id" class="flex justify-between text-xs">
                      <span class="truncate text-gray-700 max-w-[120px]" :title="r.payee">{{ r.payee ?? '—' }}</span>
                      <span class="font-medium text-gray-900 shrink-0 ml-2">¥{{ formatAmount(r.amount) }}</span>
                    </div>
                    <p v-if="c.receipts.length > 3" class="text-xs text-gray-400">他 {{ c.receipts.length - 3 }} 件...</p>
                  </div>
                </div>

                <!-- Action -->
                <div class="shrink-0">
                  <button
                    @click="handleApplicantMatch(c)"
                    :disabled="matchingApplicantId === c.transaction.id"
                    class="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <CheckCircle class="h-4 w-4" />
                    {{ matchingApplicantId === c.transaction.id ? '処理中...' : '消込実行' }}
                  </button>
                </div>
              </div>
            </div>
        </div>
        </div><!-- /overflow-y-auto -->

        <!-- Floating Bulk Action Bar -->
        <div v-if="displayCandidatePairs.length > 0" class="absolute bottom-4 left-0 right-0 bg-gray-900 text-white p-4 rounded-xl shadow-xl flex flex-col md:flex-row items-center justify-between gap-4 animate-in slide-in-from-bottom border border-gray-700 z-20">
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
        <div v-if="displayMatchedPairs.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400 py-20 bg-white rounded-xl border border-gray-200 shadow-sm">
            <Link2 class="h-16 w-16 mb-4 text-gray-200" />
            <p class="text-base font-medium text-gray-500">結合済みのデータはありません。</p>
            <p class="text-sm mt-1 text-gray-400">「未結合」タブで明細と領収書をマッチングしてください。</p>
        </div>

        <div v-else class="space-y-4">
            <div
                v-for="pair in displayMatchedPairs" :key="pair.transaction.id"
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
                                {{ pair.receipt?.payment_method || '提出領収書' }}
                            </span>
                             <span class="text-xs text-gray-500 font-medium">{{ pair.receipt?.date }}</span>
                         </div>
                    </div>
                    <p class="text-base font-bold text-gray-900 truncate" :title="pair.receipt?.payee">{{ pair.receipt?.payee }}</p>
                    <p class="text-xs text-gray-500 mt-1 flex items-center gap-1">
                        <FileText class="h-3 w-3" /> {{ pair.receipt?.submitter_name ?? pair.receipt?.submitted_by ?? '不明' }}
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
