<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { 
    CheckCircle, 
    Clock, 
    Plus, 
    FileText, 
    Search, 
    Filter, 
    ChevronDown,
    Building2,
    UserCircle2,
    Upload,
    ChevronUp,
    Send,
    Calendar
} from 'lucide-vue-next';
import { useRouter } from 'vue-router';
import { useInvoices } from '@/composables/useInvoices';

const router = useRouter();

// Tabs: 'issued' (発行), 'received' (受領), 'drafts' (下書き)
const activeTab = ref<'issued' | 'received' | 'drafts'>('issued');
const searchQuery = ref('');

const { invoices, fetchInvoices } = useInvoices();
const expandedInvoiceIds = ref<string[]>([]);

// Fetch invoices when tab changes
const loadInvoices = async () => {
    if (activeTab.value === 'issued') {
        await fetchInvoices({ direction: 'issued' });
    } else if (activeTab.value === 'received') {
        await fetchInvoices({ direction: 'received' });
    } else {
        // drafts: issued + status draft
        await fetchInvoices({ direction: 'issued' });
    }
};

onMounted(loadInvoices);
watch(activeTab, loadInvoices);

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
        // camelCase aliases for template compatibility
        displayStatus: mapStatus(inv),
        clientName: inv.client_name,
        clientId: inv.client_id,
        totalAmount: inv.total_amount,
        issueDate: inv.issue_date,
        dueDate: inv.due_date,
        reviewStatus: inv.review_status,
        lineItems: inv.line_items,
        createdBy: inv.created_by,
        // Fields not in API model — default to sensible values
        clientType: 'corporate' as string,
        title: `${inv.invoice_number ?? ''} ${inv.client_name ?? ''}`.trim(),
        type: 'single' as string,
        recurringDetails: undefined as string | undefined,
        projectName: undefined as string | undefined,
        amount: inv.total_amount,
    }));

    if (activeTab.value === 'drafts') {
        list = list.filter(i => i.status === 'draft');
    }

    if (searchQuery.value) {
        const q = searchQuery.value.toLowerCase();
        list = list.filter(i =>
            i.client_name?.toLowerCase().includes(q) ||
            i.invoice_number?.toLowerCase().includes(q)
        );
    }

    return list;
});

const toggleExpansion = (id: string) => {
    const idx = expandedInvoiceIds.value.indexOf(id);
    if (idx > -1) {
        expandedInvoiceIds.value.splice(idx, 1);
    } else {
        expandedInvoiceIds.value.push(id);
    }
};

const formatCurrency = (amount: number) => new Intl.NumberFormat('ja-JP').format(amount || 0);

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

      <!-- Search & Filters -->
      <div class="mt-8 flex flex-col md:flex-row gap-4 items-center justify-between">
        <!-- Tabs -->
        <div class="flex bg-gray-100/80 p-1 rounded-xl w-full md:w-auto overflow-x-auto shrink-0 border border-gray-200/50">
          <button 
            @click="activeTab = 'issued'" 
            class="flex-1 md:flex-none px-6 py-2.5 rounded-lg text-sm font-bold transition-all relative flex items-center justify-center gap-2"
            :class="activeTab === 'issued' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50'"
          >
            <Send class="w-4 h-4" :class="activeTab === 'issued' ? 'text-blue-600' : 'text-gray-400'" />
            発行
          </button>
          <button 
            @click="activeTab = 'received'" 
            class="flex-1 md:flex-none px-6 py-2.5 rounded-lg text-sm font-bold transition-all relative flex items-center justify-center gap-2"
            :class="activeTab === 'received' ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50'"
          >
            <Upload class="w-4 h-4" :class="activeTab === 'received' ? 'text-indigo-600' : 'text-gray-400'" />
            受領
          </button>
          <button 
            @click="activeTab = 'drafts'" 
            class="flex-1 md:flex-none px-6 py-2.5 rounded-lg text-sm font-bold transition-all relative flex items-center justify-center gap-2"
            :class="activeTab === 'drafts' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-200/50'"
          >
            <Clock class="w-4 h-4" :class="activeTab === 'drafts' ? 'text-blue-600' : 'text-gray-400'" />
            下書き
          </button>
        </div>

        <div class="flex items-center gap-3 w-full md:w-auto">
          <div class="relative flex-1 md:w-80">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input v-model="searchQuery" type="text" placeholder="取引先名、タイトル、請求書番号で検索..." class="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white shadow-sm" />
          </div>
          <button class="bg-white border border-gray-300 text-gray-700 p-2.5 rounded-lg hover:bg-gray-50 transition-colors shadow-sm shrink-0">
            <Filter class="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 overflow-x-hidden overflow-y-auto bg-slate-50 p-8">
      
      <!-- Summary Cards (Only show on Issued tab) -->
      <div v-if="activeTab === 'issued'" class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">今月の売上予定</p>
                <div class="bg-blue-50 p-2 rounded-lg"><Calendar class="w-4 h-4 text-blue-600" /></div>
            </div>
            <p class="text-2xl font-bold text-gray-900">¥1,143,000</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">消込済 (入金済)</p>
                <div class="bg-emerald-50 p-2 rounded-lg"><CheckCircle class="w-4 h-4 text-emerald-600" /></div>
            </div>
            <p class="text-2xl font-bold text-emerald-600">¥165,000</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">未消込 (作成・送付済)</p>
                <div class="bg-amber-50 p-2 rounded-lg"><Clock class="w-4 h-4 text-amber-600" /></div>
            </div>
            <p class="text-2xl font-bold text-amber-600">¥880,000</p>
        </div>
        <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200 border-l-4 border-l-red-500">
            <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-medium text-gray-500">未消込 (期限超過)</p>
                <div class="bg-red-50 p-2 rounded-lg"><Clock class="w-4 h-4 text-red-600" /></div>
            </div>
            <p class="text-2xl font-bold text-red-600">¥98,000 <span class="text-xs font-normal text-gray-500 ml-1">(1件)</span></p>
        </div>
      </div>

      <!-- Data Table -->
      <div class="bg-white shadow-sm rounded-xl border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 table-fixed">
            <thead class="bg-gray-50/80">
              <tr>
                <th scope="col" class="w-12 px-6 py-4 text-center">
                    <input type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                </th>
                <th scope="col" class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider w-40">請求書番号 / 発行日</th>
                <th scope="col" class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider w-64">取引先</th>
                <th scope="col" class="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">件名 / プロジェクト</th>
                <th scope="col" class="px-6 py-4 text-right text-xs font-bold text-gray-500 uppercase tracking-wider w-36">金額 (税込)</th>
                <th scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-40">全体ステータス</th>
                <th v-if="activeTab === 'received'" scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-36">承認状況</th>
                <th scope="col" class="px-6 py-4 text-center text-xs font-bold text-gray-500 uppercase tracking-wider w-16"></th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <template v-for="invoice in filteredInvoices" :key="invoice.id">
              <tr 
                class="hover:bg-blue-50/30 transition-colors group cursor-pointer"
                @click="toggleExpansion(invoice.id)"
              >
                <td class="px-6 py-4 whitespace-nowrap text-center">
                    <input type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500">
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
                        v-if="invoice.lineItems && invoice.lineItems.length > 0"
                        @click.stop="toggleExpansion(invoice.id)"
                        class="text-gray-400 hover:text-blue-600 p-2 rounded-lg hover:bg-white transition-colors"
                    >
                        <ChevronUp v-if="expandedInvoiceIds.includes(invoice.id)" class="w-5 h-5" />
                        <ChevronDown v-else class="w-5 h-5" />
                    </button>
                </td>
              </tr>
              
              <!-- Accordion Row for Line Items -->
              <tr v-if="expandedInvoiceIds.includes(invoice.id) && invoice.lineItems && invoice.lineItems.length > 0" class="bg-slate-50 border-t-0">
                  <td colspan="7" class="p-0">
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
  </div>
</template>
