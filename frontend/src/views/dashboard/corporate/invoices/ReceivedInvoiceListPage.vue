<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  List, Pencil, Trash2, Loader2, AlertCircle, Image, CheckCircle2, Clock, XCircle, FileText,
  ChevronUp, ChevronDown, ChevronsUpDown, X,
} from 'lucide-vue-next';
import { useInvoices, type Invoice } from '@/composables/useInvoices';
import { useAuth } from '@/composables/useAuth';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

const router = useRouter();
const { invoices, isLoading, error, fetchInvoices, deleteInvoice } = useInvoices();
const { userProfile } = useAuth();

// ─── 権限判定 ────────────────────────────────────────────────────
const isAccountingRole = computed(() => {
  if (userProfile.value?.type === 'corporate') return true;
  const role = userProfile.value?.data?.role ?? 'staff';
  return ['admin', 'manager', 'accounting'].includes(role);
});

// ─── データ取得 ─────────────────────────────────────────────────
let fetched = false;
watch(
  () => userProfile.value,
  (profile) => {
    if (!profile || fetched) return;
    fetched = true;
    if (isAccountingRole.value) {
      fetchInvoices({ document_type: 'received' });
    } else {
      fetchInvoices({ document_type: 'received', submitted_by: 'me' });
    }
  },
  { immediate: true },
);

// ─── フィルター状態 ──────────────────────────────────────────────
const filterVendor     = ref('');
const filterAmountMin  = ref<number | ''>('');
const filterAmountMax  = ref<number | ''>('');
const filterDueDateMin = ref('');
const filterDueDateMax = ref('');
const filterSubmitter  = ref('');
const filterStatus     = ref('');

const hasActiveFilter = computed(() =>
  !!(filterVendor.value || filterAmountMin.value !== '' || filterAmountMax.value !== '' ||
     filterDueDateMin.value || filterDueDateMax.value ||
     filterSubmitter.value || filterStatus.value)
);

const clearFilters = () => {
  filterVendor.value = '';
  filterAmountMin.value = '';
  filterAmountMax.value = '';
  filterDueDateMin.value = '';
  filterDueDateMax.value = '';
  filterSubmitter.value = '';
  filterStatus.value = '';
};

// ─── フィルター選択肢（実データから生成） ───────────────────────
const uniqueSubmitters = computed(() =>
  [...new Set(invoices.value.map(i => i.submitter_name).filter(Boolean))].sort()
);

// ─── ソート状態 ─────────────────────────────────────────────────
type SortKey = 'issue_date' | 'due_date' | 'vendor' | 'total_amount' | 'approval_status';
const sortKey = ref<SortKey>('issue_date');
const sortDir = ref<'asc' | 'desc'>('desc');

const toggleSort = (key: SortKey) => {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = key === 'total_amount' ? 'desc' : 'asc';
  }
};

const sortIcon = (key: SortKey) => {
  if (sortKey.value !== key) return ChevronsUpDown;
  return sortDir.value === 'asc' ? ChevronUp : ChevronDown;
};

// ─── フィルター + ソート適用 ────────────────────────────────────
const filteredInvoices = computed(() => {
  let list = invoices.value;

  if (filterVendor.value)
    list = list.filter(i => (i.vendor_name || i.client_name || '').includes(filterVendor.value));
  if (filterAmountMin.value !== '')
    list = list.filter(i => i.total_amount >= Number(filterAmountMin.value));
  if (filterAmountMax.value !== '')
    list = list.filter(i => i.total_amount <= Number(filterAmountMax.value));
  if (filterDueDateMin.value)
    list = list.filter(i => (i.due_date || '') >= filterDueDateMin.value);
  if (filterDueDateMax.value)
    list = list.filter(i => (i.due_date || '') <= filterDueDateMax.value);
  if (filterSubmitter.value)
    list = list.filter(i => (i.submitter_name || '').includes(filterSubmitter.value));
  if (filterStatus.value)
    list = list.filter(i => i.approval_status === filterStatus.value);

  return [...list].sort((a, b) => {
    let va: any, vb: any;
    switch (sortKey.value) {
      case 'issue_date':      va = a.issue_date || ''; vb = b.issue_date || ''; break;
      case 'due_date':        va = a.due_date || '';   vb = b.due_date || '';   break;
      case 'vendor':          va = a.vendor_name || a.client_name || ''; vb = b.vendor_name || b.client_name || ''; break;
      case 'total_amount':    va = a.total_amount;     vb = b.total_amount;     break;
      case 'approval_status': va = a.approval_status;  vb = b.approval_status;  break;
    }
    if (va < vb) return sortDir.value === 'asc' ? -1 : 1;
    if (va > vb) return sortDir.value === 'asc' ? 1 : -1;
    return 0;
  });
});

// ─── 削除 ───────────────────────────────────────────────────────
const deletingId = ref<string | null>(null);

const handleDelete = async (invoice: Invoice) => {
  if (!confirm(`「${invoice.client_name}」の受取請求書を削除しますか？`)) return;
  deletingId.value = invoice.id;
  await deleteInvoice(invoice.id);
  deletingId.value = null;
};

const handleEdit = (invoice: Invoice) => {
  router.push('/dashboard/corporate/invoices/received-edit/' + invoice.id);
};

// ─── ステータス表示 ──────────────────────────────────────────────
const isEditable = (status: string) =>
  ['pending_approval', 'draft', 'rejected'].includes(status);

const statusBadge = (status: string): { label: string; class: string } => {
  switch (status) {
    case 'approved':
    case 'auto_approved': return { label: '承認済み', class: 'bg-emerald-100 text-emerald-800 border-emerald-200' };
    case 'rejected':      return { label: '差戻し',   class: 'bg-rose-100 text-rose-800 border-rose-200' };
    case 'pending_approval': return { label: '承認待ち', class: 'bg-blue-100 text-blue-800 border-blue-200' };
    case 'draft':         return { label: '下書き',   class: 'bg-gray-100 text-gray-600 border-gray-200' };
    default:              return { label: status,    class: 'bg-gray-100 text-gray-600 border-gray-200' };
  }
};

const statusIcon = (status: string) => {
  switch (status) {
    case 'approved':
    case 'auto_approved': return CheckCircle2;
    case 'rejected':      return XCircle;
    default:              return Clock;
  }
};
</script>

<template>
  <div class="space-y-4">
    <!-- Header -->
    <header class="bg-white border-b border-gray-200 px-8 py-6 -mx-6 -mt-6 mb-2">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">受取請求書一覧</h1>
          <p class="text-sm text-gray-500 mt-1">
            {{ isAccountingRole ? '全社の登録済み受取請求書' : '自分が登録した受取請求書' }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-sm text-gray-500 flex items-center gap-1.5">
            <List :size="16" />
            {{ filteredInvoices.length }}<span class="text-gray-400">/ {{ invoices.length }}件</span>
          </span>
        </div>
      </div>
    </header>

    <!-- Filter Panel -->
    <div class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <!-- 発行元 -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">発行元</label>
          <input
            v-model="filterVendor"
            type="text"
            placeholder="部分一致"
            class="w-full px-2.5 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none"
          />
        </div>

        <!-- 金額 -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">金額</label>
          <div class="flex items-center gap-1">
            <input
              v-model.number="filterAmountMin"
              type="number"
              placeholder="下限"
              class="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none"
            />
            <span class="text-gray-400 text-xs shrink-0">〜</span>
            <input
              v-model.number="filterAmountMax"
              type="number"
              placeholder="上限"
              class="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none"
            />
          </div>
        </div>

        <!-- 支払期日 -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">支払期日</label>
          <div class="flex items-center gap-1">
            <input
              v-model="filterDueDateMin"
              type="date"
              class="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none"
            />
            <span class="text-gray-400 text-xs shrink-0">〜</span>
            <input
              v-model="filterDueDateMax"
              type="date"
              class="w-full px-2 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none"
            />
          </div>
        </div>

        <!-- ステータス -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">ステータス</label>
          <select
            v-model="filterStatus"
            class="w-full px-2.5 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none bg-white"
          >
            <option value="">すべて</option>
            <option value="draft">下書き</option>
            <option value="pending_approval">承認待ち</option>
            <option value="approved">承認済み</option>
            <option value="rejected">差戻し</option>
          </select>
        </div>

        <!-- 申請者（経理ロールのみ） -->
        <div v-if="isAccountingRole">
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">申請者</label>
          <select
            v-model="filterSubmitter"
            class="w-full px-2.5 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none bg-white"
          >
            <option value="">すべて</option>
            <option v-for="s in uniqueSubmitters" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
      </div>

      <!-- クリアボタン -->
      <div class="mt-3 flex justify-end">
        <button
          v-if="hasActiveFilter"
          @click="clearFilters"
          class="flex items-center gap-1 text-xs text-gray-500 hover:text-red-500 transition-colors"
        >
          <X :size="12" /> フィルターをクリア
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-24">
      <Loader2 :size="32" class="animate-spin text-indigo-500" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-xl p-6 flex items-center gap-3 text-red-700">
      <AlertCircle :size="20" />
      <span>{{ error }}</span>
    </div>

    <!-- Empty (no data) -->
    <div v-else-if="invoices.length === 0" class="bg-white rounded-2xl border border-dashed border-gray-200 p-16 flex flex-col items-center justify-center text-gray-400">
      <FileText :size="48" class="text-gray-200 mb-4" />
      <p class="font-medium text-lg text-gray-500">受取請求書が登録されていません</p>
      <p class="text-sm mt-1">「受領請求書アップロード」からファイルを登録してください</p>
    </div>

    <!-- Empty (filtered) -->
    <div v-else-if="filteredInvoices.length === 0" class="bg-white rounded-2xl border border-dashed border-gray-200 p-12 flex flex-col items-center justify-center text-gray-400">
      <FileText :size="36" class="text-gray-200 mb-3" />
      <p class="font-medium text-gray-500">条件に一致する受取請求書がありません</p>
      <button @click="clearFilters" class="mt-2 text-sm text-indigo-500 hover:underline">フィルターをクリア</button>
    </div>

    <!-- Table -->
    <div v-else class="bg-white shadow-sm rounded-xl border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead class="bg-gray-50/80">
            <tr class="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              <th class="px-4 py-3.5 w-10"></th>

              <th class="px-4 py-3.5 w-28 cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('issue_date')">
                <div class="flex items-center gap-1">
                  発行日 <component :is="sortIcon('issue_date')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-28 cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('due_date')">
                <div class="flex items-center gap-1">
                  支払期日 <component :is="sortIcon('due_date')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 min-w-[160px] cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('vendor')">
                <div class="flex items-center gap-1">
                  発行元 <component :is="sortIcon('vendor')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-32 text-right cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('total_amount')">
                <div class="flex items-center justify-end gap-1">
                  請求金額 <component :is="sortIcon('total_amount')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-28">カテゴリ</th>

              <th v-if="isAccountingRole" class="px-4 py-3.5 w-28">申請者</th>

              <th class="px-4 py-3.5 w-32 text-center cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('approval_status')">
                <div class="flex items-center justify-center gap-1">
                  ステータス <component :is="sortIcon('approval_status')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-28 text-center">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 text-sm">
            <tr
              v-for="invoice in filteredInvoices"
              :key="invoice.id"
              class="hover:bg-gray-50/50 transition-colors group"
            >
              <!-- サムネイル -->
              <td class="px-4 py-3">
                <div class="w-9 h-9 rounded-lg overflow-hidden bg-gray-100 flex items-center justify-center shrink-0">
                  <img
                    v-if="invoice.attachments?.[0]"
                    :src="invoice.attachments[0]"
                    alt="請求書"
                    class="w-full h-full object-cover"
                  />
                  <Image v-else :size="16" class="text-gray-300" />
                </div>
              </td>

              <!-- 発行日 -->
              <td class="px-4 py-3 font-mono text-gray-700 whitespace-nowrap">{{ invoice.issue_date }}</td>

              <!-- 支払期日 -->
              <td class="px-4 py-3 font-mono text-gray-600 whitespace-nowrap">{{ invoice.due_date }}</td>

              <!-- 発行元 -->
              <td class="px-4 py-3">
                <p class="font-medium text-gray-900 truncate max-w-[200px]">
                  {{ invoice.vendor_name || invoice.client_name || '—' }}
                </p>
              </td>

              <!-- 請求金額 -->
              <td class="px-4 py-3 text-right font-bold text-gray-900 whitespace-nowrap">
                ¥{{ formatAmount(invoice.total_amount) }}
              </td>

              <!-- カテゴリ -->
              <td class="px-4 py-3">
                <span class="inline-block bg-orange-50 text-orange-700 border border-orange-100 px-2 py-0.5 rounded text-[11px] font-medium">
                  {{ invoice.line_items?.[0]?.category || '—' }}
                </span>
              </td>

              <!-- 申請者（経理ロール以上のみ） -->
              <td v-if="isAccountingRole" class="px-4 py-3 text-gray-600 whitespace-nowrap">
                {{ invoice.submitter_name || '—' }}
              </td>

              <!-- ステータスバッジ -->
              <td class="px-4 py-3 text-center">
                <span
                  :class="['inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold border', statusBadge(invoice.approval_status).class]"
                >
                  <component :is="statusIcon(invoice.approval_status)" :size="10" />
                  {{ statusBadge(invoice.approval_status).label }}
                </span>
              </td>

              <!-- 操作ボタン -->
              <td class="px-4 py-3 text-center">
                <div v-if="isEditable(invoice.approval_status)" class="flex items-center justify-center gap-1">
                  <button
                    @click="handleEdit(invoice)"
                    class="p-1.5 text-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                    title="編集"
                  >
                    <Pencil :size="15" />
                  </button>
                  <button
                    @click="handleDelete(invoice)"
                    :disabled="deletingId === invoice.id"
                    class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
                    title="削除"
                  >
                    <Loader2 v-if="deletingId === invoice.id" :size="15" class="animate-spin" />
                    <Trash2 v-else :size="15" />
                  </button>
                </div>
                <span v-else class="text-xs text-gray-300">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
