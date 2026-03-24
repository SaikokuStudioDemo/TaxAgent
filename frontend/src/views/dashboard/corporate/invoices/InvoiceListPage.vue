<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { 
    Search, 
    Filter, 
    Building2,
    UserCircle2,
    Upload,
    Send,
    Calendar,
    Trash2,
    FileText,
    XCircle,
    Plus,
    CheckCircle,
    Clock,
    ChevronDown,
    CheckCircle2,
    ArrowUpRight,
    MoreVertical,
    Download,
    ExternalLink,
    Printer,
    Share2,
    AlertCircle
} from 'lucide-vue-next';
import { useRouter } from 'vue-router';
import { useInvoices } from '@/composables/useInvoices';
import ApprovalStepper from '@/components/approvals/ApprovalStepper.vue';

const router = useRouter();

// Tabs: 'issued' (発行), 'received' (受領), 'drafts' (下書き)
const activeTab = ref<'issued' | 'received' | 'drafts'>('issued');
const searchQuery = ref('');

const { invoices, fetchInvoices, bulkAction, deleteInvoice } = useInvoices();
const expandedInvoiceIds = ref<string[]>([]);
const selectedInvoiceIds = ref<string[]>([]);

const isAllSelected = computed(() => {
    return filteredInvoices.value.length > 0 && selectedInvoiceIds.value.length === filteredInvoices.value.length;
});

const toggleSelectAll = () => {
    if (isAllSelected.value) {
        selectedInvoiceIds.value = [];
    } else {
        selectedInvoiceIds.value = filteredInvoices.value.map(i => i.id);
    }
};

const showConfirmModal = ref(false);
const showRedirectLoading = ref(false);
const confirmConfig = ref({
    title: '',
    message: '',
    confirmText: '',
    confirmAction: null as (() => Promise<void>) | null,
    isDanger: false
});

const openConfirmModal = (config: typeof confirmConfig.value) => {
    confirmConfig.value = config;
    showConfirmModal.value = true;
};

const handleBulkDelete = () => {
    if (!selectedInvoiceIds.value.length) return;
    openConfirmModal({
        title: '一括削除の確認',
        message: `${selectedInvoiceIds.value.length}件のデータを削除しますか？この操作は取り消せません。`,
        confirmText: '削除する',
        isDanger: true,
        confirmAction: async () => {
            const ok = await bulkAction(selectedInvoiceIds.value, 'delete');
            if (ok) selectedInvoiceIds.value = [];
        }
    });
};

const handleBulkSend = () => {
    if (!selectedInvoiceIds.value.length) return;

    // Evaluate approval requirements
    const unapproved = invoices.value.filter(i => 
        selectedInvoiceIds.value.includes(i.id) && 
        i.approval_rule_id && 
        i.review_status !== 'approved'
    );

    if (unapproved.length > 0) {
        alert('承認プロセスが完了していない請求書が含まれています（または承認待ちです）。\nすべて承認済みの請求書のみ発行可能です。');
        return;
    }

    openConfirmModal({
        title: '一括発行の確認',
        message: `${selectedInvoiceIds.value.length}件の請求書を一括で発行・送付しますか？`,
        confirmText: '発行する',
        isDanger: false,
        confirmAction: async () => {
            const ok = await bulkAction(selectedInvoiceIds.value, 'send');
            if (ok) {
                selectedInvoiceIds.value = [];
                await fetchInvoices();
            }
        }
    });
};

const handleDeleteSingle = (id: string) => {
    openConfirmModal({
        title: 'データの削除',
        message: 'このデータを削除しますか？この操作は取り消せません。',
        confirmText: '削除する',
        isDanger: true,
        confirmAction: async () => {
            await deleteInvoice(id);
        }
    });
};

const handleEditSingle = async (id: string) => {
    showRedirectLoading.value = true;
    // Brief delay to show loading state as requested
    await new Promise(resolve => setTimeout(resolve, 800));
    router.push({ path: '/dashboard/corporate/invoices/create', query: { id } });
};

const selectedPreviewInvoice = ref<any | null>(null);
const isPreviewModalOpen = ref(false);

const openPreview = (invoice: any) => {
    selectedPreviewInvoice.value = invoice;
    isPreviewModalOpen.value = true;
};
const closePreview = () => {
    isPreviewModalOpen.value = false;
    setTimeout(() => { selectedPreviewInvoice.value = null; }, 300);
};

// Fetch all invoices to calculate counts and allow filtering
const loadInvoices = async () => {
    await fetchInvoices();
};

onMounted(loadInvoices);
// No need to watch activeTab if we fetch all once, but we can keep it if we want to refresh

// Map API invoice to display format
type InvoiceStatus = 'draft' | 'pending_send' | 'sent_unmatched' | 'matched' | 'overdue_unmatched' | 'received_unmatched' | 'received_matched';

const mapStatus = (inv: any): InvoiceStatus => {
    if (inv.status === 'draft') return 'draft';
    if (inv.status === 'matched') return inv.direction === 'received' ? 'received_matched' : 'matched';
    if (inv.direction === 'received') return 'received_unmatched';
    if (inv.status === 'sent') return 'sent_unmatched';
    return 'pending_send';
};

const filteredInvoices = computed(() => {
    let list = invoices.value.map(inv => ({
        ...inv,
        displayStatus: mapStatus(inv),
        clientName: inv.client_name,
        clientId: inv.client_id,
        totalAmount: inv.total_amount,
        issueDate: inv.issue_date,
        dueDate: inv.due_date,
        title: `${inv.invoice_number ?? ''} ${inv.client_name ?? ''}`.trim(),
        amount: inv.total_amount,
        // Template compatibility fields
        clientType: 'corporate',
        type: 'single',
        recurringDetails: undefined,
        projectName: undefined,
        reviewStatus: inv.review_status,
        approval_history: (inv as any).approval_history || [],
        current_step_index: (inv as any).current_step_index || 0,
        lineItems: inv.line_items,
    }));

    if (activeTab.value === 'issued') {
        list = list.filter(i => i.direction === 'issued' && i.status !== 'draft');
    } else if (activeTab.value === 'received') {
        list = list.filter(i => i.direction === 'received');
    } else if (activeTab.value === 'drafts') {
        list = list.filter(i => i.status === 'draft');
    }

    if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        list = list.filter(i =>
            i.clientName?.toLowerCase().includes(q) ||
            i.invoice_number?.toLowerCase().includes(q)
        );
    }

    return list;
});

const issuedCount = computed(() => invoices.value.filter(i => i.direction === 'issued' && i.status !== 'draft').length);
const receivedCount = computed(() => invoices.value.filter(i => i.direction === 'received').length);
const draftsCount = computed(() => invoices.value.filter(i => i.status === 'draft').length);

const toggleExpansion = (id: string) => {
    const idx = expandedInvoiceIds.value.indexOf(id);
    if (idx > -1) {
        expandedInvoiceIds.value.splice(idx, 1);
    } else {
        expandedInvoiceIds.value.push(id);
    }
};

const formatCurrency = (amount: number) => new Intl.NumberFormat('ja-JP').format(amount || 0);

const currentMonth = new Date().toISOString().slice(0, 7);
const issuedSummary = computed(() => {
    const list = invoices.value.filter(i => i.direction === 'issued');
    const thisMonth = list.filter(i => i.issue_date?.startsWith(currentMonth));
    const matched = list.filter(i => i.status === 'matched');
    const unmatched = list.filter(i => i.status !== 'matched' && i.status !== 'draft');
    const overdue = list.filter(i =>
        i.status !== 'matched' &&
        i.due_date && new Date(i.due_date) < new Date()
    );
    return {
        totalPlanned: thisMonth.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalMatched: matched.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalUnmatched: unmatched.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalOverdue: overdue.reduce((s, i) => s + (i.total_amount || 0), 0),
        overdueCount: overdue.length,
    };
});

const receivedSummary = computed(() => {
    const list = invoices.value.filter(i => i.direction === 'received');
    const thisMonth = list.filter(i => i.issue_date?.startsWith(currentMonth));
    const matched = list.filter(i => i.status === 'matched' || i.status === 'received_matched');
    const unmatched = list.filter(i => i.status !== 'matched' && i.status !== 'received_matched' && i.status !== 'draft');
    
    return {
        totalPlanned: thisMonth.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalMatched: matched.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalUnmatched: unmatched.reduce((s, i) => s + (i.total_amount || 0), 0),
    };
});

const getStatusBadge = (status: InvoiceStatus) => {
    switch(status) {
        case 'sent_unmatched': return { label: '未消込 (送付済)', classes: 'bg-blue-50 text-blue-700 border-blue-200', icon: Send };
        case 'matched': return { label: '消込済 (入金済)', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle };
        case 'pending_send': return { label: '未消込 (未送付)', classes: 'bg-amber-50 text-amber-700 border-amber-200', icon: FileText };
        case 'overdue_unmatched': return { label: '未消込 (期限超過)', classes: 'bg-red-50 text-red-700 border-red-200', icon: Clock };
        case 'draft': return { label: '下書き', classes: 'bg-gray-100 text-gray-700 border-gray-200', icon: FileText };
        case 'received_unmatched': return { label: '未消込 (支払待ち)', classes: 'bg-amber-50 text-amber-700 border-amber-200', icon: Clock };
        case 'received_matched': return { label: '消込済 (支払完了)', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle };
        default: return { label: '不明', classes: 'bg-gray-100 text-gray-700 border-gray-200', icon: FileText };
    }
};

const getReviewBadge = (status?: string) => {
    switch (status) {
        case 'approved':  return { label: '支払承認済', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
        case 'rejected':  return { label: '差戻し', classes: 'bg-red-50 text-red-700 border-red-200' };
        default:          return { label: '承認待ち', classes: 'bg-orange-50 text-orange-700 border-orange-200' };
    }
};

const navigateToCreate = () => router.push('/dashboard/corporate/invoices/create');
</script>

<template>
  <div class="relative h-full">
    <div class="h-full flex flex-col bg-slate-50">
      <!-- Header -->
      <header class="bg-white border-b border-gray-200 px-8 py-6 shrink-0 z-10">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">請求書一覧</h1>
          <p class="text-sm text-gray-500 mt-1">作成した請求書データと、受領した請求書データを一元管理します</p>
        </div>
        <div class="flex items-center gap-3">
          <button v-if="activeTab === 'issued'" @click="navigateToCreate" class="bg-blue-600 text-white px-5 py-2.5 rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm flex items-center shadow-sm">
            <Plus class="w-4 h-4 mr-2" />請求書データを作成
          </button>
          
          <button v-if="activeTab === 'received'" @click="router.push('/dashboard/corporate/invoices/receive')" class="bg-indigo-600 text-white px-5 py-2.5 rounded-lg hover:bg-indigo-700 transition-colors font-medium text-sm flex items-center shadow-sm">
            <Upload class="w-4 h-4 mr-2" />受領データをアップロード
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 overflow-x-hidden overflow-y-auto bg-slate-50 p-8">
      
      <!-- Tabs (Full Width) -->
      <div class="flex bg-gray-200/50 p-1.5 rounded-xl mb-6 shadow-inner border border-gray-200/50">
        <button 
          @click="activeTab = 'issued'" 
          class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'issued' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <Send class="w-4 h-4" />
          発行 <span class="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ issuedCount }}</span>
        </button>
        <button 
          @click="activeTab = 'received'" 
          class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'received' ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <Upload class="w-4 h-4" />
          受領 <span class="bg-indigo-100 text-indigo-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ receivedCount }}</span>
        </button>
        <button 
          @click="activeTab = 'drafts'" 
          class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'drafts' ? 'bg-white text-slate-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <Clock class="w-4 h-4" />
          下書き <span class="bg-gray-200 text-gray-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ draftsCount }}</span>
        </button>
      </div>

      <!-- Summary Cards (Show for Issued and Received tabs) -->
      <div v-if="activeTab === 'issued'" class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">今月の売上予定</p>
                <div class="bg-blue-50 p-2 rounded-lg"><Calendar class="w-4 h-4 text-blue-600" /></div>
            </div>
            <p class="text-2xl font-bold text-gray-900">¥{{ formatCurrency(issuedSummary.totalPlanned) }}</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">消込済 (入金済)</p>
                <div class="bg-emerald-50 p-2 rounded-lg"><CheckCircle class="w-4 h-4 text-emerald-600" /></div>
            </div>
            <p class="text-2xl font-bold text-emerald-600">¥{{ formatCurrency(issuedSummary.totalMatched) }}</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">未消込 (作成・送付済)</p>
                <div class="bg-amber-50 p-2 rounded-lg"><Clock class="w-4 h-4 text-amber-600" /></div>
            </div>
            <p class="text-2xl font-bold text-amber-600">¥{{ formatCurrency(issuedSummary.totalUnmatched) }}</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200 border-l-4 border-l-red-500">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">未消込 (期限超過)</p>
                <div class="bg-red-50 p-2 rounded-lg"><Clock class="w-4 h-4 text-red-600" /></div>
            </div>
            <p class="text-2xl font-bold text-red-600">¥{{ formatCurrency(issuedSummary.totalOverdue) }} <span class="text-xs font-normal text-gray-500 ml-1">({{ issuedSummary.overdueCount }}件)</span></p>
        </div>
      </div>

      <div v-if="activeTab === 'received'" class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">今月の支払予定</p>
                <div class="bg-indigo-50 p-2 rounded-lg"><Calendar class="w-4 h-4 text-indigo-600" /></div>
            </div>
            <p class="text-2xl font-bold text-gray-900">¥{{ formatCurrency(receivedSummary.totalPlanned) }}</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">消込済 (支払完了)</p>
                <div class="bg-emerald-50 p-2 rounded-lg"><CheckCircle class="w-4 h-4 text-emerald-600" /></div>
            </div>
            <p class="text-2xl font-bold text-emerald-600">¥{{ formatCurrency(receivedSummary.totalMatched) }}</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">未消込 (支払待ち)</p>
                <div class="bg-amber-50 p-2 rounded-lg"><Clock class="w-4 h-4 text-amber-600" /></div>
            </div>
            <p class="text-2xl font-bold text-amber-600">¥{{ formatCurrency(receivedSummary.totalUnmatched) }}</p>
        </div>
      </div>

      <!-- Search & Filters (Moved below Summary Cards) -->
      <div class="mb-6 flex flex-col md:flex-row gap-4 items-center justify-between">
        <div class="flex items-center gap-3 w-full">
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input v-model="searchQuery" type="text" placeholder="取引先名、タイトル、請求書番号で検索..." class="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/10 focus:border-blue-500 bg-white shadow-sm" />
          </div>
          <button class="bg-white border border-gray-200 text-gray-700 px-4 py-2.5 rounded-lg hover:bg-gray-50 transition-colors shadow-sm shrink-0 flex items-center gap-2 text-sm font-medium">
            <Filter class="w-4 h-4" /> フィルター
          </button>
        </div>
      </div>

      <!-- Data Table -->
      <div class="bg-white shadow-sm rounded-xl border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 table-fixed">
            <thead class="bg-gray-50/80">
              <tr>
                <th scope="col" class="w-12 px-6 py-4 text-center">
                    <input type="checkbox" :checked="isAllSelected" @change="toggleSelectAll" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer">
                </th>
                <th scope="col" class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider w-40">請求書番号 / 発行日</th>
                <th scope="col" class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider w-64">取引先</th>
                <th scope="col" class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">件名 / プロジェクト</th>
                <th scope="col" class="px-6 py-4 text-right text-xs font-bold text-gray-500 uppercase tracking-wider w-36">金額 (税込)</th>
                <th scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-40">全体ステータス</th>
                <th v-if="activeTab === 'received'" scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-36">承認状況</th>
                <th scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-20">詳細</th>
                <th scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-20">削除</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <template v-for="invoice in filteredInvoices" :key="invoice.id">
              <tr 
                class="hover:bg-blue-50/30 transition-colors group cursor-pointer"
                @click="toggleExpansion(invoice.id)"
              >
                <td class="px-6 py-4 whitespace-nowrap text-center" @click.stop>
                    <input type="checkbox" :value="invoice.id" v-model="selectedInvoiceIds" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer">
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    <div class="font-bold text-gray-900 text-sm mb-1">{{ invoice.id }}</div>
                    <div class="text-xs text-gray-500 flex items-center gap-1">
                        <Calendar class="w-3 h-3" /> {{ invoice.issueDate }}
                    </div>
                </td>
                <td class="px-6 py-4">
                    <div class="flex items-center gap-2 mb-1">
                        <component :is="invoice.clientType === 'student' ? UserCircle2 : Building2" class="w-4 h-4" :class="invoice.clientType === 'student' ? 'text-emerald-500' : 'text-blue-500'" />
                        <span class="font-bold text-gray-900 text-sm truncate" :title="invoice.clientName">{{ invoice.clientName }}</span>
                    </div>
                    <div class="text-xs text-gray-500 truncate" :title="invoice.clientId">ID: {{ invoice.clientId }}</div>
                </td>
                <td class="px-6 py-4">
                    <div class="font-bold text-gray-900 text-sm mb-1">{{ invoice.title }}</div>
                    <div class="flex items-center gap-2">
                        <span v-if="invoice.type === 'recurring'" class="bg-purple-50 text-purple-700 border border-purple-200 px-2 py-0.5 rounded text-[10px] font-bold inline-flex items-center">
                            自動生成 ({{ invoice.recurringDetails }})
                        </span>
                        <span v-if="invoice.projectName" class="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-[10px] font-medium border border-gray-200">
                            {{ invoice.projectName }}
                        </span>
                    </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-right">
                    <div class="font-black text-gray-900">¥{{ formatCurrency(invoice.amount) }}</div>
                    <div class="text-[11px] text-gray-500 mt-0.5">期日: {{ invoice.dueDate }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-center">
                    <span class="inline-flex items-center px-2.5 py-1.5 rounded-md text-xs font-bold border" :class="getStatusBadge(invoice.displayStatus).classes">
                        <component :is="getStatusBadge(invoice.displayStatus).icon" class="w-3.5 h-3.5 mr-1.5" />
                        {{ getStatusBadge(invoice.displayStatus).label }}
                    </span>
                </td>
                <!-- Approval status column (received tab only) -->
                <td v-if="activeTab === 'received'" class="px-6 py-4 whitespace-nowrap text-center">
                    <span class="inline-flex items-center px-2.5 py-1.5 rounded-md text-xs font-bold border" :class="getReviewBadge(invoice.reviewStatus).classes">
                        {{ getReviewBadge(invoice.reviewStatus).label }}
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-center">
                    <button 
                      @click.stop="openPreview(invoice)"
                      class="p-2 text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors inline-flex items-center justify-center" 
                      title="詳細を見る"
                    >
                         <FileText class="w-5 h-5" />
                    </button>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-center">
                    <button 
                      @click.stop="handleDeleteSingle(invoice.id)"
                      class="p-2 text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors inline-flex items-center justify-center" 
                      title="削除"
                    >
                        <Trash2 class="w-5 h-5" />
                    </button>
                </td>
              </tr>
              
              <!-- Accordion Row for Line Items -->
              <tr v-if="expandedInvoiceIds.includes(invoice.id) && invoice.lineItems && invoice.lineItems.length > 0" class="bg-slate-50 border-t-0">
                  <td :colspan="activeTab === 'received' ? 9 : 8" class="p-0">
                      <div class="px-14 py-4 border-l-4 border-l-blue-400 bg-blue-50/20 shadow-inner">
                          <p class="text-xs font-bold text-gray-500 mb-3 flex items-center">
                              <FileText class="w-4 h-4 mr-1.5" /> 請求明細 ({{ invoice.lineItems.length }}件)
                          </p>
                          <table class="w-full text-sm">
                              <thead class="bg-white/60 border-b border-gray-200">
                                  <tr>
                                      <th class="py-2 px-4 text-left font-medium text-gray-500 w-1/2">品目名</th>
                                      <th class="py-2 px-4 text-right font-medium text-gray-500">税率</th>
                                      <th class="py-2 px-4 text-right font-medium text-gray-500">金額 (税抜)</th>
                                  </tr>
                              </thead>
                              <tbody class="divide-y divide-gray-100">
                                  <tr v-for="(item, idx) in invoice.lineItems" :key="idx" class="hover:bg-white transition-colors">
                                      <td class="py-2.5 px-4 font-medium text-gray-800">{{ item.description }}</td>
                                      <td class="py-2.5 px-4 text-right text-gray-600">{{ item.tax_rate }}%</td>
                                      <td class="py-2.5 px-4 text-right font-bold text-gray-900">¥{{ formatCurrency(item.amount) }}</td>
                                  </tr>
                              </tbody>
                          </table>
                      </div>
                  </td>
              </tr>
              </template>
              
              <tr v-if="filteredInvoices.length === 0">
                <td colspan="7" class="px-6 py-16 text-center text-gray-500">
                    <FileText class="w-12 h-12 text-gray-300 mx-auto mb-3" />
                    <p class="text-sm font-medium">条件に一致する請求書が見つかりませんでした。</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        
        <!-- Pagination -->
        <div v-if="filteredInvoices.length > 0" class="bg-gray-50 px-6 py-3 border-t border-gray-200 flex items-center justify-between">
            <span class="text-sm text-gray-500">全 {{ filteredInvoices.length }} 件中 1-{{ filteredInvoices.length }} 件を表示</span>
            <div class="flex gap-1">
                <button class="px-3 py-1 border border-gray-300 rounded bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-50 text-sm">前のページ</button>
                <button class="px-3 py-1 border border-gray-300 rounded bg-white text-gray-700 hover:bg-gray-50 text-sm font-medium">次のページ</button>
            </div>
        </div>
      </div>
    </main>

    <!-- Floating Bulk Action Bar -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="transform translate-y-12 opacity-0"
      enter-to-class="transform translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="transform translate-y-0 opacity-100"
      leave-to-class="transform translate-y-12 opacity-0"
    >
      <div v-if="selectedInvoiceIds.length > 0" class="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
        <div class="bg-gray-900 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-6 border border-white/10 backdrop-blur-xl">
          <div class="flex items-center gap-3 pr-6 border-r border-white/20">
            <div class="bg-blue-500 text-white text-xs font-black h-6 w-6 rounded-full flex items-center justify-center">
              {{ selectedInvoiceIds.length }}
            </div>
            <span class="text-sm font-bold">選択中</span>
          </div>
          
          <div class="flex items-center gap-3">
            <button 
              v-if="activeTab === 'drafts'"
              @click="handleBulkSend"
              class="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-bold transition-colors"
            >
              <Send class="w-4 h-4" /> 一括発行・送付
            </button>
            <button 
              @click="handleBulkDelete"
              class="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-red-500 rounded-lg text-sm font-bold transition-all"
            >
              <Trash2 class="w-4 h-4" /> 一括削除
            </button>
            <button 
              @click="selectedInvoiceIds = []"
              class="text-gray-400 hover:text-white text-sm font-medium px-2"
            >
              キャンセル
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Custom Confirmation Modal -->
    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div v-if="showConfirmModal" class="fixed inset-0 z-[100] flex items-center justify-center p-4">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-gray-900/60 backdrop-blur-sm" @click="showConfirmModal = false"></div>
        
        <!-- Modal Content -->
        <div class="relative bg-white rounded-2xl shadow-2xl max-w-md w-full p-8 overflow-hidden">
          <div class="flex items-center gap-4 mb-6">
            <div :class="confirmConfig.isDanger ? 'bg-red-50' : 'bg-blue-50'" class="p-3 rounded-full">
              <AlertCircleIcon :class="confirmConfig.isDanger ? 'text-red-600' : 'text-blue-600'" class="w-6 h-6" />
            </div>
            <h3 class="text-xl font-bold text-gray-900">{{ confirmConfig.title }}</h3>
          </div>
          
          <p class="text-gray-600 mb-8 leading-relaxed">{{ confirmConfig.message }}</p>
          
          <div class="flex gap-3 justify-end">
            <button 
              @click="showConfirmModal = false"
              class="px-5 py-2.5 rounded-lg text-sm font-bold border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              キャンセル
            </button>
            <button 
              @click="async () => { if (confirmConfig.confirmAction) await confirmConfig.confirmAction(); showConfirmModal = false; }"
              :class="confirmConfig.isDanger ? 'bg-red-600 hover:bg-red-700 shadow-red-200' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-200'"
              class="px-6 py-2.5 rounded-lg text-sm font-bold text-white shadow-lg transition-all"
            >
              {{ confirmConfig.confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Transition Loading Overlay -->
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="showRedirectLoading" class="fixed inset-0 z-[150] bg-white/80 backdrop-blur-md flex flex-col items-center justify-center">
        <div class="relative w-24 h-24 mb-6">
          <div class="absolute inset-0 border-4 border-blue-100 rounded-full"></div>
          <div class="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
          <FileText class="absolute inset-0 m-auto w-8 h-8 text-blue-600 animate-pulse" />
        </div>
        <h2 class="text-xl font-bold text-gray-900 mb-2">下書きを読み込んでいます</h2>
        <p class="text-gray-500 font-medium tracking-wide">編集画面へ移動します...</p>
      </div>
    </Transition>

    <!-- Preview Modal -->
    <Teleport to="body">
    <div v-if="isPreviewModalOpen && selectedPreviewInvoice" class="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6" aria-labelledby="slide-over-title" role="dialog" aria-modal="true">
        <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity" @click="closePreview"></div>
        <div class="relative w-full max-w-5xl h-[95vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
            <div class="h-full flex flex-col w-full overflow-y-auto bg-slate-50 relative">
                <!-- Header -->
                <div class="px-6 py-4 bg-white border-b border-gray-200 flex items-center justify-between sticky top-0 z-10 shadow-sm">
                    <div>
                        <h2 class="text-lg font-bold text-gray-900" id="slide-over-title">請求書プレビュー : {{ selectedPreviewInvoice.id }}</h2>
                        <p class="text-xs text-gray-500 mt-1">取引先: <span class="font-medium text-gray-700">{{ selectedPreviewInvoice.clientName }}</span></p>
                    </div>
                    <button @click="closePreview" class="rounded-full p-2 bg-gray-50 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <span class="sr-only">Close panel</span>
                        <XCircle class="h-6 w-6" aria-hidden="true" />
                    </button>
                </div>
                <!-- Content Area -->
                <div class="flex-1 overflow-y-auto p-6 space-y-6">
                    <!-- Unified Approval Stepper -->
                    <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
                        <ApprovalStepper 
                            :document-type="activeTab === 'issued' || activeTab === 'drafts' ? 'issued_invoice' : 'received_invoice'"
                            mode="status"
                            :history="selectedPreviewInvoice.approval_history || []"
                            :current-step="selectedPreviewInvoice.current_step_index !== undefined ? selectedPreviewInvoice.current_step_index + 1 : 1"
                        />
                    </div>
                    <!-- Invoice Info -->
                    <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
                        <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-3">基本情報</h3>
                        <dl class="grid grid-cols-2 gap-4 text-sm">
                            <div class="col-span-2 flex justify-between items-center bg-gray-50 p-3 rounded-lg border border-gray-100">
                                <span class="text-gray-600 font-medium">合計金額</span>
                                <span class="text-2xl font-bold tracking-tight">¥{{ formatCurrency(selectedPreviewInvoice.amount) }}</span>
                            </div>
                            <div>
                                <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">発行日</dt>
                                <dd class="font-medium text-gray-900">{{ selectedPreviewInvoice.issueDate }}</dd>
                            </div>
                            <div>
                                <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">支払期日</dt>
                                <dd class="font-medium text-gray-900">{{ selectedPreviewInvoice.dueDate }}</dd>
                            </div>
                            <div class="col-span-2">
                                <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">件名</dt>
                                <dd class="font-medium text-gray-900">{{ selectedPreviewInvoice.title }}</dd>
                            </div>
                        </dl>
                    </div>
                </div>
            </div>
        </div>
    </div>
    </Teleport>
    </div>
  </div>
</template>
