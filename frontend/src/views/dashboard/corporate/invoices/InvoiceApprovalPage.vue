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
import { useInvoices } from '@/composables/useInvoices';

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

interface InvoiceItem {
  id: string;
  vendorName: string;
  title: string;
  amount: number;
  issuedDate: string; // YYYY-MM-DD
  dueDate: string; // YYYY-MM-DD
  category: string;
  paymentMethod: string;
  memo: string;
  status: 'pending' | 'approved' | 'rejected';
  currentStepIndex: number; 
  approvalHistory: ApprovalHistory[];
  imageUrl: string;
}

const formatAmount = (num: number) => new Intl.NumberFormat('ja-JP').format(num);

// --- COMPOSABLE ---
const { invoices: apiInvoices, fetchInvoices, submitApprovalAction } = useInvoices();

const mapApiInvoice = (inv: any): InvoiceItem => ({
  id: inv.id ?? inv._id,
  vendorName: inv.vendor_name ?? inv.client_name ?? '不明',
  title: inv.title ?? inv.description ?? '受領請求書',
  amount: inv.total_amount ?? inv.amount ?? 0,
  issuedDate: inv.issue_date ?? '',
  dueDate: inv.due_date ?? '',
  category: inv.category ?? '未分類',
  paymentMethod: inv.payment_method ?? '請求書払い',
  memo: inv.memo ?? '',
  status: inv.status === 'approved' ? 'approved' : inv.status === 'rejected' ? 'rejected' : 'pending',
  currentStepIndex: 0,
  approvalHistory: (inv.approval_history && inv.approval_history.length > 0)
    ? inv.approval_history.map((h: any, i: number) => ({
        id: h.id ?? `h_${i}`,
        step: i + 1,
        roleId: h.role_id ?? 'accounting',
        roleName: h.role_name ?? '経理担当',
        approverId: h.approver_id,
        approverName: h.approver_name,
        status: h.status ?? 'pending',
        actionDate: h.action_date,
        comment: h.comment,
      }))
    : [{ id: 'h_default', step: 1, roleId: 'accounting', roleName: '経理担当', status: (inv.status === 'approved' ? 'approved' : inv.status === 'rejected' ? 'rejected' : 'pending') as any }],
  imageUrl: inv.image_url ?? '',
});

const mockInvoices = ref<InvoiceItem[]>([]);

onMounted(async () => {
  await fetchInvoices({ direction: 'received' });
  mockInvoices.value = (apiInvoices.value as any[]).map(mapApiInvoice);
});

// --- STATE ---
type TabView = 'pending' | 'pending_all' | 'approved' | 'rejected';
const activeTab = ref<TabView>('pending');

const selectedInvoice = ref<InvoiceItem | null>(null);
const isDetailModalOpen = ref(false);

const actionComment = ref('');
const isSubmittingAction = ref(false);

const isAddingApprover = ref(false);
const selectedExtraApproverId = ref('');

// Mock list
const masterApproversList = [
  { id: 'u101', roleId: 'manager', roleName: '部門長', name: '高橋 健一', rank: 3 },
  { id: 'u102', roleId: 'director', roleName: '担当役員', name: '鈴木 次郎', rank: 4 },
  { id: 'u103', roleId: 'president', roleName: '代表取締役', name: '佐藤 社長', rank: 5 },
];

const availableApproversToAdd = computed(() => {
  if (!selectedInvoice.value || selectedInvoice.value.approvalHistory.length === 0) return [];
  const currentRole = selectedInvoice.value.approvalHistory[selectedInvoice.value.currentStepIndex].roleId;
  let currentRank = 1;
  if (currentRole.includes('accounting')) currentRank = 2;
  if (currentRole.includes('manager')) currentRank = 3;
  if (currentRole.includes('director')) currentRank = 4;
  
  return masterApproversList.filter(a => a.rank > currentRank);
});

// Computed Filters
const pendingInvoices = computed(() => mockInvoices.value.filter(i => i.status === 'pending' && i.approvalHistory[i.currentStepIndex].roleId === 'accounting'));
const pendingAllInvoices = computed(() => mockInvoices.value.filter(i => i.status === 'pending')); 
const approvedInvoices = computed(() => mockInvoices.value.filter(i => i.status === 'approved'));
const rejectedInvoices = computed(() => mockInvoices.value.filter(i => i.status === 'rejected'));

const displayedInvoices = computed(() => {
  switch (activeTab.value) {
    case 'pending': return pendingInvoices.value;
    case 'pending_all': return pendingAllInvoices.value;
    case 'approved': return approvedInvoices.value;
    case 'rejected': return rejectedInvoices.value;
    default: return [];
  }
});

// Calculate metrics
const metrics = computed(() => ({
  pendingCount: pendingInvoices.value.length,
  urgentCount: pendingInvoices.value.filter(i => i.amount >= 100000).length
}));

// --- ACTIONS ---
const openDetail = (invoice: InvoiceItem) => {
  selectedInvoice.value = invoice;
  actionComment.value = '';
  isDetailModalOpen.value = true;
};

const closeDetail = () => {
  isDetailModalOpen.value = false;
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
  setTimeout(() => { selectedInvoice.value = null; }, 300);
};

const handleAddApprover = () => {
  if (!selectedExtraApproverId.value || !selectedInvoice.value) return;
  const approver = masterApproversList.find(a => a.id === selectedExtraApproverId.value);
  if (approver) {
    const newStepIndex = selectedInvoice.value.approvalHistory.length;
    selectedInvoice.value.approvalHistory.push({
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
  if (!selectedInvoice.value) return;
  const idx = selectedInvoice.value.approvalHistory.findIndex(h => h.id === historyId);
  if (idx > -1 && historyId.startsWith('h_ext_')) {
    selectedInvoice.value.approvalHistory.splice(idx, 1);
    selectedInvoice.value.approvalHistory.forEach((h, i) => {
      h.step = i + 1;
    });
  }
};

const handleApprove = async () => {
  if (!selectedInvoice.value) return;
  isSubmittingAction.value = true;
  const invId = selectedInvoice.value.id;
  const result = await submitApprovalAction(invId, 'approved', selectedInvoice.value.currentStepIndex + 1, actionComment.value || undefined);
  if (result) {
    const invRef = mockInvoices.value.find(i => i.id === invId);
    if (invRef) {
      invRef.status = 'approved';
      const step = invRef.approvalHistory[invRef.currentStepIndex];
      if (step) { step.status = 'approved'; step.approverName = 'あなた'; step.actionDate = new Date().toLocaleString('ja-JP'); }
    }
  }
  isSubmittingAction.value = false;
  closeDetail();
};

const handleReject = async () => {
  if (!selectedInvoice.value) return;
  if (!actionComment.value.trim()) {
    alert('差戻しの場合はコメント（理由）を入力してください。');
    return;
  }
  isSubmittingAction.value = true;
  const invId = selectedInvoice.value.id;
  const result = await submitApprovalAction(invId, 'rejected', selectedInvoice.value.currentStepIndex + 1, actionComment.value);
  if (result) {
    const invRef = mockInvoices.value.find(i => i.id === invId);
    if (invRef) {
      invRef.status = 'rejected';
      const step = invRef.approvalHistory[invRef.currentStepIndex];
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
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">受領請求書承認状況</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          仕入先から届いた請求書の支払内容を確認し、承認・差戻しを行います。
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
                    <span class="text-3xl font-bold text-gray-900">{{ approvedInvoices.length }}</span>
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
                    <span v-if="pendingInvoices.length" class="ml-2 bg-blue-100 text-blue-700 py-0.5 px-2 rounded-full text-xs">{{ pendingInvoices.length }}</span>
                </button>
                <button
                    @click="activeTab = 'pending_all'"
                    class="pb-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap"
                    :class="activeTab === 'pending_all' ? 'border-purple-600 text-purple-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
                    title="管理者向け: 全社の未承認一覧"
                >
                    全社未承認一覧
                    <span v-if="pendingAllInvoices.length" class="ml-2 bg-purple-100 text-purple-700 py-0.5 px-2 rounded-full text-xs">{{ pendingAllInvoices.length }}</span>
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
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">発行日 / 期限</th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">仕入先情報</th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">件名</th>
                        <th scope="col" class="px-6 py-3.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">金額 (税込)</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-40">ステータス</th>
                        <th scope="col" class="px-6 py-3.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider w-20">詳細</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    <tr v-if="displayedInvoices.length === 0">
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
                        v-for="invoice in displayedInvoices" 
                        :key="invoice.id"
                        class="hover:bg-blue-50/50 transition-colors cursor-pointer group"
                        @click="openDetail(invoice)"
                    >
                        <!-- Date -->
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-medium">
                           {{ invoice.issuedDate }}
                           <div class="text-[11px] text-gray-400 font-normal mt-1 bg-red-50 text-red-600 rounded px-1.5 py-0.5 inline-block">期限: {{ invoice.dueDate }}</div>
                        </td>
                        <!-- Vendor -->
                        <td class="px-6 py-4">
                            <div class="flex items-center">
                                <div class="h-9 w-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-600 font-bold mr-3 shrink-0 ring-1 ring-slate-200">
                                    {{ invoice.vendorName.charAt(0) }}
                                </div>
                                <div class="min-w-0">
                                    <p class="text-sm font-medium text-gray-900 truncate">{{ invoice.vendorName }}</p>
                                    <div class="flex items-center gap-1.5 mt-0.5 text-xs text-gray-500">
                                        <Building2 class="h-3 w-3" />
                                        <span class="truncate max-w-[120px]">
                                            {{ invoice.id }}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </td>
                        <!-- Content -->
                        <td class="px-6 py-4 min-w-[200px]">
                            <p class="text-sm font-semibold tracking-wide text-gray-900 truncate">{{ invoice.title }}</p>
                            <p class="text-xs text-gray-500 mt-0.5 truncate">{{ invoice.category }} / {{ invoice.memo }}</p>
                        </td>
                        <!-- Amount -->
                        <td class="px-6 py-4 whitespace-nowrap text-right">
                           <p class="text-base font-bold text-gray-900">¥{{ formatAmount(invoice.amount) }}</p>
                           <p class="text-[11px] text-gray-500 mt-0.5">{{ invoice.paymentMethod }}</p>
                        </td>
                        <!-- Status Badge -->
                        <td class="px-6 py-4 whitespace-nowrap text-center">
                            <span v-if="invoice.status === 'pending'" class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">
                                <Clock class="w-3.5 h-3.5 mr-1" />
                                承認待ち ({{ invoice.currentStepIndex + 1 }}/{{ invoice.approvalHistory.length }})
                            </span>
                            <span v-else-if="invoice.status === 'approved'" class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
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
    <div v-if="isDetailModalOpen && selectedInvoice" class="fixed inset-0 z-50 overflow-hidden" aria-labelledby="slide-over-title" role="dialog" aria-modal="true">
        <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity" @click="closeDetail"></div>

        <div class="fixed inset-y-0 right-0 max-w-full flex w-full lg:w-[900px] xl:w-[1000px] bg-white shadow-2xl transition-transform transform duration-300 ease-in-out">
            <div class="h-full flex flex-col w-full shadow-xl overflow-y-scroll bg-slate-50 relative">
                <!-- Header -->
                <div class="px-6 py-4 pr-20 bg-white border-b border-gray-200 flex items-center justify-between sticky top-0 z-10 shadow-sm">
                    <div>
                        <h2 class="text-lg font-bold text-gray-900" id="slide-over-title">受領請求書詳細 : {{ selectedInvoice.id }}</h2>
                        <p class="text-xs text-gray-500 mt-1">仕入先: <span class="font-medium text-gray-700">{{ selectedInvoice.vendorName }}</span></p>
                    </div>
                    <button @click="closeDetail" class="rounded-full p-2 bg-gray-50 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <span class="sr-only">Close panel</span>
                        <XCircle class="h-6 w-6" aria-hidden="true" />
                    </button>
                </div>

                <!-- Content Area -->
                <div class="flex-1 overflow-y-auto p-6">
                    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full min-h-[600px]">
                        
                        <!-- Left Panel: Data & Flow -->
                        <div class="lg:col-span-5 space-y-6 flex flex-col">
                            <!-- Invoice Info -->
                            <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
                                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-3">請求書詳細内容</h3>
                                <dl class="grid grid-cols-1 gap-x-4 gap-y-4 text-sm">
                                    <div class="flex justify-between items-center bg-gray-50 p-3 rounded-lg border border-gray-100">
                                        <span class="text-gray-600 font-medium">合計請求金額</span>
                                        <span class="text-2xl font-bold tracking-tight">¥{{ formatAmount(selectedInvoice.amount) }}<span class="text-[11px] font-normal text-gray-500 ml-1">(税込)</span></span>
                                    </div>
                                    <div class="grid grid-cols-2 gap-4">
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">発行日</dt>
                                            <dd class="font-medium text-gray-900">{{ selectedInvoice.issuedDate }}</dd>
                                        </div>
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 text-red-600">支払期限</dt>
                                            <dd class="font-bold text-red-700">{{ selectedInvoice.dueDate }}</dd>
                                        </div>
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">勘定科目</dt>
                                            <dd class="font-medium text-blue-800 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded text-xs inline-block">{{ selectedInvoice.category }}</dd>
                                        </div>
                                        <div>
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">支払方法</dt>
                                            <dd class="font-medium text-gray-900">{{ selectedInvoice.paymentMethod }}</dd>
                                        </div>
                                        <div class="col-span-2">
                                            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">件名 / 内容</dt>
                                            <dd class="font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded inline-block w-full">{{ selectedInvoice.title }}</dd>
                                        </div>
                                    </div>
                                    <div>
                                        <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 mt-2">社内用メモ</dt>
                                        <dd class="font-medium text-gray-900 break-words bg-yellow-50/50 p-2 rounded-lg border border-yellow-100/50 text-xs">{{ selectedInvoice.memo || 'なし' }}</dd>
                                    </div>
                                </dl>
                            </div>

                            <!-- Approval Progress Tree -->
                            <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm flex-1">
                                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-3 mb-4">承認フロー</h3>
                                <div class="flow-root mt-4">
                                    <ul role="list" class="-mb-8">
                                        <li v-for="(step, index) in selectedInvoice.approvalHistory" :key="step.id">
                                            <div class="relative pb-8">
                                                <span v-if="index !== selectedInvoice.approvalHistory.length - 1" class="absolute top-4 left-4 -ml-px h-full w-0.5 bg-gray-200" aria-hidden="true"></span>
                                                <div class="relative flex space-x-3">
                                                    <div>
                                                        <span 
                                                            class="h-8 w-8 rounded-full flex items-center justify-center ring-4 ring-white shadow-sm"
                                                            :class="{
                                                                'bg-emerald-500 text-white': step.status === 'approved',
                                                                'bg-rose-500 text-white': step.status === 'rejected',
                                                                'bg-blue-100 border-2 border-blue-500 text-blue-700': step.status === 'pending' && index <= selectedInvoice.currentStepIndex,
                                                                'bg-gray-100 text-gray-400 border border-gray-200': step.status === 'pending' && index > selectedInvoice.currentStepIndex
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
                                                                <span v-if="step.status === 'pending' && index === selectedInvoice.currentStepIndex" class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800">
                                                                    順番待ち
                                                                </span>
                                                                <button 
                                                                    v-if="step.id.startsWith('h_ext_') && step.status === 'pending'" 
                                                                    @click="handleRemoveApprover(step.id)" 
                                                                    class="text-gray-400 hover:text-red-500 transition-colors p-0.5 rounded hover:bg-red-50"
                                                                >
                                                                    <XCircle class="w-4 h-4" />
                                                                </button>
                                                            </p>
                                                            <p v-if="step.approverName" class="text-xs text-gray-500">{{ step.approverName }}</p>
                                                            <div v-if="step.comment" class="mt-2 text-sm text-gray-700 bg-red-50/50 border border-rose-100 rounded-lg p-3 relative shadow-sm">
                                                                <div class="flex gap-2">
                                                                    <MessageSquareWarning v-if="step.status === 'rejected'" class="h-4 w-4 text-rose-500 shrink-0" />
                                                                    <p class="text-xs leading-relaxed" :class="{'text-rose-800': step.status === 'rejected'}">{{ step.comment }}</p>
                                                                </div>
                                                            </div>

                                                            <!-- Ad-Hoc Approver -->
                                                            <div v-if="index === selectedInvoice.approvalHistory.length - 1 && selectedInvoice.status === 'pending'" class="mt-4 pt-4 border-t border-gray-100 border-dashed">
                                                                <button v-if="!isAddingApprover" @click="isAddingApprover = true" class="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2.5 py-1.5 rounded-lg border border-blue-100 hover:bg-blue-100 transition-colors">
                                                                    <Plus class="w-3.5 h-3.5 mr-1" />
                                                                    次の承認者を追加
                                                                </button>
                                                                <div v-else class="bg-gray-50 border border-gray-200 rounded-lg p-3">
                                                                    <select v-model="selectedExtraApproverId" class="block w-full rounded-md border-gray-300 border shadow-sm focus:border-blue-500 focus:ring-blue-500 text-xs py-1.5 px-2 mb-2 bg-white">
                                                                        <option value="" disabled>選択してください</option>
                                                                        <option v-for="user in availableApproversToAdd" :key="user.id" :value="user.id">
                                                                            {{ user.roleName }} - {{ user.name }}
                                                                        </option>
                                                                    </select>
                                                                    <div class="flex gap-2">
                                                                        <button @click="handleAddApprover" class="bg-blue-600 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-blue-700 disabled:opacity-50" :disabled="!selectedExtraApproverId">追加</button>
                                                                        <button @click="isAddingApprover = false" class="text-gray-500 hover:text-gray-700 px-2 py-1.5 rounded-md text-xs font-medium bg-white border border-gray-200">キャンセル</button>
                                                                    </div>
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

                        <!-- Right Panel: Viewer & Action -->
                        <div class="lg:col-span-7 flex flex-col gap-4">
                            <!-- Placeholder Viewer -->
                            <div class="bg-slate-200/50 rounded-xl overflow-hidden border border-gray-200 shadow-inner relative flex-1 min-h-[400px] flex items-center justify-center">
                                <div class="text-center text-gray-400">
                                    <FileText class="w-16 h-16 mx-auto mb-2 opacity-50" />
                                    <p class="font-medium">請求書プレビュー</p>
                                    <p class="text-xs">(OCR/PDFが表示されます)</p>
                                </div>
                            </div>

                            <!-- Action Area -->
                            <div v-if="selectedInvoice.status === 'pending'" class="bg-white border border-gray-200 rounded-xl p-5 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]">
                                <div class="mb-4">
                                    <h3 class="text-sm font-bold text-gray-900 mb-2">承認/差戻しコメント（任意）</h3>
                                    <textarea 
                                        v-model="actionComment"
                                        rows="2" 
                                        class="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-3 border resize-none bg-gray-50/50" 
                                        placeholder="確認いたしました。支払いを承認します。"
                                    ></textarea>
                                </div>

                                <div class="flex gap-3">
                                    <button 
                                        @click="handleReject"
                                        :disabled="isSubmittingAction"
                                        class="flex-[1] bg-white hover:bg-rose-50 border border-rose-200 text-rose-600 hover:text-rose-700 font-semibold py-3 px-4 rounded-xl shadow-sm transition-colors text-sm flex items-center justify-center gap-2"
                                    >
                                        <XCircle class="w-4 h-4"/>
                                        差戻し
                                    </button>
                                    <button 
                                        @click="handleApprove"
                                        :disabled="isSubmittingAction"
                                        class="flex-[2] bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-xl shadow-md flex justify-center items-center transition-all text-sm gap-2"
                                    >
                                        <svg v-if="isSubmittingAction" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        <CheckCircle v-if="!isSubmittingAction" class="w-4 h-4" />
                                        {{ isSubmittingAction ? '処理中...' : '支払承認する' }}
                                    </button>
                                </div>
                            </div>
                            
                            <div v-else class="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center text-sm text-gray-500">
                                この請求書は現在アクションを必要としていません。
                            </div>
                        </div>

                    </div>
                </div>
            </div>
        </div>
    </div>
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
