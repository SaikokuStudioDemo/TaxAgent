<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { 
  CreditCard, 
  Banknote,
  Upload,
  CheckCircle,
  FileSpreadsheet
} from 'lucide-vue-next';
import { useBankTransactions } from '@/composables/useBankTransactions';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

// --- TYPES ---
interface StagedTransaction {
  id: string;
  date: string;
  description: string;
  amount: number;
  type: 'card' | 'bank';
  status: 'pending_import' | 'imported';
}

// --- COMPOSABLE ---
const { fetchTransactions, importTransactions } = useBankTransactions();

// --- STATE ---
const stagedTransactions = ref<StagedTransaction[]>([]);
const isImporting = ref(false);
const isRegistering = ref(false);
const showSuccess = ref(false);
const searchQuery = ref('');

// On mount: show already-imported transactions as reference
onMounted(async () => {
  await fetchTransactions({});
});

// --- COMPUTED ---
const filteredTransactions = computed(() =>
  stagedTransactions.value.filter(
    t => t.description.includes(searchQuery.value) || t.amount.toString().includes(searchQuery.value)
  )
);

const totalAmount = computed(() => stagedTransactions.value.reduce((sum, t) => sum + t.amount, 0));

// --- ACTIONS ---
// Parse a basic CSV string into transaction rows
const parseCsv = (text: string, type: 'bank' | 'card'): StagedTransaction[] => {
  const lines = text.trim().split('\n').slice(1); // skip header
  return lines.map((line, i) => {
    const cols = line.split(',').map(s => s.trim().replace(/^"|"$/g, ''));
    // Expected headers: 日付, 摘要, 出金額 (or 金額)
    const date = cols[0] || new Date().toISOString().slice(0, 10);
    const description = cols[1] || `明細${i + 1}`;
    const amount = parseInt(cols[2]?.replace(/[¥,\s]/g, '') || '0', 10) || 0;
    return { id: `staged-${type}-${i}`, date, description, amount, type, status: 'pending_import' as const };
  });
};

const openFilePicker = (type: 'bank' | 'card') => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.csv,text/csv';
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    isImporting.value = true;
    showSuccess.value = false;
    const text = await file.text();
    const parsed = parseCsv(text, type);
    // Merge with existing staged (avoid duplicates by description+date+amount)
    const existing = new Set(stagedTransactions.value.map(t => `${t.date}|${t.description}|${t.amount}`));
    const newOnes = parsed.filter(t => !existing.has(`${t.date}|${t.description}|${t.amount}`));
    stagedTransactions.value = [...stagedTransactions.value, ...newOnes];
    isImporting.value = false;
  };
  input.click();
};

const handleRegister = async () => {
  if (stagedTransactions.value.length === 0) return;
  isRegistering.value = true;

  // Group by type and import
  const byType = { bank: [] as StagedTransaction[], card: [] as StagedTransaction[] };
  stagedTransactions.value.forEach(t => byType[t.type].push(t));

  for (const [sourceType, txs] of Object.entries(byType)) {
    if (txs.length === 0) continue;
    const period = txs[0].date.slice(0, 7);
    await importTransactions({
      source_type: sourceType as 'bank' | 'card',
      account_name: sourceType === 'bank' ? '銀行口座' : 'クレジットカード',
      transactions: txs.map(t => ({
        transaction_date: t.date,
        description: t.description,
        amount: t.amount,
        direction: 'debit' as const,
        fiscal_period: period,
      })),
    });
  }

  stagedTransactions.value = [];
  isRegistering.value = false;
  showSuccess.value = true;
  await fetchTransactions({});
  setTimeout(() => { showSuccess.value = false; }, 5000);
};
</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6 h-full flex flex-col">
    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4 shrink-0">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">データアップロード (口座・カード)</h1>
        <p class="text-muted-foreground mt-2 text-sm text-gray-500">
          銀行口座やクレジットカードの利用明細（CSV）をシステムに取り込みます。<br/>
          取り込んだデータは「マッチング確認」画面にて、提出された領収書データと紐付けることができます。
        </p>
      </div>
    </div>

    <div v-if="showSuccess" class="bg-emerald-50 text-emerald-800 p-4 rounded-xl border border-emerald-200 flex items-center gap-3 shrink-0 animate-in fade-in slide-in-from-top-2">
        <CheckCircle class="h-5 w-5 text-emerald-500" />
        <p class="text-sm font-medium">データの取り込みを完了しました。マッチング画面で確認・結合を行ってください。</p>
    </div>

    <!-- Upload Actions Container -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 shrink-0">
        <!-- Bank Upload Card -->
        <div class="bg-white border border-gray-200 rounded-xl p-6 flex flex-col items-center justify-center text-center hover:border-blue-300 transition-colors shadow-sm">
            <div class="h-12 w-12 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mb-4">
                <Banknote class="h-6 w-6" />
            </div>
            <h3 class="font-bold text-gray-900 mb-1">銀行口座明細</h3>
            <p class="text-xs text-gray-500 mb-5">全銀協フォーマットなどのCSVファイル</p>
            <button 
                @click="openFilePicker('bank')"
                :disabled="isImporting"
                class="w-full inline-flex justify-center items-center px-4 py-2.5 border border-blue-200 shadow-sm text-sm font-bold rounded-lg text-blue-700 bg-blue-50 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 transition-colors"
                >
                <Upload class="-ml-1 mr-2 h-4 w-4" />
                CSVファイルを選択
            </button>
        </div>

        <!-- Card Upload Card -->
        <div class="bg-white border border-gray-200 rounded-xl p-6 flex flex-col items-center justify-center text-center hover:border-slate-400 transition-colors shadow-sm">
            <div class="h-12 w-12 bg-slate-100 text-slate-700 rounded-full flex items-center justify-center mb-4">
                <CreditCard class="h-6 w-6" />
            </div>
            <h3 class="font-bold text-gray-900 mb-1">クレジットカード明細</h3>
            <p class="text-xs text-gray-500 mb-5">各カード会社のCSVダウンロードファイル</p>
            <button 
                @click="openFilePicker('card')"
                :disabled="isImporting"
                class="w-full inline-flex justify-center items-center px-4 py-2.5 border border-transparent shadow-sm text-sm font-bold rounded-lg text-white bg-slate-800 hover:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-900 disabled:opacity-50 transition-colors"
            >
                <Upload class="-ml-1 mr-2 h-4 w-4" />
                CSVファイルを選択
            </button>
        </div>
    </div>

    <!-- Staged Data Preview -->
    <div class="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col min-h-[400px] overflow-hidden">
        <div class="p-4 border-b border-gray-200 bg-slate-50 flex items-center justify-between shrink-0">
            <div class="flex items-center gap-2">
                <FileSpreadsheet class="text-slate-600 h-5 w-5" />
                <h2 class="font-bold text-gray-800 text-base">取り込みプレビュー</h2>
                <span v-if="stagedTransactions.length > 0" class="bg-slate-200 text-slate-700 text-xs font-bold px-2 py-0.5 rounded-full">{{ stagedTransactions.length }}件</span>
            </div>
            <div v-if="stagedTransactions.length > 0" class="flex gap-4 items-center">
                <p class="text-sm font-medium text-gray-700">合計金額: <span class="text-lg font-bold ml-1">¥{{ formatAmount(totalAmount) }}</span></p>
                <button 
                    @click="handleRegister"
                    :disabled="isRegistering"
                    class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg shadow-sm flex items-center gap-2 transition-colors disabled:opacity-50"
                >
                    <svg v-if="isRegistering" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <CheckCircle v-else class="h-4 w-4" />
                    {{ isRegistering ? '登録中...' : 'データを登録する' }}
                </button>
            </div>
        </div>

        <!-- Table / Empty State -->
        <div class="flex-1 overflow-auto bg-gray-50/30">
            <div v-if="stagedTransactions.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400 py-20">
                <FileSpreadsheet class="h-16 w-16 mb-4 text-gray-200" />
                <p class="text-sm font-medium text-gray-500">現在、取り込み待機中（プレビュー）のデータはありません。</p>
                <p class="text-xs mt-1 text-gray-400">上部のボタンからCSVファイルを読み込んでください。</p>
            </div>
            <div v-else>
                <table class="min-w-full divide-y divide-gray-200 text-sm">
                    <thead class="bg-gray-50 sticky top-0 shadow-sm z-10">
                        <tr>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[100px]">種別</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-[120px]">利用日</th>
                            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">摘要・詳細</th>
                            <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-[150px]">出金額</th>
                            <th scope="col" class="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-[100px]">ステータス</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        <tr v-for="t in filteredTransactions" :key="t.id" class="hover:bg-gray-50 transition-colors">
                            <td class="px-6 py-4 whitespace-nowrap">
                                <span class="text-xs font-medium px-2 py-1 rounded-full border inline-flex items-center gap-1" :class="t.type === 'card' ? 'bg-slate-50 text-slate-700 border-slate-200' : 'bg-blue-50 text-blue-700 border-blue-200'">
                                    <CreditCard v-if="t.type === 'card'" class="h-3 w-3" />
                                    <Banknote v-else class="h-3 w-3" />
                                    {{ t.type === 'card' ? 'カード' : '銀行' }}
                                </span>
                            </td>
                            <td class="px-6 py-4 whitespace-nowrap text-gray-900 font-medium">{{ t.date }}</td>
                            <td class="px-6 py-4 text-gray-900">{{ t.description }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-right font-bold text-gray-900">¥{{ formatAmount(t.amount) }}</td>
                            <td class="px-6 py-4 whitespace-nowrap text-center">
                                <span class="text-xs text-yellow-600 bg-yellow-50 px-2.5 py-1 rounded-md border border-yellow-200 font-medium whitespace-nowrap">登録待ち</span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
  </div>
</template>
