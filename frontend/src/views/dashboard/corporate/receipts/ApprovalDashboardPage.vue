<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  CheckCircle,
  XCircle,
  Clock,
  Plus,
  FileText,
  Search,
  Filter,
  AlertCircle,
  Building2,
  FolderKanban,
  MessageSquareWarning
} from 'lucide-vue-next';
import { useReceipts } from '@/composables/useReceipts';

// --- MOCK DATA ---
interface ApprovalHistory {
  id: string;
  step: number;
  roleId: string; // e.g., 'group_leader', 'manager'
  roleName: string; // e.g., '係長', '部長'
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
  date: string; // YYYY-MM-DD
  issuer: string;
  amount: number;
  taxRate: string;
  category: string;
  paymentMethod: string;
  memo: string;
  status: 'pending' | 'approved' | 'rejected';
  currentStepIndex: number; // Index of the approvalHistory array
  approvalHistory: ApprovalHistory[];
  imageUrl: string;
}

// Simulated data to represent realistic approval states based on Phase 11.5 hierarchical models
const formatAmount = (num: number) => new Intl.NumberFormat('ja-JP').format(num);

// Fetch real receipts and map to ReceiptItem shape for the template
const { receipts: apiReceipts, fetchReceipts, approveReceipt } = useReceipts();

const mockReceipts = ref<ReceiptItem[]>([]);

const mapApiReceipt = (r: any): ReceiptItem => ({
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
  currentStepIndex: 0,
  approvalHistory: (r.approval_history && r.approval_history.length > 0)
    ? r.approval_history.map((h: any, i: number) => ({
        id: h.id ?? `h_${i}`,
        step: i + 1,
        roleId: h.role_id ?? 'approver',
        roleName: h.role_name ?? '承認者',
        approverId: h.approver_id,
        approverName: h.approver_name,
        status: h.status ?? 'pending',
        actionDate: h.action_date,
        comment: h.comment,
      }))
    : [{ id: 'h_default', step: 1, roleId: 'manager', roleName: '管理者', status: r.status === 'approved' ? 'approved' : r.status === 'rejected' ? 'rejected' : 'pending' as any }],
  imageUrl: r.image_url ?? '',
});

onMounted(async () => {
  await fetchReceipts({});
  mockReceipts.value = apiReceipts.value.map(mapApiReceipt);
});

// --- STATE ---
type TabView = 'pending' | 'pending_all' | 'approved' | 'rejected';
const activeTab = ref<TabView>('pending');

const selectedReceipt = ref<ReceiptItem | null>(null);
const isDetailModalOpen = ref(false);

const actionComment = ref('');
const isSubmittingAction = ref(false);

const isAddingApprover = ref(false);
const selectedExtraApproverId = ref('');

// Mock list of all potential higher-rank approvers
const masterApproversList = [
  { id: 'u101', roleId: 'manager', roleName: '営業1課 部長', name: '高橋 健一', rank: 3 },
  { id: 'u102', roleId: 'director', roleName: '担当役員', name: '鈴木 次郎', rank: 4 },
  { id: 'u103', roleId: 'president', roleName: '代表取締役', name: '佐藤 社長', rank: 5 },
];

const availableApproversToAdd = computed(() => {
  if (!selectedReceipt.value || selectedReceipt.value.approvalHistory.length === 0) return [];
  // Find current step's approver rank (mocking rank from roleId string matching)
  const currentRole = selectedReceipt.value.approvalHistory[selectedReceipt.value.currentStepIndex].roleId;
  let currentRank = 1;
  if (currentRole.includes('leader')) currentRank = 2;
  if (currentRole.includes('manager')) currentRank = 3;
  if (currentRole.includes('director')) currentRank = 4;
  if (currentRole.includes('president')) currentRank = 5;
  
  return masterApproversList.filter(a => a.rank > currentRank);
});

// Computed Filters
const pendingReceipts = computed(() => mockReceipts.value.filter(r => r.status === 'pending' && r.approvalHistory[r.currentStepIndex].approverName !== '鈴木次郎'));
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
  actionComment.value = '';
  isDetailModalOpen.value = true;
};

const closeDetail = () => {
  isDetailModalOpen.value = false;
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
  setTimeout(() => { selectedReceipt.value = null; }, 300);
};

const handleAddApprover = () => {
  if (!selectedExtraApproverId.value || !selectedReceipt.value) return;
  const approver = masterApproversList.find(a => a.id === selectedExtraApproverId.value);
  if (approver) {
    const newStepIndex = selectedReceipt.value.approvalHistory.length;
    selectedReceipt.value.approvalHistory.push({
      id: 'h_ext_' + Date.now(),
      step: newStepIndex + 1,
      roleId: approver.roleId,
      roleName: approver.roleName,
      approverName: approver.name,
      status: 'pending'
    });
  }
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
};

const handleRemoveApprover = (historyId: string) => {
  if (!selectedReceipt.value) return;
  const idx = selectedReceipt.value.approvalHistory.findIndex(h => h.id === historyId);
  if (idx > -1 && historyId.startsWith('h_ext_')) {
    selectedReceipt.value.approvalHistory.splice(idx, 1);
    selectedReceipt.value.approvalHistory.forEach((h, i) => {
      h.step = i + 1;
    });
  }
};

const handleApprove = async () => {
  if (!selectedReceipt.value) return;
  isSubmittingAction.value = true;
  const receiptId = selectedReceipt.value.id;
  const result = await approveReceipt(receiptId, 'approve', actionComment.value || undefined);
  if (result) {
    // Update local state immediately
    const receiptRef = mockReceipts.value.find(r => r.id === receiptId);
    if (receiptRef) {
      receiptRef.status = 'approved';
      const step = receiptRef.approvalHistory[receiptRef.currentStepIndex];
      if (step) { step.status = 'approved'; step.approverName = 'あなた'; step.actionDate = new Date().toLocaleString('ja-JP'); }
    }
  }
  isSubmittingAction.value = false;
  closeDetail();
};

const handleReject = async () => {
  if (!selectedReceipt.value) return;
  if (!actionComment.value.trim()) {
    alert('差戻しの場合はコメント（理由）を入力してください。');
    return;
  }
  isSubmittingAction.value = true;
  const receiptId = selectedReceipt.value.id;
  const result = await approveReceipt(receiptId, 'reject', actionComment.value);
  if (result) {
    const receiptRef = mockReceipts.value.find(r => r.id === receiptId);
    if (receiptRef) {
      receiptRef.status = 'rejected';
      const step = receiptRef.approvalHistory[receiptRef.currentStepIndex];
      if (step) { step.status = 'rejected'; step.approverName = 'あなた'; step.comment = actionComment.value; }
    }
  }
  isSubmittingAction.value = false;
  closeDetail();
};

</script>

<template>
  <div class="space-y-6">
    <!-- Header Area -->
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">領収書承認状況</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          部下およびプロジェクトメンバーから送信された領収書の確認・承認・差戻しを行います。
        </p>
      </div>
    </div>

    <!-- Quick Metrics -->
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

    <!-- Tab Navigation & Filters -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div class="border-b border-gray-200 px-4 pt-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <nav class="flex space-x-6 overflow-x-auto no-scrollbar" aria-label="Tabs">
                <button
                    @click="activeTab = 'pending'"
                    class="pb-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap"
                    :class="activeTab === 'pending' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
                >
                    あなたの承認待ち
                    <span v-if="pendingReceipts.length" class="ml-2 bg-blue-100 text-blue-700 py-0.5 px-2 rounded-full text-xs">{{ pendingReceipts.length }}</span>
                </button>
                <button
                    @click="activeTab = 'pending_all'"
                    class="pb-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap"
                    :class="activeTab === 'pending_all' ? 'border-purple-600 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
                    title="管理者向け: 全社の未承認一覧"
                >
                    全社未承認一覧
                    <span v-if="pendingAllReceipts.length" class="ml-2 bg-purple-100 text-purple-700 py-0.5 px-2 rounded-full text-xs">{{ pendingAllReceipts.length }}</span>
                </button>
                <button
                    @click="activeTab = 'approved'"
                    class="pb-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap"
                    :class="activeTab === 'approved' ? 'border-emerald-600 text-emerald-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
                >
                    承認済履歴
                </button>
                <button
                    @click="activeTab = 'rejected'"
                    class="pb-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap"
                    :class="activeTab === 'rejected' ? 'border-rose-600 text-rose-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
                >
                    差戻し履歴
                </button>
            </nav>
            <div class="flex items-center gap-2 pb-3">
                <div class="relative w-64 md:w-80 border-l border-gray-200 pl-4 ml-4">
                    <div class="absolute inset-y-0 left-4 pl-3 flex items-center pointer-events-none">
                        <Search class="h-4 w-4 text-gray-400" />
                    </div>
                    <input type="text" placeholder="名前や金額・発行元で検索..." class="block w-full pl-9 pr-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-gray-50 focus:ring-blue-500 focus:border-blue-500 text-gray-900" />
                </div>
                <button class="p-1.5 border border-gray-300 rounded-lg text-gray-500 hover:bg-gray-50" title="フィルター設定">
                    <Filter class="h-4 w-4" />
                </button>
            </div>
        </div>

        <!-- Data Table -->
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50/80">
                    <tr>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">申請日付</th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">申請者情報</th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">発行元 / 内容</th>
                        <th scope="col" class="px-6 py-3.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">金額 (税込)</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-40">ステータス</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-20">詳細</th>
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
                        <td class="px-6 py-4 whitespace-nowrap text-center">
                            <span v-if="receipt.status === 'pending'" class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                                <Clock class="w-3.5 h-3.5 mr-1" />
                                承認待ち ({{ receipt.currentStepIndex + 1 }}/{{ receipt.approvalHistory.length }})
                            </span>
                            <span v-else-if="receipt.status === 'approved'" class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                <CheckCircle class="w-3.5 h-3.5 mr-1" />
                                承認済
                            </span>
                            <span v-else class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
                                <XCircle class="w-3.5 h-3.5 mr-1" />
                                差戻し
                            </span>
                        </td>
                        <!-- Action -->
                        <td class="px-6 py-4 whitespace-nowrap text-center text-sm">
                            <button class="text-blue-500 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 p-2 rounded-lg transition-colors inline-flex items-center justify-center">
                                <FileText class="w-5 h-5" />
                            </button>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>


    <!-- Detail Modal / Side Panel -->
    <div v-if="isDetailModalOpen && selectedReceipt" class="fixed inset-0 z-50 overflow-hidden" aria-labelledby="slide-over-title" role="dialog" aria-modal="true">
        <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity" @click="closeDetail"></div>

        <div class="fixed inset-y-0 right-0 max-w-full flex w-full lg:w-[900px] xl:w-[1000px] bg-white shadow-2xl transition-transform transform duration-300 ease-in-out">
            <div class="h-full flex flex-col w-full shadow-xl overflow-y-scroll bg-slate-50 relative">
                <!-- Header -->
                <div class="px-6 py-4 pr-20 bg-white border-b border-gray-200 flex items-center justify-between sticky top-0 z-10 shadow-sm">
                    <div>
                        <h2 class="text-lg font-bold text-gray-900" id="slide-over-title">申請詳細 : {{ selectedReceipt.id }}</h2>
                        <p class="text-xs text-gray-500 mt-1">提出者: <span class="font-medium text-gray-700">{{ selectedReceipt.submitterName }}</span></p>
                    </div>
                    <button @click="closeDetail" class="rounded-full p-2 bg-gray-50 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <span class="sr-only">Close panel</span>
                        <XCircle class="h-6 w-6" aria-hidden="true" />
                    </button>
                </div>

                <!-- Content Area -->
                <div class="flex-1 overflow-y-auto p-6">
                    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full min-h-[600px]">
                        
                        <!-- Left Panel: Data & Flow (Occupies 5 columns) -->
                        <div class="lg:col-span-5 space-y-6 flex flex-col">
                            <!-- Receipt Info -->
                            <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
                                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-3">領収書内容</h3>
                                <dl class="grid grid-cols-1 gap-x-4 gap-y-4 text-sm">
                                    <div class="flex justify-between items-center bg-gray-50 p-3 rounded-lg border border-gray-100">
                                        <span class="text-gray-600 font-medium">合計金額</span>
                                        <span class="text-2xl font-bold tracking-tight">¥{{ formatAmount(selectedReceipt.amount) }}<span class="text-[11px] font-normal text-gray-500 ml-1">(税込)</span></span>
                                    </div>
                                    <div class="grid grid-cols-2 gap-4">
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">申請日</dt>
                                            <dd class="font-medium text-gray-900">{{ selectedReceipt.date }}</dd>
                                        </div>
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">適用税率</dt>
                                            <dd class="font-medium text-gray-900">{{ selectedReceipt.taxRate }}</dd>
                                        </div>
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">勘定科目</dt>
                                            <dd class="font-medium text-blue-800 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded text-xs inline-block">{{ selectedReceipt.category }}</dd>
                                        </div>
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">決済手段</dt>
                                            <dd class="font-medium text-gray-900">{{ selectedReceipt.paymentMethod }}</dd>
                                        </div>
                                        <div class="col-span-2">
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">発行元 / 店舗</dt>
                                            <dd class="font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded inline-block">{{ selectedReceipt.issuer }}</dd>
                                        </div>
                                    </div>
                                    <div>
                                        <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 mt-2">メモ・備考</dt>
                                        <dd class="font-medium text-gray-900 break-words bg-yellow-50/50 p-2 rounded-lg border border-yellow-100/50 text-xs">{{ selectedReceipt.memo }}</dd>
                                    </div>
                                    
                                    <div v-if="selectedReceipt.projectName" class="pt-2 border-t border-gray-100 mt-2">
                                        <dt class="text-purple-600 text-[11px] tracking-wide flex items-center gap-1 mb-1"><FolderKanban class="w-3 h-3"/>紐付けプロジェクト</dt>
                                        <dd class="font-medium text-purple-900 bg-purple-50 px-2 py-1 rounded inline-block text-xs border border-purple-100 w-full truncate">
                                            {{ selectedReceipt.projectName }}
                                        </dd>
                                    </div>
                                </dl>
                            </div>

                            <!-- Approval Progress Tree -->
                            <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm flex-1">
                                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-3 mb-4">承認フロー</h3>
                                <div class="flow-root mt-4">
                                    <ul role="list" class="-mb-8">
                                        <li v-for="(step, index) in selectedReceipt.approvalHistory" :key="step.id">
                                            <div class="relative pb-8">
                                                <span v-if="index !== selectedReceipt.approvalHistory.length - 1" class="absolute top-4 left-4 -ml-px h-full w-0.5 bg-gray-200" aria-hidden="true"></span>
                                                <div class="relative flex space-x-3">
                                                    <div>
                                                        <span 
                                                            class="h-8 w-8 rounded-full flex items-center justify-center ring-4 ring-white shadow-sm"
                                                            :class="{
                                                                'bg-emerald-500 text-white': step.status === 'approved',
                                                                'bg-rose-500 text-white': step.status === 'rejected',
                                                                'bg-blue-100 border-2 border-blue-500 text-blue-700': step.status === 'pending' && index <= selectedReceipt.currentStepIndex,
                                                                'bg-gray-100 text-gray-400 border border-gray-200': step.status === 'pending' && index > selectedReceipt.currentStepIndex
                                                            }"
                                                        >
                                                            <CheckCircle v-if="step.status === 'approved'" class="h-4 w-4" aria-hidden="true" />
                                                            <XCircle v-else-if="step.status === 'rejected'" class="h-4 w-4" aria-hidden="true" />
                                                            <span v-else class="text-xs font-bold">{{ index + 1 }}</span>
                                                        </span>
                                                    </div>
                                                    <div class="flex min-w-0 flex-1 justify-between space-x-4 pt-1.5">
                                                        <div>
                                                            <p class="text-sm font-medium text-gray-900 flex items-center gap-2">
                                                                {{ step.roleName }}
                                                                <span v-if="step.status === 'pending' && index === selectedReceipt.currentStepIndex" class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800">
                                                                    順番待ち
                                                                </span>
                                                                <!-- Delete button for manually added approvers -->
                                                                <button 
                                                                    v-if="step.id.startsWith('h_ext_') && step.status === 'pending'" 
                                                                    @click="handleRemoveApprover(step.id)" 
                                                                    class="text-gray-400 hover:text-red-500 transition-colors p-0.5 rounded hover:bg-red-50"
                                                                    title="このステップを削除"
                                                                >
                                                                    <XCircle class="w-4 h-4" />
                                                                </button>
                                                            </p>
                                                            <p v-if="step.approverName" class="text-xs text-gray-500">{{ step.approverName }}</p>
                                                            
                                                            <!-- Step Comment -->
                                                            <div v-if="step.comment" class="mt-2 text-sm text-gray-700 bg-red-50/50 border border-rose-100 rounded-lg p-3 relative shadow-sm">
                                                                <div class="flex gap-2">
                                                                    <MessageSquareWarning v-if="step.status === 'rejected'" class="h-4 w-4 text-rose-500 shrink-0" />
                                                                    <p class="text-xs leading-relaxed" :class="{'text-rose-800': step.status === 'rejected'}">{{ step.comment }}</p>
                                                                </div>
                                                            </div>
                                                            
                                                            <!-- Ad-Hoc Approver Insertion Button (Only visible on the last step if still pending) -->
                                                            <div v-if="index === selectedReceipt.approvalHistory.length - 1 && selectedReceipt.status === 'pending'" class="mt-4 pt-4 border-t border-gray-100 border-dashed">
                                                                <button v-if="!isAddingApprover" @click="isAddingApprover = true" class="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2.5 py-1.5 rounded-lg border border-blue-100 hover:bg-blue-100 transition-colors">
                                                                    <Plus class="w-3.5 h-3.5 mr-1" />
                                                                    次の承認者を追加 (個別対応)
                                                                </button>
                                                                <div v-else class="bg-gray-50 border border-gray-200 rounded-lg p-3 shadow-inner">
                                                                    <p class="text-xs font-bold text-gray-700 mb-2">追加する承認者を選択(現在の階層以上)</p>
                                                                    <div class="flex items-center gap-2">
                                                                        <select v-model="selectedExtraApproverId" class="block w-full rounded-md border-gray-300 border shadow-sm focus:border-blue-500 focus:ring-blue-500 text-xs py-1.5 px-2 bg-white">
                                                                            <option value="" disabled>選択してください</option>
                                                                            <option v-for="user in availableApproversToAdd" :key="user.id" :value="user.id">
                                                                                {{ user.roleName }} - {{ user.name }}
                                                                            </option>
                                                                        </select>
                                                                        <button @click="handleAddApprover" class="bg-blue-600 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-blue-700 whitespace-nowrap disabled:opacity-50" :disabled="!selectedExtraApproverId">追加</button>
                                                                        <button @click="isAddingApprover = false" class="text-gray-500 hover:text-gray-700 px-2 py-1.5 rounded-md text-xs font-medium whitespace-nowrap bg-white border border-gray-200 shadow-sm">キャンセル</button>
                                                                    </div>
                                                                    <p v-if="availableApproversToAdd.length === 0" class="text-[10px] text-rose-500 mt-1">現在の階層より上位の役職者が存在しません。</p>
                                                                </div>
                                                            </div>

                                                        </div>
                                                        <div class="whitespace-nowrap text-right text-xs text-gray-500 flex flex-col items-end">
                                                            <span v-if="step.actionDate">{{ step.actionDate }}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <!-- Right Panel: Image & Action (Occupies 7 columns) -->
                        <div class="lg:col-span-7 flex flex-col gap-4">
                            <!-- Image View -->
                            <div class="bg-slate-200/50 rounded-xl overflow-hidden border border-gray-200 shadow-inner relative group flex-1 min-h-[400px]">
                                <div class="absolute inset-0 flex items-center justify-center text-gray-400" v-if="!selectedReceipt.imageUrl">
                                    <FileText class="w-16 h-16" />
                                    <p class="ml-4 font-medium">画像データはありません</p>
                                </div>
                                <img v-else :src="selectedReceipt.imageUrl" class="absolute inset-0 w-full h-full object-contain" alt="Receipt Preview" />
                            </div>

                            <!-- Action Area (Only visible if pending AND current user is supposed to act) -->
                            <div v-if="selectedReceipt.status === 'pending'" class="bg-white border text-center relative border-gray-200 rounded-xl p-5 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]">
                                
                                <div v-if="selectedReceipt.approvalHistory[selectedReceipt.currentStepIndex].approverName === '鈴木次郎'" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 text-left">
                                    <h4 class="text-sm font-bold text-blue-800 flex items-center gap-2"><Clock class="w-4 h-4"/> 別の担当者の承認待ち</h4>
                                    <p class="text-xs text-blue-700 mt-1">現在は <strong>{{ selectedReceipt.approvalHistory[selectedReceipt.currentStepIndex].roleName }} ({{ selectedReceipt.approvalHistory[selectedReceipt.currentStepIndex].approverName }})</strong> の承認を待っています。</p>
                                </div>
                                <div v-else>
                                    <div class="mb-4">
                                        <h3 class="text-sm font-bold text-gray-900 mb-2 text-left">承認用コメント（任意）</h3>
                                        <textarea 
                                            v-model="actionComment"
                                            rows="2" 
                                            class="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-3 border resize-none bg-gray-50/50" 
                                            placeholder="確認しました。"
                                        ></textarea>
                                    </div>

                                    <div class="flex gap-3">
                                        <button 
                                            @click="handleReject"
                                            :disabled="isSubmittingAction"
                                            class="flex-[1] bg-white hover:bg-rose-50 border border-rose-200 text-rose-600 hover:text-rose-700 font-semibold py-3 px-4 rounded-xl shadow-sm transition-colors text-sm disabled:opacity-50 ring-1 ring-inset ring-rose-100 flex items-center justify-center gap-2"
                                        >
                                            <XCircle class="w-4 h-4"/>
                                            差戻し
                                        </button>
                                        <button 
                                            @click="handleApprove"
                                            :disabled="isSubmittingAction"
                                            class="flex-[2] bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-xl shadow-md flex justify-center items-center transition-all hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 text-sm disabled:opacity-50 gap-2"
                                        >
                                            <svg v-if="isSubmittingAction" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                            </svg>
                                            <CheckCircle v-if="!isSubmittingAction" class="w-4 h-4" />
                                            {{ isSubmittingAction ? '処理中...' : '承認する' }}
                                        </button>
                                    </div>
                                </div>
                            </div>
                            
                            <div v-else class="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center text-sm text-gray-500">
                                この申請は現在アクションを必要としていません。
                            </div>
                        </div>

                    </div>
                </div>
            </div>
        </div>
    </div>
  </div>
</template>
