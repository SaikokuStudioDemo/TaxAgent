<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import {
    Search,
    Filter,
    Building2,
    Upload,
    Send,
    Calendar,
    Trash2,
    FileText,
    Plus,
    CheckCircle,
    Clock,
    AlertCircle
} from 'lucide-vue-next';
import { useRouter } from 'vue-router';
import { useInvoices, type Invoice } from '@/composables/useInvoices';
import { api } from '@/lib/api';
import InvoiceDetailModal from '@/components/invoices/InvoiceDetailModal.vue';
import { formatNumber as formatCurrency } from '@/lib/utils/formatters';

const router = useRouter();

// Tabs: 'issued' (発行), 'received' (受領), 'pending_approval' (承認待ち), 'drafts' (下書き)
const activeTab = ref<'issued' | 'received' | 'pending_approval' | 'drafts'>('issued');
const searchQuery = ref('');
const tabCounts = ref({ issued: 0, received: 0, pending_approval: 0, drafts: 0 });

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
        i.approval_status !== 'approved' && i.approval_status !== 'auto_approved'
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

// handleEditSingle removed as it's not currently used in the list view actions

const selectedPreviewInvoice = ref<Invoice | null>(null);
const isPreviewModalOpen = ref(false);

const openPreview = (invoice: Invoice) => {
    selectedPreviewInvoice.value = invoice;
    isPreviewModalOpen.value = true;
};
const closePreview = () => {
    isPreviewModalOpen.value = false;
    setTimeout(() => { selectedPreviewInvoice.value = null; }, 300);
};

const handleModalActionCompleted = async () => {
    closePreview();
    await loadInvoices();
};

const handleStepAdded = (updated: Invoice) => {
    const idx = invoices.value.findIndex(i => i.id === updated.id);
    if (idx !== -1) invoices.value[idx] = { ...invoices.value[idx], extra_approval_steps: updated.extra_approval_steps };
    if (selectedPreviewInvoice.value?.id === updated.id) {
        selectedPreviewInvoice.value = { ...selectedPreviewInvoice.value, extra_approval_steps: updated.extra_approval_steps };
    }
};

// Fetch invoices filtered by active tab via API parameters
const loadInvoices = async () => {
    if (activeTab.value === 'issued') {
        await fetchInvoices({ document_type: 'issued' });
    } else if (activeTab.value === 'received') {
        await fetchInvoices({ document_type: 'received' });
    } else if (activeTab.value === 'pending_approval') {
        await fetchInvoices({ approval_status: 'pending_approval' });
    } else if (activeTab.value === 'drafts') {
        await fetchInvoices({ approval_status: 'draft' });
    }
    tabCounts.value[activeTab.value] = invoices.value.length;
};

const loadAllTabCounts = async () => {
    const [issued, received, pending, drafts] = await Promise.all([
        api.get<any[]>('/invoices?document_type=issued'),
        api.get<any[]>('/invoices?document_type=received'),
        api.get<any[]>('/invoices?approval_status=pending_approval'),
        api.get<any[]>('/invoices?approval_status=draft'),
    ]);
    tabCounts.value = {
        issued: issued.length,
        received: received.length,
        pending_approval: pending.length,
        drafts: drafts.length,
    };
};

onMounted(async () => {
    await Promise.all([loadInvoices(), loadAllTabCounts()]);
});
watch(activeTab, async () => {
    await Promise.all([loadInvoices(), loadAllTabCounts()]);
});

// Map API invoice to display format
type InvoiceStatus = 'draft' | 'pending_approval' | 'pending_send' | 'sent_unmatched' | 'reconciled' | 'overdue_unmatched' | 'received_unmatched' | 'received_reconciled';
type DisplayInvoice = Invoice & { displayStatus: InvoiceStatus };

const mapStatus = (inv: Invoice): InvoiceStatus => {
    if (inv.approval_status === 'draft') return 'draft';
    if (inv.approval_status === 'pending_approval') return 'pending_approval';
    if (inv.reconciliation_status === 'reconciled') return inv.document_type === 'received' ? 'received_reconciled' : 'reconciled';
    if (inv.document_type === 'received') return 'received_unmatched';
    if (inv.delivery_status === 'sent') return 'sent_unmatched';
    return 'pending_send';
};

const filteredInvoices = computed((): DisplayInvoice[] => {
    // API already filtered by tab; apply only search filter here
    let list: DisplayInvoice[] = invoices.value.map(inv => ({
        ...inv,
        displayStatus: mapStatus(inv),
    }));

    if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        list = list.filter(i =>
            i.client_name?.toLowerCase().includes(q) ||
            i.vendor_name?.toLowerCase().includes(q) ||
            i.invoice_number?.toLowerCase().includes(q)
        );
    }

    return list;
});

const issuedCount = computed(() => tabCounts.value.issued);
const receivedCount = computed(() => tabCounts.value.received);
const pendingApprovalCount = computed(() => tabCounts.value.pending_approval);
const draftsCount = computed(() => tabCounts.value.drafts);

const toggleExpansion = (id: string) => {
    const idx = expandedInvoiceIds.value.indexOf(id);
    if (idx > -1) {
        expandedInvoiceIds.value.splice(idx, 1);
    } else {
        expandedInvoiceIds.value.push(id);
    }
};

const currentMonth = new Date().toISOString().slice(0, 7);
const issuedSummary = computed(() => {
    const list = invoices.value.filter(i => i.document_type === 'issued');
    const thisMonth = list.filter(i => i.issue_date?.startsWith(currentMonth));
    const matched = list.filter(i => i.reconciliation_status === 'reconciled');
    const unmatched = list.filter(i => i.reconciliation_status !== 'reconciled' && i.approval_status !== 'draft');
    const overdue = list.filter(i =>
        i.reconciliation_status !== 'reconciled' &&
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
    const list = invoices.value.filter(i => i.document_type === 'received');
    const thisMonth = list.filter(i => i.issue_date?.startsWith(currentMonth));
    const matched = list.filter(i => i.reconciliation_status === 'reconciled');
    const unmatched = list.filter(i => i.reconciliation_status !== 'reconciled' && i.approval_status !== 'draft');
    
    return {
        totalPlanned: thisMonth.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalMatched: matched.reduce((s, i) => s + (i.total_amount || 0), 0),
        totalUnmatched: unmatched.reduce((s, i) => s + (i.total_amount || 0), 0),
    };
});

const getStatusBadge = (status: InvoiceStatus) => {
    switch(status) {
        case 'sent_unmatched': return { label: '未消込 (送付済)', classes: 'bg-blue-50 text-blue-700 border-blue-200', icon: Send };
        case 'reconciled': return { label: '消込済 (入金済)', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle };
        case 'pending_send': return { label: '未消込 (未送付)', classes: 'bg-amber-50 text-amber-700 border-amber-200', icon: FileText };
        case 'overdue_unmatched': return { label: '未消込 (期限超過)', classes: 'bg-red-50 text-red-700 border-red-200', icon: Clock };
        case 'draft': return { label: '下書き', classes: 'bg-gray-100 text-gray-700 border-gray-200', icon: FileText };
        case 'pending_approval': return { label: '承認待ち', classes: 'bg-orange-100 text-orange-700 border-orange-200', icon: Clock };
        case 'received_unmatched': return { label: '未消込 (支払待ち)', classes: 'bg-amber-50 text-amber-700 border-amber-200', icon: Clock };
        case 'received_reconciled': return { label: '消込済 (支払完了)', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle };
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
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">請求書リスト</h1>
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
          @click="activeTab = 'pending_approval'"
          class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'pending_approval' ? 'bg-white text-orange-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <AlertCircle class="w-4 h-4" />
          承認待ち <span class="bg-orange-100 text-orange-700 text-[10px] px-1.5 py-0.5 rounded-full ml-1">{{ pendingApprovalCount }}</span>
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
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50/80">
              <tr>
                <th scope="col" class="w-12 px-4 py-4 text-center">
                    <input type="checkbox" :checked="isAllSelected" @change="toggleSelectAll" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer">
                </th>
                <th scope="col" class="px-4 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider min-w-[120px]">発行日 / 番号</th>
                <th scope="col" class="px-4 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider min-w-[150px]">{{ activeTab === 'received' ? '請求元' : '請求先' }}</th>
                <th scope="col" class="hidden lg:table-cell px-4 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">件名 / プロジェクト</th>
                <th scope="col" class="px-4 py-4 text-right text-xs font-bold text-gray-500 uppercase tracking-wider min-w-[120px]">金額 (税込)</th>
                <th scope="col" class="px-4 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider min-w-[140px]">ステータス</th>
                <th v-if="activeTab === 'received'" scope="col" class="hidden md:table-cell px-4 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider min-w-[100px]">承認状況</th>
                <th scope="col" class="px-4 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-24 sticky right-0 bg-gray-50/90 backdrop-blur shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.1)]">操作</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <template v-for="invoice in filteredInvoices" :key="invoice.id">
              <tr 
                class="hover:bg-blue-50/30 transition-colors group cursor-pointer"
                @click="toggleExpansion(invoice.id)"
              >
                <td class="px-4 py-4 text-center" @click.stop>
                    <input type="checkbox" :value="invoice.id" v-model="selectedInvoiceIds" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer">
                </td>
                <td class="px-4 py-4 whitespace-nowrap">
                    <div class="text-xs text-gray-500 flex items-center gap-1 mb-1">
                        <Calendar class="w-3 h-3" /> {{ invoice.issue_date }}
                    </div>
                    <div class="font-bold text-gray-900 text-sm">{{ invoice.id }}</div>
                </td>
                <td class="px-4 py-4">
                    <div class="flex items-center gap-2 mb-1">
                        <Building2 class="w-4 h-4 shrink-0 text-blue-500" />
                        <span class="font-bold text-gray-900 text-sm truncate max-w-[120px] md:max-w-none"
                              :title="invoice.document_type === 'received' ? (invoice.vendor_name || invoice.client_name) : invoice.client_name">
                          {{ invoice.document_type === 'received' ? (invoice.vendor_name || invoice.client_name) : invoice.client_name }}
                        </span>
                    </div>
                    <div v-if="invoice.document_type === 'received' && invoice.vendor_name" class="text-[10px] text-gray-400 truncate">宛先: {{ invoice.client_name }}</div>
                    <div v-else class="text-[10px] text-gray-400 truncate" :title="invoice.client_id">{{ invoice.client_id }}</div>
                </td>
                <td class="hidden lg:table-cell px-4 py-4">
                    <div class="font-bold text-gray-900 text-sm mb-1 truncate max-w-[150px]">{{ invoice.invoice_number || invoice.client_name || '請求書' }}</div>
                    <div class="flex items-center gap-2">
                        <span v-if="invoice.project_name" class="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-[10px] font-medium border border-gray-200 truncate max-w-[80px]">
                            {{ invoice.project_name }}
                        </span>
                    </div>
                </td>
                <td class="px-4 py-4 whitespace-nowrap text-right">
                    <div class="font-black text-gray-900">¥{{ formatCurrency(invoice.total_amount) }}</div>
                    <div class="text-[10px] text-gray-500 mt-0.5">期日: {{ invoice.due_date }}</div>
                </td>
                <td class="px-4 py-4 whitespace-nowrap text-center">
                    <span class="inline-flex items-center px-2 py-1 rounded-md text-[10px] font-bold border shrink-0" :class="getStatusBadge(invoice.displayStatus).classes">
                        {{ getStatusBadge(invoice.displayStatus).label }}
                    </span>
                </td>
                <td v-if="activeTab === 'received'" class="hidden md:table-cell px-4 py-4 whitespace-nowrap text-center">
                    <span class="inline-flex items-center px-2 py-1 rounded-md text-[10px] font-bold border" :class="getReviewBadge(invoice.approval_status).classes">
                        {{ getReviewBadge(invoice.approval_status).label }}
                    </span>
                </td>
                <td class="px-4 py-4 whitespace-nowrap text-center sticky right-0 bg-white/90 group-hover:bg-blue-50/90 transition-colors backdrop-blur shadow-[-4px_0_10px_-4px_rgba(0,0,0,0.1)]">
                    <div class="flex items-center justify-center gap-1.5">
                        <button 
                          @click.stop="openPreview(invoice)"
                          class="p-1.5 text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors inline-flex items-center justify-center" 
                          title="詳細"
                        >
                             <FileText class="w-4 h-4" />
                        </button>
                        <button 
                          @click.stop="handleDeleteSingle(invoice.id)"
                          class="p-1.5 text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors inline-flex items-center justify-center" 
                          title="削除"
                        >
                            <Trash2 class="w-4 h-4" />
                        </button>
                    </div>
                </td>
              </tr>
              
              <!-- Accordion Row for Line Items -->
              <tr v-if="expandedInvoiceIds.includes(invoice.id) && invoice.line_items && invoice.line_items.length > 0" class="bg-slate-50 border-t-0">
                  <td :colspan="activeTab === 'received' ? 9 : 8" class="p-0">
                      <div class="px-14 py-4 border-l-4 border-l-blue-400 bg-blue-50/20 shadow-inner">
                          <p class="text-xs font-bold text-gray-500 mb-3 flex items-center">
                              <FileText class="w-4 h-4 mr-1.5" /> 請求明細 ({{ invoice.line_items.length }}件)
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
                                  <tr v-for="(item, idx) in invoice.line_items" :key="idx" class="hover:bg-white transition-colors">
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
              <AlertCircle :class="confirmConfig.isDanger ? 'text-red-600' : 'text-blue-600'" class="w-6 h-6" />
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


    <!-- Detail Modal -->
    <InvoiceDetailModal
        :show="isPreviewModalOpen"
        :invoice="selectedPreviewInvoice"
        :document_type="activeTab === 'received' ? 'received' : 'issued'"
        @close="closePreview"
        @action-completed="handleModalActionCompleted"
        @step-added="handleStepAdded"
    />
    </div>
  </div>
</template>
