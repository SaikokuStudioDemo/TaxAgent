<script setup lang="ts">
import { ref, onMounted } from 'vue';
import {
  History, Loader2, AlertCircle, ChevronDown, ChevronUp,
  Pencil, Trash2, Save, X, FileText,
} from 'lucide-vue-next';
import { api } from '@/lib/api';
import { useTransactions, type Transaction } from '@/composables/useTransactions';
import { formatNumber } from '@/lib/utils/formatters';

interface ImportFile {
  id: string;
  source_type: string;
  account_name: string;
  file_name: string;
  row_count: number;
  status: string;
  imported_at: string;
}

const { updateTransaction, deleteTransaction, error: txError } = useTransactions();

// ─── インポート履歴 ────────────────────────────────────────────
const files = ref<ImportFile[]>([]);
const isLoadingFiles = ref(false);
const filesError = ref<string | null>(null);

const fetchFiles = async () => {
  isLoadingFiles.value = true;
  filesError.value = null;
  try {
    files.value = await api.get<ImportFile[]>('/bank-import-files');
  } catch (e: any) {
    filesError.value = e.message;
  } finally {
    isLoadingFiles.value = false;
  }
};

onMounted(fetchFiles);

// ─── アコーディオン状態 ────────────────────────────────────────
const expandedFileId = ref<string | null>(null);
const fileTransactions = ref<Record<string, Transaction[]>>({});
const isLoadingTx = ref<Record<string, boolean>>({});

const toggleExpand = async (file: ImportFile) => {
  if (expandedFileId.value === file.id) {
    expandedFileId.value = null;
    return;
  }
  expandedFileId.value = file.id;
  if (fileTransactions.value[file.id]) return; // already loaded

  isLoadingTx.value[file.id] = true;
  try {
    const txs = await api.get<Transaction[]>(`/transactions?import_file_id=${file.id}`);
    fileTransactions.value[file.id] = txs;
  } catch (e: any) {
    fileTransactions.value[file.id] = [];
  } finally {
    isLoadingTx.value[file.id] = false;
  }
};

// ─── インライン編集 ────────────────────────────────────────────
interface EditState {
  transaction_date: string;
  description: string;
  amount: string;
}
const editingId = ref<string | null>(null);
const editForm = ref<EditState>({ transaction_date: '', description: '', amount: '' });
const isSaving = ref(false);

const startEdit = (tx: Transaction) => {
  editingId.value = tx.id;
  editForm.value = {
    transaction_date: tx.transaction_date,
    description: tx.description,
    amount: String(tx.amount),
  };
};

const cancelEdit = () => {
  editingId.value = null;
};

const saveEdit = async (fileId: string, tx: Transaction) => {
  isSaving.value = true;
  const updated = await updateTransaction(tx.id, {
    transaction_date: editForm.value.transaction_date,
    description: editForm.value.description,
    amount: Number(editForm.value.amount.replace(/,/g, '')),
  });
  isSaving.value = false;
  if (updated) {
    const list = fileTransactions.value[fileId];
    const idx = list.findIndex(t => t.id === tx.id);
    if (idx !== -1) list[idx] = updated;
    editingId.value = null;
  }
};

// ─── 削除 ─────────────────────────────────────────────────────
const deletingId = ref<string | null>(null);

const handleDeleteTx = async (fileId: string, tx: Transaction) => {
  if (!confirm(`「${tx.description}」を削除しますか？`)) return;
  deletingId.value = tx.id;
  const ok = await deleteTransaction(tx.id);
  deletingId.value = null;
  if (ok) {
    fileTransactions.value[fileId] = fileTransactions.value[fileId].filter(t => t.id !== tx.id);
  }
};

// ─── ファイル削除 ──────────────────────────────────────────────
const deletingFileId = ref<string | null>(null);

const handleDeleteFile = async (file: ImportFile) => {
  if (!confirm(`「${file.file_name}」のインポート履歴を削除しますか？\n関連する明細もすべて削除されます。`)) return;
  deletingFileId.value = file.id;
  try {
    await api.delete(`/bank-import-files/${file.id}`);
    files.value = files.value.filter(f => f.id !== file.id);
    if (expandedFileId.value === file.id) expandedFileId.value = null;
    delete fileTransactions.value[file.id];
  } catch (e: any) {
    filesError.value = e.message;
  } finally {
    deletingFileId.value = null;
  }
};

// ─── ステータス表示 ────────────────────────────────────────────
const statusLabel = (status: string) => {
  switch (status) {
    case 'matched': return { label: '消込済', cls: 'bg-emerald-100 text-emerald-800 border-emerald-200' };
    case 'transferred': return { label: '現金振替', cls: 'bg-blue-100 text-blue-800 border-blue-200' };
    default: return { label: '未消込', cls: 'bg-gray-100 text-gray-500 border-gray-200' };
  }
};

const txTypeLabel = (type: string) => type === 'credit' ? '入金' : '出金';
const txTypeCls = (type: string) => type === 'credit'
  ? 'text-emerald-700 font-bold'
  : 'text-rose-700 font-bold';
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <header class="bg-white border-b border-gray-200 px-8 py-6 -mx-6 -mt-6 mb-6">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 tracking-tight">取込履歴</h1>
          <p class="text-sm text-gray-500 mt-1">過去にインポートした銀行・カード明細の一覧</p>
        </div>
        <div class="flex items-center gap-2 text-sm text-gray-500">
          <History :size="16" />
          <span>{{ files.length }}件</span>
        </div>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="isLoadingFiles" class="flex items-center justify-center py-24">
      <Loader2 :size="32" class="animate-spin text-indigo-500" />
    </div>

    <!-- Error -->
    <div v-else-if="filesError" class="bg-red-50 border border-red-200 rounded-xl p-6 flex items-center gap-3 text-red-700">
      <AlertCircle :size="20" />
      <span>{{ filesError }}</span>
    </div>

    <!-- Empty -->
    <div v-else-if="files.length === 0" class="bg-white rounded-2xl border border-dashed border-gray-200 p-16 flex flex-col items-center justify-center text-gray-400">
      <FileText :size="48" class="text-gray-200 mb-4" />
      <p class="font-medium text-lg text-gray-500">取込履歴がありません</p>
      <p class="text-sm mt-1">「銀行明細取込」からファイルをインポートしてください</p>
    </div>

    <!-- File list -->
    <div v-else class="space-y-3">
      <div
        v-for="file in files"
        :key="file.id"
        class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden"
      >
        <!-- File row -->
        <div
          class="flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-gray-50/60 transition-colors"
          @click="toggleExpand(file)"
        >
          <component
            :is="expandedFileId === file.id ? ChevronUp : ChevronDown"
            :size="18"
            class="text-gray-400 shrink-0"
          />
          <div class="flex-1 min-w-0">
            <p class="font-semibold text-gray-900 truncate">{{ file.file_name }}</p>
            <p class="text-xs text-gray-500 mt-0.5">
              {{ file.account_name }} ·
              {{ file.source_type === 'bank' ? '銀行' : 'カード' }} ·
              {{ file.row_count }}件 ·
              {{ file.imported_at?.slice(0, 10) }}
            </p>
          </div>
          <button
            @click.stop="handleDeleteFile(file)"
            :disabled="deletingFileId === file.id"
            class="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
            title="このインポートを削除"
          >
            <Loader2 v-if="deletingFileId === file.id" :size="15" class="animate-spin" />
            <Trash2 v-else :size="15" />
          </button>
        </div>

        <!-- Accordion: transactions -->
        <div v-if="expandedFileId === file.id" class="border-t border-gray-100">
          <!-- Loading transactions -->
          <div v-if="isLoadingTx[file.id]" class="flex items-center justify-center py-8">
            <Loader2 :size="24" class="animate-spin text-indigo-400" />
          </div>

          <!-- No transactions -->
          <div v-else-if="!fileTransactions[file.id]?.length" class="py-8 text-center text-sm text-gray-400">
            明細データが見つかりません
          </div>

          <!-- Transaction table -->
          <div v-else class="overflow-x-auto">
            <table class="w-full text-left">
              <thead class="bg-gray-50/80">
                <tr class="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  <th class="px-4 py-2.5 w-32">日付</th>
                  <th class="px-4 py-2.5 min-w-[200px]">摘要</th>
                  <th class="px-4 py-2.5 w-32 text-right">金額</th>
                  <th class="px-4 py-2.5 w-20 text-center">種別</th>
                  <th class="px-4 py-2.5 w-24 text-center">消込状態</th>
                  <th class="px-4 py-2.5 w-24 text-center">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50 text-sm">
                <tr
                  v-for="tx in fileTransactions[file.id]"
                  :key="tx.id"
                  :class="['transition-colors', editingId === tx.id ? 'bg-indigo-50/40' : 'hover:bg-gray-50/40']"
                >
                  <!-- 編集モード -->
                  <template v-if="editingId === tx.id">
                    <td class="px-4 py-2">
                      <input
                        type="date"
                        v-model="editForm.transaction_date"
                        class="border border-indigo-300 rounded-lg px-2 py-1 text-xs font-mono w-full focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </td>
                    <td class="px-4 py-2">
                      <input
                        type="text"
                        v-model="editForm.description"
                        class="border border-indigo-300 rounded-lg px-2 py-1 text-xs w-full focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </td>
                    <td class="px-4 py-2">
                      <input
                        type="text"
                        v-model="editForm.amount"
                        class="border border-indigo-300 rounded-lg px-2 py-1 text-xs text-right w-full focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </td>
                    <td class="px-4 py-2 text-center">
                      <span :class="txTypeCls(tx.transaction_type)">{{ txTypeLabel(tx.transaction_type) }}</span>
                    </td>
                    <td class="px-4 py-2 text-center">
                      <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border', statusLabel(tx.status).cls]">
                        {{ statusLabel(tx.status).label }}
                      </span>
                    </td>
                    <td class="px-4 py-2">
                      <div class="flex items-center justify-center gap-1">
                        <button
                          @click="saveEdit(file.id, tx)"
                          :disabled="isSaving"
                          class="p-1.5 text-indigo-500 hover:text-indigo-700 hover:bg-indigo-100 rounded-lg transition-colors disabled:opacity-40"
                          title="保存"
                        >
                          <Loader2 v-if="isSaving" :size="14" class="animate-spin" />
                          <Save v-else :size="14" />
                        </button>
                        <button
                          @click="cancelEdit"
                          class="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                          title="キャンセル"
                        >
                          <X :size="14" />
                        </button>
                      </div>
                    </td>
                  </template>

                  <!-- 表示モード -->
                  <template v-else>
                    <td class="px-4 py-2.5 font-mono text-gray-700 whitespace-nowrap">{{ tx.transaction_date }}</td>
                    <td class="px-4 py-2.5 text-gray-800 max-w-[260px] truncate">{{ tx.description }}</td>
                    <td class="px-4 py-2.5 text-right whitespace-nowrap" :class="txTypeCls(tx.transaction_type)">
                      ¥{{ formatNumber(tx.amount) }}
                    </td>
                    <td class="px-4 py-2.5 text-center text-xs" :class="txTypeCls(tx.transaction_type)">
                      {{ txTypeLabel(tx.transaction_type) }}
                    </td>
                    <td class="px-4 py-2.5 text-center">
                      <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border', statusLabel(tx.status).cls]">
                        {{ statusLabel(tx.status).label }}
                      </span>
                    </td>
                    <td class="px-4 py-2.5">
                      <div v-if="tx.status === 'unmatched'" class="flex items-center justify-center gap-1">
                        <button
                          @click="startEdit(tx)"
                          class="p-1.5 text-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                          title="編集"
                        >
                          <Pencil :size="14" />
                        </button>
                        <button
                          @click="handleDeleteTx(file.id, tx)"
                          :disabled="deletingId === tx.id"
                          class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
                          title="削除"
                        >
                          <Loader2 v-if="deletingId === tx.id" :size="14" class="animate-spin" />
                          <Trash2 v-else :size="14" />
                        </button>
                      </div>
                      <span v-else class="text-xs text-gray-300 block text-center">—</span>
                    </td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- tx error toast -->
    <div v-if="txError" class="fixed bottom-6 right-6 bg-red-600 text-white text-sm px-5 py-3 rounded-xl shadow-lg">
      {{ txError }}
    </div>
  </div>
</template>
