<script setup lang="ts">
import { onMounted, nextTick } from 'vue';
import {
  FileText,
  CheckCircle,
  Link2,
  Search,
  Upload,
  ChevronDown,
  ChevronUp,
  User,
} from 'lucide-vue-next';
import { useExpenseMatching } from '@/composables/useExpenseMatching';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import { MATCHING_STYLES } from '@/constants/matchingStyles';
import { ref } from 'vue';

const {
  isLoading,
  activeTab,
  groupSearch,
  transactionSearch,
  receiptGroups,
  sortedReceiptGroups,
  unmatchedDebitTransactions,
  sortedDebitTransactions,
  selectedGroupUserId,
  selectedTransactionId,
  selectedGroup,
  selectedTransaction,
  difference,
  matchedExpenses,
  isMatching,
  loadData,
  selectGroup,
  selectTransaction,
  handleMatch,
  revertMatch,
} = useExpenseMatching();

onMounted(loadData);

// 両ペインスクロールリセット
const groupScrollPane = ref<HTMLElement | null>(null);
const txScrollPane = ref<HTMLElement | null>(null);

const scrollBothToTop = () => nextTick(() => {
  groupScrollPane.value?.scrollTo({ top: 0 });
  txScrollPane.value?.scrollTo({ top: 0 });
});

const handleSelectGroup = (userId: string) => {
  selectGroup(userId);
  scrollBothToTop();
};

const handleSelectTransaction = (txId: string) => {
  selectTransaction(txId);
  scrollBothToTop();
};

// アコーディオン（グループ内の領収書展開）
const expandedGroupIds = ref<Set<string>>(new Set());
const toggleExpand = (userId: string) => {
  const next = new Set(expandedGroupIds.value);
  next.has(userId) ? next.delete(userId) : next.add(userId);
  expandedGroupIds.value = next;
};

const formatDate = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit' }) : '—';
</script>

<template>
  <div class="space-y-4 h-full flex flex-col">

    <!-- Header -->
    <div class="shrink-0">
      <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">経費消込</h1>
      <p class="text-sm text-gray-500 mt-2">
        申請者ごとにグルーピングされた領収書と、振込出金明細を突合して消込を確定します。
      </p>
    </div>

    <!-- Tabs -->
    <div :class="MATCHING_STYLES.tabContainer">
      <button
        @click="activeTab = 'unmatched'"
        :class="[MATCHING_STYLES.tabBase, activeTab === 'unmatched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]"
      >
        未消込
        <span class="ml-1.5 bg-amber-100 text-amber-700 text-xs font-bold px-1.5 py-0.5 rounded-full">
          {{ receiptGroups.length }}
        </span>
      </button>
      <button
        @click="activeTab = 'matched'"
        :class="[MATCHING_STYLES.tabBase, 'flex items-center justify-center gap-1.5', activeTab === 'matched' ? MATCHING_STYLES.tabActive : MATCHING_STYLES.tabInactive]"
      >
        <CheckCircle v-if="matchedExpenses.length > 0" class="h-4 w-4 text-emerald-500" />
        消込済み ({{ matchedExpenses.length }})
      </button>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex-1 flex items-center justify-center text-gray-400 text-sm">
      読み込み中...
    </div>

    <!-- ── 未消込タブ ─────────────────────────────────── -->
    <template v-else-if="activeTab === 'unmatched'">

      <!-- Match Action Bar -->
      <div v-if="selectedGroup && selectedTransaction"
        :class="['shrink-0', MATCHING_STYLES.guidanceBarActive]">
        <div class="flex items-start gap-3">
          <div class="bg-white/20 p-2 rounded-full hidden sm:block mt-0.5">
            <Link2 class="h-5 w-5" />
          </div>
          <div>
            <div class="flex items-center gap-2 mb-1">
              <p class="font-bold text-lg">消込準備完了</p>
              <span v-if="difference === 0" class="text-xs bg-emerald-500 px-2 py-0.5 rounded-full font-bold">金額一致</span>
              <span v-else class="text-xs bg-amber-500 px-2 py-0.5 rounded-full font-bold">差額あり</span>
            </div>
            <div class="flex items-center gap-4 text-sm text-blue-100">
              <span><span class="font-bold text-white">{{ selectedGroup.userName }}</span> の領収書 {{ selectedGroup.receipts.length }}件</span>
              <span>合計 <strong class="text-white">¥{{ formatAmount(selectedGroup.total) }}</strong></span>
              <span>振込 <strong class="text-white">¥{{ formatAmount(selectedTransaction.amount) }}</strong></span>
              <span v-if="difference !== 0" class="text-amber-300 font-bold">
                差額 ¥{{ formatAmount(Math.abs(difference!)) }}
              </span>
            </div>
          </div>
        </div>
        <button
          @click="handleMatch"
          :disabled="isMatching"
          :class="['w-full md:w-auto disabled:opacity-50 disabled:cursor-not-allowed', MATCHING_STYLES.matchButton]"
        >
          <CheckCircle class="h-5 w-5" />
          {{ isMatching ? '処理中...' : 'この内容で消込する' }}
        </button>
      </div>

      <!-- Two-pane layout -->
      <div class="flex-1 flex flex-col lg:flex-row gap-4 min-h-0">

        <!-- Left: Receipt Groups -->
        <div :class="MATCHING_STYLES.paneBase">
          <!-- Header -->
          <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-indigo-50']">
            <div class="flex items-center gap-2">
              <User class="h-5 w-5 text-indigo-500" />
              <h2 class="font-bold text-gray-800 text-base">申請者</h2>
              <span class="text-xs bg-indigo-100 text-indigo-700 font-bold px-2 py-0.5 rounded-full">{{ receiptGroups.length }}</span>
            </div>
          </div>
          <!-- Search -->
          <div class="p-3 border-b border-gray-100 shrink-0">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input v-model="groupSearch" type="text" placeholder="氏名・店舗名で検索..."
                :class="MATCHING_STYLES.searchInput" />
            </div>
          </div>
          <!-- Groups -->
          <div ref="groupScrollPane" class="flex-1 overflow-y-auto p-3 space-y-2">
            <div v-if="receiptGroups.length === 0"
              class="flex flex-col items-center justify-center h-full text-gray-400 py-16">
              <Upload class="h-12 w-12 mb-3 text-gray-200" />
              <p class="text-sm font-medium text-gray-500">消込対象の領収書がありません</p>
            </div>

            <div
              v-for="group in sortedReceiptGroups" :key="group.userId"
              class="overflow-hidden"
              :class="[MATCHING_STYLES.cardBase, selectedGroupUserId === group.userId ? MATCHING_STYLES.cardSelected : '']"
            >
              <!-- Selected accent bar -->
              <div v-if="selectedGroupUserId === group.userId"
                class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
              <!-- Selected checkmark -->
              <div v-if="selectedGroupUserId === group.userId"
                class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                <CheckCircle class="w-4 h-4" />
              </div>

              <!-- Card body -->
              <div
                @click="handleSelectGroup(group.userId)"
                class="flex items-center gap-3 cursor-pointer"
              >
                <!-- User Icon -->
                <div class="shrink-0 w-9 h-9 rounded-full bg-indigo-100 flex items-center justify-center">
                  <User class="h-5 w-5 text-indigo-600" />
                </div>
                <!-- Info -->
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-bold text-gray-900">{{ group.userName }}</p>
                  <p class="text-xs text-gray-500">領収書 {{ group.receipts.length }}件</p>
                </div>
                <!-- Total -->
                <div class="shrink-0 text-right mr-6">
                  <p class="text-lg font-bold tracking-tight text-gray-900">¥{{ formatAmount(group.total) }}</p>
                </div>
                <!-- Expand toggle -->
                <button
                  @click.stop="toggleExpand(group.userId)"
                  class="shrink-0 text-gray-400 hover:text-gray-600 p-1"
                >
                  <ChevronUp v-if="expandedGroupIds.has(group.userId)" class="h-4 w-4" />
                  <ChevronDown v-else class="h-4 w-4" />
                </button>
              </div>

              <!-- Accordion: receipt details -->
              <div v-if="expandedGroupIds.has(group.userId)" class="border-t border-gray-100 divide-y divide-gray-50">
                <div
                  v-for="r in group.receipts" :key="r.id"
                  class="flex items-center gap-3 px-4 py-2.5 bg-gray-50/50 text-xs"
                >
                  <FileText class="h-3.5 w-3.5 text-gray-400 shrink-0" />
                  <span class="flex-1 text-gray-700 truncate" :title="r.payee">{{ r.payee }}</span>
                  <span class="text-gray-500 whitespace-nowrap">{{ formatDate(r.date) }}</span>
                  <span class="font-bold text-gray-800 whitespace-nowrap">¥{{ formatAmount(r.amount) }}</span>
                </div>
                <div class="flex justify-end px-4 py-2 bg-indigo-50/50">
                  <span class="text-xs font-bold text-indigo-700">合計 ¥{{ formatAmount(group.total) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Center icon (desktop) -->
        <div class="hidden lg:flex flex-col items-center justify-center shrink-0 -mx-1">
          <div :class="MATCHING_STYLES.centerIcon">
            <Link2 class="h-5 w-5 text-blue-500" />
          </div>
        </div>

        <!-- Right: Debit Transactions -->
        <div :class="MATCHING_STYLES.paneBase">
          <!-- Header -->
          <div :class="[MATCHING_STYLES.paneHeaderBase, 'bg-slate-50']">
            <div class="flex items-center gap-2">
              <span class="text-sm font-bold text-gray-700">振込出金明細</span>
              <span class="text-xs bg-slate-200 text-slate-700 font-bold px-2 py-0.5 rounded-full">{{ unmatchedDebitTransactions.length }}</span>
            </div>
          </div>
          <!-- Search -->
          <div class="p-3 border-b border-gray-100 shrink-0">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input v-model="transactionSearch" type="text" placeholder="摘要・金額で検索..."
                :class="MATCHING_STYLES.searchInput" />
            </div>
          </div>
          <!-- Transactions -->
          <div ref="txScrollPane" class="flex-1 overflow-y-auto p-3 space-y-2">
            <div v-if="unmatchedDebitTransactions.length === 0"
              class="flex flex-col items-center justify-center h-full text-gray-400 py-16">
              <Upload class="h-12 w-12 mb-3 text-gray-200" />
              <p class="text-sm font-medium text-gray-500">未消込の振込出金明細がありません</p>
            </div>

            <div
              v-for="tx in sortedDebitTransactions" :key="tx.id"
              @click="handleSelectTransaction(tx.id)"
              :class="[MATCHING_STYLES.cardBase, 'flex items-center gap-3 min-h-[72px]', selectedTransactionId === tx.id ? MATCHING_STYLES.cardSelected : '']"
            >
              <div v-if="selectedTransactionId === tx.id"
                class="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500"></div>
              <div v-if="selectedTransactionId === tx.id"
                class="absolute top-2 right-2 bg-blue-600 text-white rounded-full p-0.5 shadow-sm">
                <CheckCircle class="w-4 h-4" />
              </div>
              <!-- Info -->
              <div class="flex-1 min-w-0">
                <p class="text-sm font-bold text-gray-900 truncate" :title="tx.description">{{ tx.description }}</p>
                <p class="text-xs text-gray-500 mt-0.5">{{ tx.transaction_date }} · {{ tx.account_name }}</p>
              </div>
              <!-- Amount -->
              <p class="shrink-0 text-lg font-bold tracking-tight text-gray-900 pr-6">¥{{ formatAmount(tx.amount) }}</p>
            </div>
          </div>
        </div>

      </div>
    </template>

    <!-- ── 消込済みタブ ────────────────────────────────── -->
    <template v-else-if="activeTab === 'matched'">
      <div class="flex-1 overflow-y-auto space-y-3 pb-8">
        <div v-if="matchedExpenses.length === 0"
          class="flex flex-col items-center justify-center py-24 bg-white rounded-xl border border-gray-200 shadow-sm text-gray-400">
          <CheckCircle class="h-16 w-16 mb-4 text-gray-200" />
          <p class="text-base font-medium text-gray-500">消込済みデータはありません</p>
        </div>

        <div
          v-for="item in matchedExpenses" :key="item.matchId"
          class="bg-white border border-emerald-200 rounded-xl shadow-sm relative overflow-hidden"
        >
          <!-- Left accent -->
          <div class="absolute left-0 top-0 bottom-0 w-1.5 bg-emerald-500"></div>

          <!-- Main row -->
          <div class="pl-5 pr-4 py-4 flex flex-col md:flex-row items-start md:items-center gap-4">

            <!-- Group info -->
            <div class="flex items-center gap-3 flex-1 min-w-0">
              <div class="shrink-0 w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center">
                <User class="h-5 w-5 text-emerald-600" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-bold text-gray-900">{{ item.group.userName }}</p>
                <p class="text-xs text-gray-500 mt-0.5">領収書 {{ item.group.receipts.length }}件</p>
              </div>
            </div>

            <!-- Link icon -->
            <div class="shrink-0 flex flex-col items-center">
              <div class="bg-emerald-100 text-emerald-600 rounded-full p-1.5">
                <CheckCircle class="h-4 w-4" />
              </div>
              <p class="text-[10px] font-bold text-emerald-700 mt-1">消込済</p>
            </div>

            <!-- Transaction info -->
            <div class="flex-1 min-w-0">
              <p class="text-xs text-gray-500">{{ item.transaction.transaction_date }}</p>
              <p class="text-sm font-bold text-gray-900 truncate" :title="item.transaction.description">
                {{ item.transaction.description }}
              </p>
              <p class="text-xs text-gray-400">{{ item.transaction.account_name }}</p>
            </div>

            <!-- Amount -->
            <div class="shrink-0 text-right">
              <p class="text-base font-bold text-gray-900">¥{{ formatAmount(item.transaction.amount) }}</p>
            </div>

            <!-- Accordion toggle + Revert -->
            <div class="shrink-0 flex items-center gap-1">
              <button
                @click="toggleExpand(item.matchId)"
                class="text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-100 px-2 py-1.5 rounded-lg transition-colors border border-transparent hover:border-gray-200 flex items-center gap-1"
              >
                <ChevronUp v-if="expandedGroupIds.has(item.matchId)" class="h-3.5 w-3.5" />
                <ChevronDown v-else class="h-3.5 w-3.5" />
                明細
              </button>
              <button
                @click="revertMatch(item.matchId)"
                class="text-xs text-gray-400 hover:text-red-600 hover:bg-red-50 px-2 py-1.5 rounded-lg transition-colors border border-transparent hover:border-red-200"
              >
                解除
              </button>
            </div>
          </div>

          <!-- Accordion: receipt details -->
          <div v-if="expandedGroupIds.has(item.matchId)"
            class="border-t border-emerald-100 divide-y divide-gray-50">
            <div
              v-for="r in item.group.receipts" :key="r.id"
              class="flex items-center gap-3 pl-5 pr-4 py-2.5 bg-emerald-50/30 text-xs"
            >
              <FileText class="h-3.5 w-3.5 text-gray-400 shrink-0" />
              <span class="flex-1 text-gray-700 truncate" :title="r.payee">{{ r.payee }}</span>
              <span class="text-gray-500 whitespace-nowrap">{{ formatDate(r.date) }}</span>
              <span class="font-bold text-gray-800 whitespace-nowrap">¥{{ formatAmount(r.amount) }}</span>
            </div>
            <div class="flex justify-end pl-5 pr-4 py-2 bg-emerald-50/50">
              <span class="text-xs font-bold text-emerald-700">合計 ¥{{ formatAmount(item.group.total) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>

  </div>
</template>
