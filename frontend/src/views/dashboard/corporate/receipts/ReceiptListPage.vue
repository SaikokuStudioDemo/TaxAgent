<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  List, Pencil, Trash2, Loader2, AlertCircle, Image, CheckCircle2, Clock, XCircle, FileText,
  ChevronUp, ChevronDown, ChevronsUpDown, X,
} from 'lucide-vue-next';
import { useReceipts, type Receipt } from '@/composables/useReceipts';
import { useAuth } from '@/composables/useAuth';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

const router = useRouter();
const { receipts, isLoading, error, fetchReceipts, deleteReceipt } = useReceipts();
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
    fetchReceipts(isAccountingRole.value ? {} : { submitted_by: 'me' });
  },
  { immediate: true },
);

// ─── フィルター状態 ──────────────────────────────────────────────
const filterPayee      = ref('');
const filterAmountMin  = ref<number | ''>('');
const filterAmountMax  = ref<number | ''>('');
const filterSubmitter  = ref('');
const filterCategory   = ref('');
const filterPayment    = ref('');
const filterStatus     = ref('');

const hasActiveFilter = computed(() =>
  !!(filterPayee.value || filterAmountMin.value !== '' || filterAmountMax.value !== '' ||
     filterSubmitter.value || filterCategory.value || filterPayment.value || filterStatus.value)
);

const clearFilters = () => {
  filterPayee.value = '';
  filterAmountMin.value = '';
  filterAmountMax.value = '';
  filterSubmitter.value = '';
  filterCategory.value = '';
  filterPayment.value = '';
  filterStatus.value = '';
};

// ─── フィルター選択肢（実データから生成） ───────────────────────
const uniqueCategories = computed(() =>
  [...new Set(receipts.value.map(r => r.category).filter(Boolean))].sort()
);
const uniquePaymentMethods = computed(() =>
  [...new Set(receipts.value.map(r => r.payment_method).filter(Boolean))].sort()
);
const uniqueSubmitters = computed(() =>
  [...new Set(receipts.value.map(r => r.submitter_name || r.submitted_by).filter(Boolean))].sort()
);

// ─── ソート状態 ─────────────────────────────────────────────────
type SortKey = 'date' | 'payee' | 'amount' | 'category' | 'payment_method' | 'submitter_name' | 'approval_status';
const sortKey = ref<SortKey>('date');
const sortDir = ref<'asc' | 'desc'>('desc');

const toggleSort = (key: SortKey) => {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey.value = key;
    sortDir.value = key === 'amount' ? 'desc' : 'asc';
  }
};

const sortIcon = (key: SortKey) => {
  if (sortKey.value !== key) return ChevronsUpDown;
  return sortDir.value === 'asc' ? ChevronUp : ChevronDown;
};

// ─── フィルター + ソート適用 ────────────────────────────────────
const filteredReceipts = computed(() => {
  let list = receipts.value;

  if (filterPayee.value)
    list = list.filter(r => (r.payee || '').includes(filterPayee.value));
  if (filterAmountMin.value !== '')
    list = list.filter(r => r.amount >= Number(filterAmountMin.value));
  if (filterAmountMax.value !== '')
    list = list.filter(r => r.amount <= Number(filterAmountMax.value));
  if (filterSubmitter.value)
    list = list.filter(r => (r.submitter_name || r.submitted_by || '').includes(filterSubmitter.value));
  if (filterCategory.value)
    list = list.filter(r => r.category === filterCategory.value);
  if (filterPayment.value)
    list = list.filter(r => r.payment_method === filterPayment.value);
  if (filterStatus.value)
    list = list.filter(r => r.approval_status === filterStatus.value);

  return [...list].sort((a, b) => {
    let va: any, vb: any;
    switch (sortKey.value) {
      case 'date':            va = a.date; vb = b.date; break;
      case 'payee':           va = a.payee || ''; vb = b.payee || ''; break;
      case 'amount':          va = a.amount; vb = b.amount; break;
      case 'category':        va = a.category || ''; vb = b.category || ''; break;
      case 'payment_method':  va = a.payment_method || ''; vb = b.payment_method || ''; break;
      case 'submitter_name':  va = a.submitter_name || ''; vb = b.submitter_name || ''; break;
      case 'approval_status': va = a.approval_status; vb = b.approval_status; break;
    }
    if (va < vb) return sortDir.value === 'asc' ? -1 : 1;
    if (va > vb) return sortDir.value === 'asc' ? 1 : -1;
    return 0;
  });
});

// ─── 削除 ───────────────────────────────────────────────────────
const deletingId = ref<string | null>(null);
const handleDelete = async (receipt: Receipt) => {
  if (!confirm(`「${receipt.payee}」の領収書を削除しますか？`)) return;
  deletingId.value = receipt.id;
  await deleteReceipt(receipt.id);
  deletingId.value = null;
};

const handleEdit = (receipt: Receipt) => {
  router.push('/dashboard/corporate/receipts/edit/' + receipt.id);
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
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">領収書一覧</h1>
          <p class="text-sm text-gray-500 mt-1">
            {{ isAccountingRole ? '全社の登録済み領収書' : '自分が提出した領収書' }}
          </p>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-sm text-gray-500 flex items-center gap-1.5">
            <List :size="16" />
            {{ filteredReceipts.length }}<span class="text-gray-400">/ {{ receipts.length }}件</span>
          </span>
        </div>
      </div>
    </header>

    <!-- Filter Panel -->
    <div class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <!-- 支払先 -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">支払先</label>
          <input
            v-model="filterPayee"
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

        <!-- カテゴリ -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">カテゴリ</label>
          <select
            v-model="filterCategory"
            class="w-full px-2.5 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none bg-white"
          >
            <option value="">すべて</option>
            <option v-for="c in uniqueCategories" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>

        <!-- 支払方法 -->
        <div>
          <label class="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">支払方法</label>
          <select
            v-model="filterPayment"
            class="w-full px-2.5 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-400 focus:border-indigo-400 outline-none bg-white"
          >
            <option value="">すべて</option>
            <option v-for="m in uniquePaymentMethods" :key="m" :value="m">{{ m }}</option>
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
    <div v-else-if="receipts.length === 0" class="bg-white rounded-2xl border border-dashed border-gray-200 p-16 flex flex-col items-center justify-center text-gray-400">
      <FileText :size="48" class="text-gray-200 mb-4" />
      <p class="font-medium text-lg text-gray-500">領収書が登録されていません</p>
      <p class="text-sm mt-1">「領収書提出」から画像をアップロードしてください</p>
    </div>

    <!-- Empty (filtered) -->
    <div v-else-if="filteredReceipts.length === 0" class="bg-white rounded-2xl border border-dashed border-gray-200 p-12 flex flex-col items-center justify-center text-gray-400">
      <FileText :size="36" class="text-gray-200 mb-3" />
      <p class="font-medium text-gray-500">条件に一致する領収書がありません</p>
      <button @click="clearFilters" class="mt-2 text-sm text-indigo-500 hover:underline">フィルターをクリア</button>
    </div>

    <!-- Table -->
    <div v-else class="bg-white shadow-sm rounded-xl border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead class="bg-gray-50/80">
            <tr class="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              <th class="px-4 py-3.5 w-10"></th>

              <th class="px-4 py-3.5 w-28 cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('date')">
                <div class="flex items-center gap-1">
                  日付 <component :is="sortIcon('date')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 min-w-[160px] cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('payee')">
                <div class="flex items-center gap-1">
                  支払先 <component :is="sortIcon('payee')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-32 text-right cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('amount')">
                <div class="flex items-center justify-end gap-1">
                  金額 <component :is="sortIcon('amount')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-28 cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('category')">
                <div class="flex items-center gap-1">
                  カテゴリ <component :is="sortIcon('category')" :size="12" />
                </div>
              </th>

              <th class="px-4 py-3.5 w-28 cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('payment_method')">
                <div class="flex items-center gap-1">
                  支払方法 <component :is="sortIcon('payment_method')" :size="12" />
                </div>
              </th>

              <th v-if="isAccountingRole" class="px-4 py-3.5 w-28 cursor-pointer hover:text-gray-700 select-none" @click="toggleSort('submitter_name')">
                <div class="flex items-center gap-1">
                  申請者 <component :is="sortIcon('submitter_name')" :size="12" />
                </div>
              </th>

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
              v-for="receipt in filteredReceipts"
              :key="receipt.id"
              class="hover:bg-gray-50/50 transition-colors group"
            >
              <!-- サムネイル -->
              <td class="px-4 py-3">
                <div class="w-9 h-9 rounded-lg overflow-hidden bg-gray-100 flex items-center justify-center shrink-0">
                  <img
                    v-if="receipt.attachments?.[0]"
                    :src="receipt.attachments[0]"
                    alt="領収書"
                    class="w-full h-full object-cover"
                  />
                  <Image v-else :size="16" class="text-gray-300" />
                </div>
              </td>

              <!-- 日付 -->
              <td class="px-4 py-3 font-mono text-gray-700 whitespace-nowrap">{{ receipt.date }}</td>

              <!-- 支払先 -->
              <td class="px-4 py-3">
                <p class="font-medium text-gray-900 truncate max-w-[200px]">{{ receipt.payee || '—' }}</p>
              </td>

              <!-- 金額 -->
              <td class="px-4 py-3 text-right font-bold text-gray-900 whitespace-nowrap">
                ¥{{ formatAmount(receipt.amount) }}
              </td>

              <!-- カテゴリ -->
              <td class="px-4 py-3">
                <span class="inline-block bg-orange-50 text-orange-700 border border-orange-100 px-2 py-0.5 rounded text-[11px] font-medium">
                  {{ receipt.category || '—' }}
                </span>
              </td>

              <!-- 支払方法 -->
              <td class="px-4 py-3">
                <span class="inline-block bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-[11px]">
                  {{ receipt.payment_method }}
                </span>
              </td>

              <!-- 申請者 -->
              <td v-if="isAccountingRole" class="px-4 py-3 text-gray-600 whitespace-nowrap">
                {{ receipt.submitter_name || '—' }}
              </td>

              <!-- ステータスバッジ -->
              <td class="px-4 py-3 text-center">
                <span
                  :class="['inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-semibold border', statusBadge(receipt.approval_status).class]"
                >
                  <component :is="statusIcon(receipt.approval_status)" :size="10" />
                  {{ statusBadge(receipt.approval_status).label }}
                </span>
              </td>

              <!-- 操作ボタン -->
              <td class="px-4 py-3 text-center">
                <div v-if="isEditable(receipt.approval_status)" class="flex items-center justify-center gap-1">
                  <button
                    @click="handleEdit(receipt)"
                    class="p-1.5 text-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                    title="編集"
                  >
                    <Pencil :size="15" />
                  </button>
                  <button
                    @click="handleDelete(receipt)"
                    :disabled="deletingId === receipt.id"
                    class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
                    title="削除"
                  >
                    <Loader2 v-if="deletingId === receipt.id" :size="15" class="animate-spin" />
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
