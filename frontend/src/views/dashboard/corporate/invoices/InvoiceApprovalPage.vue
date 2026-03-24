<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
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
import { useInvoices } from '@/composables/useInvoices';
import InvoiceDetailModal from '@/components/invoices/InvoiceDetailModal.vue';

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
  issuedDate: string;
  dueDate: string;
  category: string;
  paymentMethod: string;
  memo: string;
  status: 'pending' | 'approved' | 'rejected';
  currentStepIndex: number; 
  approvalHistory: ApprovalHistory[];
  imageUrl: string;
}

const formatAmount = (num: number) => new Intl.NumberFormat('ja-JP').format(num);

// --- STATE ---
const { invoices: apiInvoices, fetchInvoices } = useInvoices();
const activeDirection = ref<'received' | 'issued'>('received');
const mockInvoices = ref<InvoiceItem[]>([]);

const mapApiInvoice = (inv: any): InvoiceItem => {
  const history = (inv.approval_history && inv.approval_history.length > 0)
    ? inv.approval_history.map((h: any, i: number) => ({
        id: h.id ?? `h_${i}`,
        step: h.step ?? i + 1,
        roleId: h.role_id ?? 'accounting',
        roleName: h.role_name ?? '経理担当',
        approverId: h.approver_id,
        approverName: h.approver_name,
        status: h.status ?? 'pending',
        actionDate: h.action_date,
        comment: h.comment,
      }))
    : [];

  const extraSteps = (inv.extra_approval_steps || []).map((s: any, i: number) => ({
      id: `h_ext_${Date.now()}_${i}`,
      step: history.length + i + 1,
      roleId: s.roleId,
      roleName: s.roleName,
      approverName: s.approverName,
      status: 'pending' as const,
  }));

  const combinedHistory = [...history, ...extraSteps];

  return {
    id: inv.id ?? inv._id,
    vendorName: inv.vendor_name ?? inv.client_name ?? '不明',
    title: inv.title ?? inv.description ?? '請求書',
    amount: inv.total_amount ?? inv.amount ?? 0,
    issuedDate: inv.issue_date ?? '',
    dueDate: inv.due_date ?? '',
    category: inv.category ?? '未分類',
    paymentMethod: inv.payment_method ?? '請求書払い',
    memo: inv.memo ?? '',
    status: inv.status === 'approved' ? 'approved' : inv.status === 'rejected' ? 'rejected' : 'pending',
    currentStepIndex: inv.current_step ? inv.current_step - 1 : 0,
    approvalHistory: combinedHistory.length > 0
      ? combinedHistory
      : [{ id: 'h_default', step: 1, roleId: 'accounting', roleName: '承認担当', status: (inv.status === 'approved' ? 'approved' : inv.status === 'rejected' ? 'rejected' : 'pending') as any }],
    imageUrl: (inv.attachments && inv.attachments.length > 0) ? inv.attachments[0] : (inv.image_url ?? ''),
  };
};

const loadData = async () => {
    await fetchInvoices({ direction: activeDirection.value });
    mockInvoices.value = (apiInvoices.value as any[]).map(mapApiInvoice);
};

onMounted(loadData);

watch(activeDirection, loadData);

// --- TAB STATE ---
type TabView = 'pending' | 'pending_all' | 'approved' | 'rejected';
const activeTab = ref<TabView>('pending');

const selectedInvoice = ref<InvoiceItem | null>(null);
const isDetailModalOpen = ref(false);

// Computed Filters
const pendingInvoices = computed(() => mockInvoices.value.filter(i => i.status === 'pending' && i.approvalHistory[i.currentStepIndex]?.roleId === 'accounting'));
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
  isDetailModalOpen.value = true;
};

const closeDetail = () => {
  isDetailModalOpen.value = false;
  setTimeout(() => { selectedInvoice.value = null; }, 300);
};

const handleActionCompleted = async () => {
  closeDetail();
  await loadData();
};

</script>

<template>
  <div class="space-y-6">
    <!-- Header Area -->
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">請求書承認状況</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          {{ activeDirection === 'received' ? '仕入先から届いた請求書の支払内容を確認し、承認・差戻しを行います。' : '発行を予定している請求書の内容を確認し、承認・差戻しを行います。' }}
        </p>
      </div>

      <!-- Direction Toggle -->
      <div class="inline-flex p-1 bg-gray-100 rounded-xl shadow-inner border border-gray-200">
          <button 
            @click="activeDirection = 'received'"
            class="px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 flex items-center gap-2"
            :class="activeDirection === 'received' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
          >
            <Clock class="w-4 h-4" v-if="activeDirection === 'received'" />
            受領請求書
          </button>
          <button 
            @click="activeDirection = 'issued'"
            class="px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 flex items-center gap-2"
            :class="activeDirection === 'issued' ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
          >
            <CheckCircle class="w-4 h-4" v-if="activeDirection === 'issued'" />
            発行請求書
          </button>
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
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-32">
                            {{ activeDirection === 'issued' ? '発行日 / 支払期日' : '受領日 / 支払期限' }}
                        </th>
                        <th scope="col" class="px-6 py-3.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                            {{ activeDirection === 'issued' ? '取引先情報' : '仕入先情報' }}
                        </th>
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
                           <div class="text-[11px] text-gray-400 font-normal mt-1 bg-red-50 text-red-600 rounded px-1.5 py-0.5 inline-block">期日: {{ invoice.dueDate }}</div>
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


    <!-- Detail Modal -->
    <InvoiceDetailModal
        :show="isDetailModalOpen"
        :invoice="selectedInvoice"
        :direction="activeDirection"
        @close="closeDetail"
        @action-completed="handleActionCompleted"
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
