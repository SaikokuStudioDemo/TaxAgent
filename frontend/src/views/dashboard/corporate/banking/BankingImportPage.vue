<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  Upload,
  CheckCircle,
  FileText,
  Loader2,
  X,
  Banknote,
  CreditCard,
  ChevronDown,
  ChevronUp,
} from 'lucide-vue-next';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import { useTransactions } from '@/composables/useTransactions';
import { useAuth } from '@/composables/useAuth';

const { getToken } = useAuth();
const { importTransactions } = useTransactions();

// --- TYPES ---
interface StagedTransaction {
  date: string;
  description: string;
  amount: number;
  transaction_type: 'debit' | 'credit';
  withdrawal_amount?: number;
  deposit_amount?: number;
}

interface StagedFile {
  id: string;
  file_name: string;
  file_type: 'csv' | 'pdf';
  source_type: 'bank' | 'card';
  account_name: string;
  transactions: StagedTransaction[];
  row_count: number;
  is_loading: boolean;
}

// --- STATE ---
const stagedFiles = ref<StagedFile[]>([]);
const isImporting = ref(false);
const isRegistering = ref(false);
const showSuccess = ref(false);
const expandedFileIds = ref<Set<string>>(new Set());

onMounted(() => {});

// --- ACCORDION ---
const toggleExpand = (fileId: string) => {
  const next = new Set(expandedFileIds.value);
  if (next.has(fileId)) {
    next.delete(fileId);
  } else {
    next.add(fileId);
  }
  expandedFileIds.value = next;
};

const getPreviewTransactions = (file: StagedFile) => file.transactions.slice(0, 20);

// --- COMPUTED ---
const totalRows = computed(() =>
  stagedFiles.value.reduce((sum, f) => sum + f.row_count, 0)
);
const hasReady = computed(() =>
  stagedFiles.value.some(f => !f.is_loading && f.row_count > 0)
);

// --- CSV PARSER ---
// 対応フォーマット:
//   3列: 日付, 摘要, 金額（マイナス=入金）
//   4列以上: 日付, 摘要, 出金額, 入金額[, 残高...]
const parseCsv = (text: string): StagedTransaction[] => {
  const lines = text.trim().split('\n').slice(1);
  return lines
    .map((line, i) => {
      const cols = line.split(',').map(s => s.trim().replace(/^"|"$/g, ''));
      const date = cols[0] || new Date().toISOString().slice(0, 10);
      const description = cols[1] || `明細${i + 1}`;
      const col2 = parseInt(cols[2]?.replace(/[¥,\s]/g, '') || '0', 10) || 0;
      const col3 = parseInt(cols[3]?.replace(/[¥,\s]/g, '') || '0', 10) || 0;

      let amount: number;
      let transaction_type: 'debit' | 'credit';
      let withdrawal_amount: number;
      let deposit_amount: number;

      if (cols.length >= 4) {
        withdrawal_amount = col2;
        deposit_amount = col3;
        if (col3 > 0 && col2 === 0) {
          amount = col3;
          transaction_type = 'credit';
        } else {
          amount = col2;
          transaction_type = 'debit';
        }
      } else {
        amount = Math.abs(col2);
        transaction_type = col2 < 0 ? 'credit' : 'debit';
        withdrawal_amount = transaction_type === 'debit' ? amount : 0;
        deposit_amount = transaction_type === 'credit' ? amount : 0;
      }

      return { date, description, amount, transaction_type, withdrawal_amount, deposit_amount };
    })
    .filter(t => t.amount > 0);
};

// --- PDF EXTRACT (preview only, no DB save) ---
const extractPdfTransactions = async (file: File): Promise<StagedTransaction[]> => {
  const formData = new FormData();
  formData.append('file', file);

  const token = await getToken();
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

  const res = await fetch(`${apiUrl}/transactions/extract-pdf`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token ?? ''}` },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? 'PDFの解析に失敗しました');
  }

  const data = await res.json();
  return (data.transactions ?? []) as StagedTransaction[];
};

// --- FILE PROCESSOR ---
const processFile = async (file: File) => {
  const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
  const fileId = `file-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const baseName = file.name.replace(/\.[^/.]+$/, '');

  if (isPdf) {
    stagedFiles.value.push({
      id: fileId,
      file_name: file.name,
      file_type: 'pdf',
      source_type: 'bank',
      account_name: baseName,
      transactions: [],
      row_count: 0,
      is_loading: true,
    });

    try {
      const transactions = await extractPdfTransactions(file);
      const idx = stagedFiles.value.findIndex(f => f.id === fileId);
      if (idx !== -1) {
        stagedFiles.value[idx] = {
          ...stagedFiles.value[idx],
          transactions,
          row_count: transactions.length,
          is_loading: false,
        };
      }
    } catch (e: any) {
      const idx = stagedFiles.value.findIndex(f => f.id === fileId);
      if (idx !== -1) stagedFiles.value.splice(idx, 1);
      alert(e.message ?? 'PDFの取り込み中にエラーが発生しました。');
    }
  } else {
    const text = await file.text();
    const transactions = parseCsv(text);
    stagedFiles.value.push({
      id: fileId,
      file_name: file.name,
      file_type: 'csv',
      source_type: 'bank',
      account_name: baseName,
      transactions,
      row_count: transactions.length,
      is_loading: false,
    });
  }
};

// --- FILE PICKER ---
const openFilePicker = () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.csv,text/csv,application/pdf,.pdf';
  input.multiple = true;
  input.onchange = async (e) => {
    const files = Array.from((e.target as HTMLInputElement).files ?? []);
    if (!files.length) return;
    isImporting.value = true;
    for (const file of files) {
      await processFile(file);
    }
    isImporting.value = false;
  };
  input.click();
};

// --- REMOVE FILE ---
const removeFile = (fileId: string) => {
  stagedFiles.value = stagedFiles.value.filter(f => f.id !== fileId);
};

// --- REGISTER ---
const handleRegister = async () => {
  if (!hasReady.value) return;
  isRegistering.value = true;

  for (const file of stagedFiles.value) {
    if (file.is_loading || file.transactions.length === 0) continue;

    await importTransactions({
      source_type: file.source_type,
      account_name: file.account_name || (file.source_type === 'bank' ? '銀行口座' : 'クレジットカード'),
      file_name: file.file_name,
      transactions: file.transactions.map(t => ({
        transaction_date: t.date,
        description: t.description,
        amount: t.amount,
        transaction_type: t.transaction_type,
        withdrawal_amount: t.withdrawal_amount ?? (t.transaction_type === 'debit' ? t.amount : 0),
        deposit_amount: t.deposit_amount ?? (t.transaction_type === 'credit' ? t.amount : 0),
      })),
    });
  }

  stagedFiles.value = [];
  isRegistering.value = false;
  showSuccess.value = true;
  setTimeout(() => { showSuccess.value = false; }, 5000);
};
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6 h-full flex flex-col">
    <!-- Header -->
    <div class="shrink-0">
      <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">データアップロード</h1>
      <p class="text-sm text-gray-500 mt-2">
        銀行口座・クレジットカードの利用明細（CSV・PDF）を取り込みます。<br/>
        ファイルごとに種別と口座名を設定してから一括登録してください。
      </p>
    </div>

    <!-- Success Banner -->
    <div v-if="showSuccess"
      class="bg-emerald-50 text-emerald-800 p-4 rounded-xl border border-emerald-200 flex items-center gap-3 shrink-0 animate-in fade-in slide-in-from-top-2">
      <CheckCircle class="h-5 w-5 text-emerald-500 shrink-0" />
      <p class="text-sm font-medium">データの登録が完了しました。マッチング画面で確認・消込を行ってください。</p>
    </div>

    <!-- Upload Area -->
    <div
      class="bg-white border-2 border-dashed border-gray-300 rounded-xl p-8 flex flex-col items-center justify-center text-center hover:border-blue-400 transition-colors shrink-0">
      <div class="h-12 w-12 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mb-4">
        <Upload class="h-6 w-6" />
      </div>
      <h3 class="font-bold text-gray-900 mb-1">明細ファイルをアップロード</h3>
      <p class="text-xs text-gray-500 mb-5">銀行口座・クレジットカードのCSVまたはPDFファイル</p>
      <button
        @click="openFilePicker"
        :disabled="isImporting"
        class="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white font-bold rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50">
        <Loader2 v-if="isImporting" class="h-4 w-4 animate-spin" />
        <Upload v-else class="h-4 w-4" />
        {{ isImporting ? '処理中...' : 'CSV / PDF を選択' }}
      </button>
      <p class="text-xs text-gray-400 mt-3">複数ファイルを同時に選択できます</p>
    </div>

    <!-- Staged Files -->
    <div v-if="stagedFiles.length > 0" class="flex-1 flex flex-col min-h-0 space-y-4">
      <!-- File List Header -->
      <div class="flex items-center justify-between shrink-0">
        <h2 class="font-bold text-gray-800">
          取り込みファイル
          <span class="ml-1.5 bg-gray-200 text-gray-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ stagedFiles.length }}件</span>
        </h2>
        <button
          v-if="hasReady"
          @click="handleRegister"
          :disabled="isRegistering"
          class="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-6 rounded-lg shadow-sm transition-colors disabled:opacity-50">
          <Loader2 v-if="isRegistering" class="h-4 w-4 animate-spin" />
          <CheckCircle v-else class="h-4 w-4" />
          {{ isRegistering ? '登録中...' : `${totalRows}件を一括登録` }}
        </button>
      </div>

      <!-- File Cards -->
      <div class="flex-1 overflow-y-auto min-h-0 space-y-3 pr-1">
        <div v-for="file in stagedFiles" :key="file.id"
          class="bg-white border border-gray-200 rounded-xl p-4 space-y-3">

          <!-- File Header -->
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 min-w-0">
              <FileText class="h-4 w-4 text-gray-400 shrink-0" />
              <span class="font-medium text-gray-900 text-sm truncate">{{ file.file_name }}</span>
              <span class="shrink-0 text-xs px-2 py-0.5 rounded-full font-bold"
                :class="file.file_type === 'pdf' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'">
                {{ file.file_type.toUpperCase() }}
              </span>
            </div>
            <button @click="removeFile(file.id)"
              class="text-gray-400 hover:text-red-500 transition-colors shrink-0 ml-2">
              <X class="h-4 w-4" />
            </button>
          </div>

          <!-- OCR Loading -->
          <div v-if="file.is_loading" class="flex items-center gap-2 text-blue-600 text-sm">
            <Loader2 class="h-4 w-4 animate-spin" />
            <span>OCR処理中...（数十秒かかる場合があります）</span>
          </div>

          <!-- Settings -->
          <div v-else class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-gray-600 mb-1">種別</label>
              <select v-model="file.source_type"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                <option value="bank">銀行口座明細</option>
                <option value="card">クレジットカード明細</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-bold text-gray-600 mb-1">口座名・カード名</label>
              <input v-model="file.account_name"
                type="text"
                placeholder="例: PayPay銀行、オリコカード"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
          </div>

          <!-- Row Count + Accordion Toggle -->
          <div v-if="!file.is_loading"
            class="flex items-center justify-between pt-2 border-t border-gray-100">
            <div class="flex items-center gap-1.5 text-xs text-gray-500">
              <span v-if="file.source_type === 'bank'" class="inline-flex items-center gap-1 text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full font-medium">
                <Banknote class="h-3 w-3" /> 銀行
              </span>
              <span v-else class="inline-flex items-center gap-1 text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full font-medium">
                <CreditCard class="h-3 w-3" /> カード
              </span>
              <span v-if="file.row_count > 0">{{ file.row_count }}件のデータを検出</span>
              <span v-else class="text-amber-600 font-medium">データが検出されませんでした</span>
            </div>
            <button v-if="file.row_count > 0"
              @click="toggleExpand(file.id)"
              class="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors">
              <ChevronUp v-if="expandedFileIds.has(file.id)" class="h-3.5 w-3.5" />
              <ChevronDown v-else class="h-3.5 w-3.5" />
              {{ expandedFileIds.has(file.id) ? '閉じる' : '明細を確認' }}
            </button>
          </div>

          <!-- Accordion: Transaction Table -->
          <div v-if="expandedFileIds.has(file.id) && file.transactions.length > 0"
            class="border border-gray-100 rounded-lg overflow-hidden">
            <table class="w-full text-xs">
              <thead class="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th class="text-left px-3 py-2 font-semibold text-gray-600 w-[110px]">日付</th>
                  <th class="text-left px-3 py-2 font-semibold text-gray-600">摘要</th>
                  <th class="text-right px-3 py-2 font-semibold text-gray-600 w-[90px]">出金</th>
                  <th class="text-right px-3 py-2 font-semibold text-gray-600 w-[90px]">入金</th>
                  <th class="text-center px-3 py-2 font-semibold text-gray-600 w-[60px]">種別</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50">
                <tr v-for="(tx, idx) in getPreviewTransactions(file)" :key="idx"
                  class="hover:bg-gray-50 transition-colors">
                  <td class="px-3 py-2 text-gray-600 whitespace-nowrap">{{ tx.date }}</td>
                  <td class="px-3 py-2 text-gray-800 max-w-[200px] truncate" :title="tx.description">
                    {{ tx.description }}
                  </td>
                  <td class="px-3 py-2 text-right text-red-600 whitespace-nowrap">
                    {{ (tx.withdrawal_amount ?? 0) > 0 ? `¥${formatAmount(tx.withdrawal_amount!)}` : '—' }}
                  </td>
                  <td class="px-3 py-2 text-right text-emerald-600 whitespace-nowrap">
                    {{ (tx.deposit_amount ?? 0) > 0 ? `¥${formatAmount(tx.deposit_amount!)}` : '—' }}
                  </td>
                  <td class="px-3 py-2 text-center">
                    <span class="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
                      :class="tx.transaction_type === 'debit' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'">
                      {{ tx.transaction_type === 'debit' ? '出金' : '入金' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="file.transactions.length > 20"
              class="px-3 py-2 text-center text-xs text-gray-400 bg-gray-50 border-t border-gray-100">
              ※ 先頭20件を表示。全{{ file.transactions.length }}件は登録後に確認できます。
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="flex-1 flex flex-col items-center justify-center text-gray-400 py-16">
      <FileText class="h-16 w-16 mb-4 text-gray-200" />
      <p class="text-sm font-medium text-gray-500">取り込み待ちのファイルはありません</p>
      <p class="text-xs mt-1 text-gray-400">上のボタンからCSV・PDFを選択してください</p>
    </div>
  </div>
</template>
