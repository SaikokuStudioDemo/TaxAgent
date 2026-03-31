<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import {
  CheckCircle,
  XCircle,
  Clock,
  FileText,
  Search,
  Filter,
  AlertCircle,
  FolderKanban,
  Building2
} from 'lucide-vue-next';
import { useInvoices, type Invoice } from '@/composables/useInvoices';
import { useDocumentApproval } from '@/composables/useDocumentApproval';
import InvoiceDetailModal from '@/components/invoices/InvoiceDetailModal.vue';
import { buildApprovalHistory } from '@/composables/useApprovalHistory';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

// --- STATE ---
const { invoices, pendingForMe, fetchInvoices, fetchPendingForMe } = useInvoices();
// 受領/発行の切り替えは請求書固有のロジックなのでページに残す
const activeDirection = ref<'received' | 'issued'>('issued');

const loadData = async () => {
    const requestedDirection = activeDirection.value;
    await Promise.all([
        fetchInvoices({ document_type: requestedDirection }),
        fetchPendingForMe(),
    ]);
    // Prevent race condition if user rapid-clicked tabs
    if (activeDirection.value !== requestedDirection) return;
};

onMounted(loadData);
watch(activeDirection, loadData);

const {
  activeTab,
  searchQuery,
  pendingList: pendingInvoices,
  pendingAllList: pendingAllInvoices,
  approvedList: approvedInvoices,
  displayedItems: displayedInvoices,
  metrics,
  selectedItem: selectedInvoice,
  isDetailModalOpen,
  openDetail,
  closeDetail,
  handleActionCompleted,
} = useDocumentApproval<Invoice>({
  fetchFn: loadData,
  items: invoices,
  pendingItems: pendingForMe,
  getApprovalStatus: i => i.approval_status,
  getAmount: i => i.total_amount,
  urgentThreshold: 100000,
  getSearchableText: i => [i.client_name, i.vendor_name, i.invoice_number, i.total_amount?.toString(), i.creator_name].filter(Boolean).join(' '),
});

// 承認ステップ表示用ヘルパー（請求書固有）
const getApprovalHistory = (inv: Invoice) =>
    buildApprovalHistory(inv.approval_steps ?? [], inv.approval_history ?? [], inv.approval_status);

const handleStepAdded = (updated: Invoice) => {
  const idx = invoices.value.findIndex(i => i.id === updated.id);
  if (idx !== -1) invoices.value[idx] = { ...invoices.value[idx], extra_approval_steps: updated.extra_approval_steps };
  const pidx = pendingForMe.value.findIndex(i => i.id === updated.id);
  if (pidx !== -1) pendingForMe.value[pidx] = { ...pendingForMe.value[pidx], extra_approval_steps: updated.extra_approval_steps };
};

</script>

<template>
  <div class="space-y-6">
    <!-- Header Area -->
    <header class="bg-white border-b border-gray-200 px-8 py-6 -mx-6 -mt-6">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">請求書承認状況</h1>
          <p class="text-sm text-gray-500 mt-1">
            {{ activeDirection === 'received' ? '仕入先から届いた請求書の支払内容を確認し、承認を行います' : '発行を予定している請求書の内容を確認し、承認を行います' }}
          </p>
        </div>
      </div>
    </header>

    <div class="mt-6"></div>

    <!-- Direction Toggle (Full Width) -->
    <div class="flex bg-gray-200/50 p-1.5 rounded-xl mb-6 shadow-inner border border-gray-200/50">
        <button
          @click="activeDirection = 'received'"
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeDirection === 'received' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <Clock class="w-4 h-4" />
          受領請求書
        </button>
        <button
          @click="activeDirection = 'issued'"
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeDirection === 'issued' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <CheckCircle class="w-4 h-4" />
          発行請求書
        </button>
    </div>

    <!-- Quick Metrics -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex items-center justify-between hover:shadow-md transition-shadow cursor-pointer" @click="activeTab = 'pending'">
            <div>
                <p class="text-sm font-medium text-gray-500 mb-1">あなたの承認待ち</p>
                <div class="flex items-baseline gap-2">
                    <span class="text-3xl font-bold" :class="metrics.pendingCount > 0 ? 'text-blue-600' : 'text-gray-900'">{{ metrics.pendingCount }}</span>
                    <span class="text-sm text-gray-500 font-medium">件</span>
                </div>
            </div>
            <div class="h-12 w-12 rounded-full bg-blue-50 flex items-center justify-center">
                <Clock class="text-blue-600" :size="24" />
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex items-center justify-between hover:shadow-md transition-shadow">
            <div>
                <p class="text-sm font-medium text-gray-500 mb-1">高額/要注意アラート</p>
                <div class="flex items-baseline gap-2">
                    <span class="text-3xl font-bold" :class="metrics.urgentCount > 0 ? 'text-amber-500' : 'text-gray-900'">{{ metrics.urgentCount }}</span>
                    <span class="text-sm text-gray-500 font-medium">件</span>
                </div>
            </div>
            <div class="h-12 w-12 rounded-full bg-amber-50 flex items-center justify-center">
                <AlertCircle class="text-amber-500" :size="24" />
            </div>
        </div>
        <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-5 flex items-center justify-between opacity-60 cursor-pointer" @click="activeTab = 'approved'">
            <div>
                <p class="text-sm font-medium text-gray-500 mb-1">今週の承認完了</p>
                <div class="flex items-baseline gap-2">
                    <span class="text-3xl font-bold text-gray-900">{{ approvedInvoices.length }}</span>
                    <span class="text-sm text-gray-500 font-medium">件</span>
                </div>
            </div>
            <div class="h-12 w-12 rounded-full bg-gray-50 flex items-center justify-center">
                <CheckCircle class="text-gray-500" :size="24" />
            </div>
        </div>
    </div>

    <!-- Status Tabs (Full Width) -->
    <div class="flex bg-gray-200/50 p-1.5 rounded-xl mb-6 shadow-inner border border-gray-200/50">
        <button
          @click="activeTab = 'pending'"
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'pending' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          あなたの承認待ち <span v-if="pendingInvoices.length" class="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ pendingInvoices.length }}</span>
        </button>
        <button
          @click="activeTab = 'pending_all'"
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'pending_all' ? 'bg-white text-purple-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          全社未承認 <span v-if="pendingAllInvoices.length" class="bg-purple-100 text-purple-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ pendingAllInvoices.length }}</span>
        </button>
        <button
          @click="activeTab = 'approved'"
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'approved' ? 'bg-white text-emerald-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          承認済履歴
        </button>
        <button
          @click="activeTab = 'rejected'"
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'rejected' ? 'bg-white text-rose-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          差戻し履歴
        </button>
    </div>

    <!-- Search & Filters -->
    <div class="mb-6 flex flex-col md:flex-row gap-4 items-center justify-between">
        <div class="flex items-center gap-3 w-full">
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input v-model="searchQuery" type="text" placeholder="名前や金額・発行元で検索..." class="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500 bg-white shadow-sm transition-all" />
          </div>
          <button class="bg-white border border-gray-200 text-gray-700 px-4 py-2.5 rounded-lg hover:bg-gray-50 transition-colors shadow-sm shrink-0 flex items-center gap-2 text-sm font-medium">
            <Filter class="w-4 h-4" /> フィルター
          </button>
        </div>
    </div>

    <div class="bg-white shadow-sm rounded-xl border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50/80">
                    <tr>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-28">
                            {{ activeDirection === 'issued' ? '発行日 / 支払期日' : '受領日 / 支払期限' }}
                        </th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                            {{ activeDirection === 'issued' ? '取引先情報' : '仕入先情報' }}
                        </th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">件名</th>
                        <th scope="col" class="px-6 py-3.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">金額 (税込)</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-28">書類種別</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-40 sticky right-20 bg-gray-50/90 backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.05)]">ステータス</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-20 sticky right-0 bg-gray-50/90 backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.1)]">詳細</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    <tr v-if="displayedInvoices.length === 0">
                        <td colspan="7" class="px-6 py-16 text-center text-gray-500">
                            <div class="flex flex-col items-center justify-center">
                                <CheckCircle v-if="activeTab.startsWith('pending')" class="h-12 w-12 text-emerald-300 mb-3" />
                                <FolderKanban v-else class="h-12 w-12 text-gray-300 mb-3" />
                                <p class="text-base font-medium text-gray-900">{{ activeTab.startsWith('pending') ? 'すべての承認が完了しています！' : '該当するデータがありません' }}</p>
                                <p class="text-sm text-gray-500 mt-1">素晴らしいですね。</p>
                            </div>
                        </td>
                    </tr>
                    <tr
                        v-for="invoice in displayedInvoices"
                        :key="invoice.id"
                        class="hover:bg-blue-50/50 transition-colors cursor-pointer group"
                        @click="openDetail(invoice)"
                    >
                        <!-- Date -->
                        <td class="px-6 py-4 align-middle">
                            <div class="text-sm text-gray-900 font-medium whitespace-nowrap">{{ invoice.issue_date }}</div>
                            <div class="text-[11px] font-normal mt-1 bg-red-50 text-red-600 rounded px-1.5 py-0.5 inline-block whitespace-nowrap">期日: {{ invoice.due_date }}</div>
                        </td>
                        <!-- Vendor -->
                        <td class="px-6 py-4">
                            <div class="flex items-center">
                                <div class="h-9 w-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-600 font-bold mr-3 shrink-0 ring-1 ring-slate-200">
                                    {{ (invoice.client_name ?? '?').charAt(0) }}
                                </div>
                                <div class="min-w-0">
                                    <p class="text-sm font-medium text-gray-900 truncate">{{ invoice.client_name }}</p>
                                    <div class="flex items-center gap-1.5 mt-0.5 text-xs text-gray-500">
                                        <Building2 class="h-3 w-3" />
                                        <span class="truncate max-w-[120px]">
                                            {{ invoice.creator_name ?? '不明' }}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </td>
                        <!-- Content -->
                        <td class="px-6 py-4 min-w-[200px]">
                            <p class="text-sm font-semibold tracking-wide text-gray-900 truncate">{{ invoice.invoice_number ?? invoice.client_name ?? '請求書' }}</p>
                            <p class="text-xs text-gray-500 mt-0.5 truncate"><span v-if="invoice.line_items?.[0]?.category" class="bg-orange-50 text-orange-700 border border-orange-200 px-1.5 py-0.5 rounded text-[10px] font-medium">{{ invoice.line_items?.[0]?.category }}</span><span v-if="invoice.line_items?.[0]?.category" class="mx-1 text-gray-400">/</span><span class="bg-gray-100 px-1.5 py-0.5 rounded text-[10px]">{{ invoice.payment_method ?? '請求書払い' }}</span></p>
                        </td>
                        <!-- Amount -->
                        <td class="px-6 py-4 whitespace-nowrap text-right">
                           <p class="text-base font-bold text-gray-900">¥{{ formatAmount(invoice.total_amount) }}</p>
                        </td>
                        <!-- 書類種別 -->
                        <td class="px-6 py-4 whitespace-nowrap text-center">
                            <span v-if="invoice.document_type === 'issued'" class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-gray-100 text-gray-600 border border-gray-200">
                                発行請求書
                            </span>
                            <span v-else class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-gray-100 text-gray-600 border border-gray-200">
                                受領請求書
                            </span>
                        </td>
                        <!-- Status Badge -->
                        <td class="px-6 py-4 whitespace-nowrap text-center sticky right-20 bg-white/90 group-hover:bg-blue-50/90 transition-colors backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.05)]">
                            <span v-if="!['approved', 'auto_approved', 'rejected'].includes(invoice.approval_status)" class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                                <Clock class="w-3.5 h-3.5 mr-1" />
                                承認待ち ({{ invoice.current_step }}/{{ getApprovalHistory(invoice).length + (invoice.extra_approval_steps ?? []).length }})
                            </span>
                            <span v-else-if="invoice.approval_status === 'auto_approved'" class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                                <CheckCircle class="w-3.5 h-3.5 mr-1" />
                                自動承認済
                            </span>
                            <span v-else-if="invoice.approval_status === 'approved'" class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                <CheckCircle class="w-3.5 h-3.5 mr-1" />
                                承認済
                            </span>
                            <span v-else class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-rose-100 text-rose-800 border border-rose-200">
                                <XCircle class="w-3.5 h-3.5 mr-1" />
                                差戻し
                            </span>
                        </td>
                        <!-- Action -->
                        <td class="px-6 py-4 whitespace-nowrap text-center text-sm sticky right-0 bg-white/90 group-hover:bg-blue-50/90 transition-colors backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.1)]">
                            <button class="text-blue-500 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 p-2 rounded-lg transition-colors inline-flex items-center justify-center">
                                <FileText class="w-5 h-5" />
                            </button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>


    <!-- Detail Modal -->
    <InvoiceDetailModal
        :show="isDetailModalOpen"
        :invoice="selectedInvoice"
        :document_type="activeDirection"
        @close="closeDetail"
        @action-completed="handleActionCompleted"
        @step-added="handleStepAdded"
    />
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
