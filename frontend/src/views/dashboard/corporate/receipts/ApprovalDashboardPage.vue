<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  CheckCircle,
  XCircle,
  Clock,
  FileText,
  Search,
  Filter,
  AlertCircle,
  Building2,
  FolderKanban
} from 'lucide-vue-next';
import { useReceipts } from '@/composables/useReceipts';
import ReceiptDetailModal from '@/components/receipts/ReceiptDetailModal.vue';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

// --- MOCK DATA ---
interface ApprovalHistory {
  id: string;
  step: number;
  roleId: string;
  roleName: string;
  approverId?: string;
  approverName?: string;
  status: 'pending' | 'approved' | 'rejected' | 'skipped';
  actionDate?: string;
  comment?: string;
}

interface ReceiptItem {
  id: string;
  submitterName: string;
  departmentName: string;
  groupName?: string;
  projectName?: string;
  date: string;
  issuer: string;
  amount: number;
  taxRate: string;
  category: string;
  paymentMethod: string;
  memo: string;
  status: 'pending' | 'approved' | 'rejected';
  currentStepIndex: number;
  approvalHistory: ApprovalHistory[];
  imageUrl: string;
}

// Fetch real receipts and map to ReceiptItem shape for the template
const { receipts: apiReceipts, fetchReceipts } = useReceipts();

const mockReceipts = ref<ReceiptItem[]>([]);

const mapApiReceipt = (r: any): ReceiptItem => {
  const history = (r.approval_history && r.approval_history.length > 0)
    ? r.approval_history.map((h: any, i: number) => ({
        id: h.id ?? `h_${i}`,
        step: h.step ?? i + 1,
        roleId: h.role_id ?? 'approver',
        roleName: h.role_name ?? '承認者',
        approverId: h.approver_id,
        approverName: h.approver_name,
        status: h.status ?? 'pending',
        actionDate: h.action_date,
        comment: h.comment,
      }))
    : [];

  const extraSteps = (r.extra_approval_steps || []).map((s: any, i: number) => ({
      id: `h_ext_${Date.now()}_${i}`,
      step: history.length + i + 1,
      roleId: s.roleId,
      roleName: s.roleName,
      approverName: s.approverName,
      status: 'pending' as const,
  }));

  const combinedHistory = [...history, ...extraSteps];

  return {
    id: r.id ?? r._id,
    submitterName: r.submitter_name ?? r.created_by ?? '不明',
    departmentName: r.department ?? '一般',
    groupName: undefined,
    projectName: undefined,
    date: r.date,
    issuer: r.payee ?? '不明',
    amount: r.amount,
    taxRate: `${r.tax_rate ?? 10}%`,
    category: r.category ?? '未分類',
    paymentMethod: r.payment_method ?? '不明',
    memo: r.memo ?? '',
    status: r.status === 'approved' ? 'approved' : r.status === 'rejected' ? 'rejected' : 'pending',
    currentStepIndex: r.current_step ? r.current_step - 1 : 0,
    approvalHistory: combinedHistory.length > 0 
      ? combinedHistory 
      : [{ id: 'h_default', step: 1, roleId: 'manager', roleName: '管理者', status: r.status === 'approved' ? 'approved' : r.status === 'rejected' ? 'rejected' : 'pending' as any }],
    imageUrl: r.imageUrl ?? r.image_url ?? '',
  };
};

const loadData = async () => {
    await fetchReceipts({});
    mockReceipts.value = apiReceipts.value.map(mapApiReceipt);
};

onMounted(loadData);

// --- STATE ---
type TabView = 'pending' | 'pending_all' | 'approved' | 'rejected';
const activeTab = ref<TabView>('pending');

const selectedReceipt = ref<ReceiptItem | null>(null);
const isDetailModalOpen = ref(false);

// Computed Filters
const pendingReceipts = computed(() => mockReceipts.value.filter(r => r.status === 'pending' && r.approvalHistory[r.currentStepIndex]?.approverName !== '鈴木次郎'));
const pendingAllReceipts = computed(() => mockReceipts.value.filter(r => r.status === 'pending')); 
const approvedReceipts = computed(() => mockReceipts.value.filter(r => r.status === 'approved'));
const rejectedReceipts = computed(() => mockReceipts.value.filter(r => r.status === 'rejected'));

const displayedReceipts = computed(() => {
  switch (activeTab.value) {
    case 'pending': return pendingReceipts.value;
    case 'pending_all': return pendingAllReceipts.value;
    case 'approved': return approvedReceipts.value;
    case 'rejected': return rejectedReceipts.value;
    default: return [];
  }
});

// Calculate metrics
const metrics = computed(() => ({
  pendingCount: pendingReceipts.value.length,
  urgentCount: pendingReceipts.value.filter(r => r.amount >= 50000).length // example rule
}));

// --- ACTIONS ---
const openDetail = (receipt: ReceiptItem) => {
  selectedReceipt.value = receipt;
  isDetailModalOpen.value = true;
};

const closeDetail = () => {
  isDetailModalOpen.value = false;
  setTimeout(() => { selectedReceipt.value = null; }, 300);
};

const handleActionCompleted = async () => {
  closeDetail();
  await loadData();
};

</script>

<template>
  <div class="space-y-6">
    <!-- Header Area -->
    <header class="bg-white border-b border-gray-200 px-8 py-6 -mx-6 -mt-6 mb-6">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">領収書承認状況</h1>
          <p class="text-sm text-gray-500 mt-1">部下やプロジェクトメンバーから送信された領収書の確認・承認を行います</p>
        </div>
      </div>
    </header>

    <!-- Quick Metrics (unchanged) -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                    <span class="text-3xl font-bold text-gray-900">{{ approvedReceipts.length }}</span>
                    <span class="text-sm text-gray-500 font-medium">件</span>
                </div>
            </div>
            <div class="h-12 w-12 rounded-full bg-gray-50 flex items-center justify-center">
                <CheckCircle class="text-gray-500" :size="24" />
            </div>
        </div>
    </div>

    <!-- Tab Navigation (Full Width) -->
    <div class="flex bg-gray-200/50 p-1.5 rounded-xl mb-6 shadow-inner border border-gray-200/50">
        <button 
          @click="activeTab = 'pending'" 
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'pending' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <Clock class="w-4 h-4" />
          あなたの承認待ち <span v-if="pendingReceipts.length" class="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ pendingReceipts.length }}</span>
        </button>
        <button 
          @click="activeTab = 'pending_all'" 
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'pending_all' ? 'bg-white text-purple-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <FolderKanban class="w-4 h-4" />
          全社未承認 <span v-if="pendingAllReceipts.length" class="bg-purple-100 text-purple-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ pendingAllReceipts.length }}</span>
        </button>
        <button 
          @click="activeTab = 'approved'" 
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'approved' ? 'border-b-0 bg-white text-emerald-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <CheckCircle class="w-4 h-4" />
          承認済履歴
        </button>
        <button 
          @click="activeTab = 'rejected'" 
          class="flex-1 px-4 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'rejected' ? 'bg-white text-rose-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <XCircle class="w-4 h-4" />
          差戻し履歴
        </button>
    </div>

    <!-- Search & Filters -->
    <div class="mb-6 flex flex-col md:flex-row gap-4 items-center justify-between">
        <div class="flex items-center gap-3 w-full">
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input type="text" placeholder="名前や金額・発行元で検索..." class="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500 bg-white shadow-sm transition-all" />
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
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">申請日付</th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">申請者情報</th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">発行元 / 内容</th>
                        <th scope="col" class="px-6 py-3.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">金額 (税込)</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-40 sticky right-20 bg-gray-50/90 backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.05)]">ステータス</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-20 sticky right-0 bg-gray-50/90 backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.1)]">詳細</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    <tr v-if="displayedReceipts.length === 0">
                        <td colspan="6" class="px-6 py-16 text-center text-gray-500">
                            <div class="flex flex-col items-center justify-center">
                                <CheckCircle v-if="activeTab.startsWith('pending')" class="h-12 w-12 text-emerald-300 mb-3" />
                                <FolderKanban v-else class="h-12 w-12 text-gray-300 mb-3" />
                                <p class="text-base font-medium text-gray-900">{{ activeTab.startsWith('pending') ? 'すべての承認が完了しています！' : '該当するデータがありません' }}</p>
                                <p class="text-sm text-gray-500 mt-1">素晴らしいですね。</p>
                            </div>
                        </td>
                    </tr>
                    <tr 
                        v-for="receipt in displayedReceipts" 
                        :key="receipt.id"
                        class="hover:bg-blue-50/50 transition-colors cursor-pointer group"
                        @click="openDetail(receipt)"
                    >
                        <!-- Date -->
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">
                           {{ receipt.date }}
                           <div class="text-[11px] text-gray-400 font-normal mt-1 bg-gray-100 rounded px-1.5 py-0.5 inline-block">ID: {{ receipt.id }}</div>
                        </td>
                        <!-- Submitter / Dept / Project -->
                        <td class="px-6 py-4">
                            <div class="flex items-center">
                                <div class="h-9 w-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-600 font-bold mr-3 shrink-0 ring-1 ring-slate-200">
                                    {{ receipt.submitterName.charAt(0) }}
                                </div>
                                <div class="min-w-0">
                                    <p class="text-sm font-medium text-gray-900 truncate">{{ receipt.submitterName.split(' ')[0] }}</p>
                                    <div class="flex items-center gap-1.5 mt-0.5 text-xs text-gray-500">
                                        <Building2 class="h-3 w-3" v-if="!receipt.projectName" />
                                        <FolderKanban class="h-3 w-3 text-purple-500" v-else />
                                        <span class="truncate max-w-[120px]" :class="{'text-purple-600 font-medium': receipt.projectName}">
                                            {{ receipt.projectName || receipt.groupName || receipt.departmentName }}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </td>
                        <!-- Content -->
                        <td class="px-6 py-4 min-w-[200px]">
                            <p class="text-sm font-semibold tracking-wide text-gray-900 truncate">{{ receipt.issuer }}</p>
                            <p class="text-xs text-gray-500 mt-0.5 truncate">{{ receipt.category }} / {{ receipt.memo }} / <span class="bg-gray-100 px-1.5 py-0.5 rounded ml-1">{{ receipt.paymentMethod }}</span></p>
                        </td>
                        <!-- Amount -->
                        <td class="px-6 py-4 whitespace-nowrap text-right">
                           <p class="text-base font-bold text-gray-900">¥{{ formatAmount(receipt.amount) }}</p>
                           <p class="text-[11px] text-gray-500 mt-0.5">税 {{ receipt.taxRate }}</p>
                        </td>
                        <!-- Status Badge -->
                        <td class="px-6 py-4 whitespace-nowrap text-center sticky right-20 bg-white/90 group-hover:bg-blue-50/90 transition-colors backdrop-blur z-10 shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.05)]">
                            <span v-if="receipt.status === 'pending'" class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                                <Clock class="w-3.5 h-3.5 mr-1" />
                                承認待ち ({{ receipt.currentStepIndex + 1 }}/{{ receipt.approvalHistory.length }})
                            </span>
                            <span v-else-if="receipt.status === 'approved'" class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
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
    <ReceiptDetailModal
        :show="isDetailModalOpen"
        :receipt="selectedReceipt"
        @close="closeDetail"
        @action-completed="handleActionCompleted"
    />
  </div>
</template>
