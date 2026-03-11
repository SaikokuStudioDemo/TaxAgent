<script setup lang="ts">
import { ref, computed } from 'vue';
import { UploadCloud, ScanLine, Trash2, CheckCircle2, Save, Loader2, AlertCircle, FileText } from 'lucide-vue-next';
import { formatCurrency } from '@/lib/utils/formatters';
import { useReceipts } from '@/composables/useReceipts';

// Type definitions for staging receipts
interface StagedReceipt {
  id: string;
  selected: boolean;
  date: string;
  amount: number;
  taxRate: number;
  paymentMethod: '立替' | '法人カード';
  projectId?: string;
  payee: string;
  category: string;
  status: 'new' | 'edited' | 'error';
  errorMessage?: string;
}

const { createReceipt } = useReceipts();

const stagedReceipts = ref<StagedReceipt[]>([]);
const isSubmitting = ref(false);
const isExtracting = ref(false);
const showSuccessModal = ref(false);
const showErrorModal = ref(false);
const showImageModal = ref(false);
const selectedPreviewImageUrl = ref<string>('');
const successCount = ref(0);

const categories = ['消耗品費', '交際費', '旅費交通費', '通信費', '会議費'];
const PROJECTS = [
  { id: '', name: '指定なし (部門費)' },
  { id: 'proj-1', name: '社内基幹システムリプレイス' },
  { id: 'proj-2', name: '〇〇株式会社様 Webサイト制作' }
];

// Simulate OCR/Import extraction (staging only — no DB write here)
const simulateExtraction = async (type: 'import' | 'ocr') => {
  isExtracting.value = true;
  await new Promise(resolve => setTimeout(resolve, 1500));

  const newReceipts: StagedReceipt[] = [];
  const count = type === 'ocr' ? 1 : Math.floor(Math.random() * 3) + 2;

  for (let i = 0; i < count; i++) {
    const amount = Math.floor(Math.random() * 20000) + 1000;
    const isError = Math.random() > 0.8;

    newReceipts.push({
      id: crypto.randomUUID(),
      selected: !isError,
      date: new Date(Date.now() - Math.floor(Math.random() * 10000000000)).toISOString().split('T')[0],
      amount,
      taxRate: 10,
      paymentMethod: Math.random() > 0.5 ? '立替' : '法人カード',
      projectId: Math.random() > 0.6 ? PROJECTS[Math.floor(Math.random() * (PROJECTS.length - 1)) + 1].id : '',
      payee: `テスト加盟店 ${Math.floor(Math.random() * 100)}`,
      category: categories[Math.floor(Math.random() * categories.length)],
      status: isError ? 'error' : 'new',
      errorMessage: isError ? '金額と税率の整合性が確認できませんでした。原本を確認してください。' : undefined,
    });
  }

  stagedReceipts.value.push(...newReceipts);
  isExtracting.value = false;
};

const selectAll = computed({
  get: () => stagedReceipts.value.length > 0 && stagedReceipts.value.every(r => r.selected),
  set: (val: boolean) => stagedReceipts.value.forEach(r => r.selected = val),
});

const selectedCount = computed(() => stagedReceipts.value.filter(r => r.selected).length);
const selectedTotalAmount = computed(() => stagedReceipts.value.filter(r => r.selected).reduce((sum, r) => sum + r.amount, 0));

const removeReceipt = (id: string) => {
  stagedReceipts.value = stagedReceipts.value.filter(r => r.id !== id);
};

const previewReceipt = (_receipt: StagedReceipt) => {
  selectedPreviewImageUrl.value = 'https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80';
  showImageModal.value = true;
};

// Submit staged receipts to the real API
const submitSelected = async () => {
  const selectedToSubmit = stagedReceipts.value.filter(r => r.selected);
  if (selectedToSubmit.length === 0) return;

  const hasErrors = selectedToSubmit.some(r => r.status === 'error');
  if (hasErrors) {
    showErrorModal.value = true;
    return;
  }

  isSubmitting.value = true;
  let saved = 0;

  try {
    // Submit each receipt one by one (supports approval rule evaluation per item)
    const currentMonth = new Date().toISOString().slice(0, 7);
    for (const r of selectedToSubmit) {
      const result = await createReceipt({
        date: r.date,
        amount: r.amount,
        tax_rate: r.taxRate,
        payment_method: r.paymentMethod,
        payee: r.payee,
        category: r.category,
        fiscal_period: currentMonth,
      });
      if (result) saved++;
    }

    const submittedIds = selectedToSubmit.map(r => r.id);
    successCount.value = saved;
    showSuccessModal.value = true;
    stagedReceipts.value = stagedReceipts.value.filter(r => !submittedIds.includes(r.id));
  } catch (err) {
    console.error('Submission failed', err);
    alert('登録に失敗しました。');
  } finally {
    isSubmitting.value = false;
  }
};

const formatInputAmount = (val: number | string) => {
  if (val === null || val === undefined || val === '') return '';
  const numStr = val.toString().replace(/[^\d]/g, '');
  if (!numStr) return '';
  return parseInt(numStr, 10).toLocaleString('ja-JP');
};

const parseInputAmount = (val: string) => {
  const parsed = parseInt(val.replace(/[^\d]/g, ''), 10);
  return isNaN(parsed) ? 0 : parsed;
};

const handleAmountInput = (receipt: StagedReceipt, event: Event) => {
  const target = event.target as HTMLInputElement;
  const cursorPostion = target.selectionStart;
  const oldLength = target.value.length;
  const parsed = parseInputAmount(target.value);
  receipt.amount = parsed;
  const formatted = formatInputAmount(parsed);
  target.value = formatted;
  if (cursorPostion !== null) {
    const diff = formatted.length - oldLength;
    const newPos = Math.max(0, cursorPostion + diff);
    target.setSelectionRange(newPos, newPos);
  }
};
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-end mb-2">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">領収書提出</h1>
        <p class="text-gray-500 mt-1">画像やPDFを読み込み、データを抽出して登録リストに追加します。</p>
      </div>
    </div>

    <!-- Upload Action Buttons -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Import Button -->
      <button 
        @click="simulateExtraction('import')"
        :disabled="isExtracting"
        class="bg-white border-2 border-dashed border-indigo-200 hover:border-indigo-400 hover:bg-indigo-50 transition-all rounded-2xl p-8 flex flex-col items-center justify-center gap-3 group relative overflow-hidden"
      >
        <div class="w-16 h-16 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
          <UploadCloud :size="32" v-if="!isExtracting" />
          <UploadCloud :size="32" class="animate-pulse" v-else />
        </div>
        <div class="text-center">
          <h3 class="text-lg font-bold text-gray-900">画像/PDFインポート</h3>
          <p class="text-sm text-gray-500 mt-1">端末内のファイルを選択して読み込み</p>
        </div>
      </button>

      <!-- OCR Button -->
      <button 
        @click="simulateExtraction('ocr')"
        :disabled="isExtracting"
        class="bg-white border-2 border-dashed border-emerald-200 hover:border-emerald-400 hover:bg-emerald-50 transition-all rounded-2xl p-8 flex flex-col items-center justify-center gap-3 group relative overflow-hidden"
      >
        <div class="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
          <ScanLine :size="32" v-if="!isExtracting" />
          <ScanLine :size="32" class="animate-pulse" v-else />
        </div>
        <div class="text-center">
          <h3 class="text-lg font-bold text-gray-900">カメラでOCR読み込み</h3>
          <p class="text-sm text-gray-500 mt-1">領収書を撮影して文字を自動抽出</p>
        </div>
      </button>
    </div>

    <!-- Staging Data Area -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 flex flex-col mt-8" v-if="stagedReceipts.length > 0">
      <div class="px-6 py-5 border-b border-gray-100 flex justify-between items-center bg-gray-50/50 rounded-t-2xl">
        <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
          登録プレビュー <span class="bg-indigo-100 text-indigo-700 text-xs px-2.5 py-1 rounded-full font-bold">{{ stagedReceipts.length }}件</span>
        </h2>
        <div class="text-sm text-gray-500 font-medium">
          選択中: <span class="text-indigo-600 font-bold">{{ selectedCount }}件</span> (合計 {{ formatCurrency(selectedTotalAmount) }})
        </div>
      </div>
      
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-white text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-100">
              <th class="py-4 px-4 w-16 text-center">
                <input type="checkbox" v-model="selectAll" class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
              </th>
              <th class="py-4 px-4 w-32">日付</th>
              <th class="py-4 px-4 min-w-[150px]">発行元 / 店舗</th>
              <th class="py-4 px-4 w-36 text-right">金額 (税込)</th>
              <th class="py-4 px-4 w-28">税率</th>
              <th class="py-4 px-4 w-36">決済手段</th>
              <th class="py-4 px-4 w-40">プロジェクト</th>
              <th class="py-4 px-4 w-40">勘定科目</th>
              <th class="py-4 px-4 w-24 text-center">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 text-sm">
            <tr v-for="receipt in stagedReceipts" :key="receipt.id" class="hover:bg-gray-50/50 transition-colors" :class="{'bg-indigo-50/20': receipt.selected, 'bg-red-50/20': receipt.status === 'error'}">
              <td class="py-4 px-4 text-center">
                <div class="flex items-center justify-center gap-2 group relative">
                  <input type="checkbox" v-model="receipt.selected" class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
                  <div v-if="receipt.status === 'error'" class="cursor-help relative">
                    <AlertCircle :size="16" class="text-red-500" />
                    <!-- Left-aligned tooltip to prevent viewport cutoff on the left edge -->
                    <div class="absolute bottom-full left-0 mb-2 w-56 p-2 bg-gray-900 text-white text-xs rounded shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 break-words text-left">
                      {{ receipt.errorMessage }}
                      <!-- Triangle caret pointing to the icon -->
                      <div class="absolute top-full left-2 border-4 border-transparent border-t-gray-900"></div>
                    </div>
                  </div>
                </div>
              </td>
              <td class="py-4 px-4">
                <input type="date" v-model="receipt.date" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors font-mono text-sm">
              </td>
              <td class="py-4 px-4">
                <input type="text" v-model="receipt.payee" placeholder="発行元を入力" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors font-medium text-gray-900">
              </td>
              <td class="py-4 px-4">
                <div class="relative">
                  <span class="absolute left-2 top-1 text-gray-400 font-bold" :class="{'text-red-400': receipt.status === 'error'}">¥</span>
                  <input type="text" :value="formatInputAmount(receipt.amount)" @input="handleAmountInput(receipt, $event)" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded pl-6 pr-2 py-1 w-full text-right font-bold transition-colors text-gray-900">
                </div>
              </td>
              <td class="py-4 px-4">
                <select v-model="receipt.taxRate" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors text-gray-900">
                  <option :value="10">10%</option>
                  <option :value="8">8% (軽減)</option>
                  <option :value="0">対象外</option>
                </select>
              </td>
              <td class="py-4 px-4">
                <select v-model="receipt.paymentMethod" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors text-gray-900 font-medium">
                  <option value="立替">立替精算</option>
                  <option value="法人カード">法人カード</option>
                </select>
              </td>
              <td class="py-4 px-4">
                <select v-model="receipt.projectId" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors text-gray-700">
                  <option v-for="proj in PROJECTS" :key="proj.id" :value="proj.id">{{ proj.name }}</option>
                </select>
              </td>
              <td class="py-4 px-4">
                <select v-model="receipt.category" :class="{'text-red-600': receipt.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors text-gray-700">
                  <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
                </select>
              </td>
              <td class="py-4 px-4 text-center">
                <div class="flex items-center justify-center gap-1">
                  <button @click.prevent="previewReceipt(receipt)" class="text-indigo-400 hover:text-indigo-600 transition-colors p-1.5 rounded-lg hover:bg-indigo-50" title="原本プレビュー">
                    <FileText :size="18" />
                  </button>
                  <button @click="removeReceipt(receipt.id)" class="text-gray-400 hover:text-red-500 transition-colors p-1.5 rounded-lg hover:bg-red-50" title="削除">
                    <Trash2 :size="18" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Action Footer -->
      <div class="p-6 border-t border-gray-100 bg-gray-50 flex justify-end rounded-b-2xl">
        <button 
          @click="submitSelected"
          :disabled="selectedCount === 0 || isSubmitting"
          class="flex items-center gap-2 bg-indigo-600 text-white font-bold py-3 px-8 rounded-xl hover:bg-indigo-700 shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Loader2 v-if="isSubmitting" :size="20" class="animate-spin" />
          <Save v-else :size="20" />
          {{ isSubmitting ? '登録中...' : `選択した ${selectedCount} 件を登録` }}
        </button>
      </div>

    </div>
    
    <!-- Empty State for Staging Area -->
    <div v-if="stagedReceipts.length === 0 && !isExtracting" class="bg-white rounded-2xl shadow-sm border border-gray-200 border-dashed p-12 flex flex-col items-center justify-center text-gray-400 mt-8">
      <CheckCircle2 :size="48" class="text-gray-200 mb-4" />
      <p class="font-medium text-lg text-gray-500">登録待ちの領収書はありません</p>
      <p class="text-sm mt-1 text-gray-400">上のボタンから画像やPDFを読み込んでください</p>
    </div>

    <!-- Success Modal -->
    <div v-if="showSuccessModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/50 backdrop-blur-sm transition-opacity">
      <div class="bg-white rounded-3xl p-8 max-w-sm w-full shadow-2xl transform transition-all text-center">
        <div class="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-4">
          <CheckCircle2 :size="32" />
        </div>
        <h3 class="text-xl font-bold text-gray-900 mb-2">登録完了</h3>
        <p class="text-gray-500 mb-6 font-medium">{{ successCount }}件の領収書データを<br/>正常に登録しました。</p>
        <button 
          @click="showSuccessModal = false"
          class="w-full bg-gray-900 text-white font-bold py-3 px-4 rounded-xl hover:bg-gray-800 transition-colors"
        >
          OK
        </button>
      </div>
    </div>

    <!-- Error Modal (Validation Block) -->
    <div v-if="showErrorModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/50 backdrop-blur-sm transition-opacity">
      <div class="bg-white rounded-3xl p-8 max-w-sm w-full shadow-2xl transform transition-all text-center border-t-8 border-red-500">
        <div class="w-16 h-16 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4">
          <AlertCircle :size="32" />
        </div>
        <h3 class="text-xl font-bold text-gray-900 mb-2">登録エラー</h3>
        <p class="text-gray-500 mb-6 font-medium leading-relaxed">
          エラー警告がある領収書が含まれています。<br/><br/>
          <span class="text-sm">先に内容を修正（税率・金額の確認など）するか、左側のチェックを外してから再度お試しください。</span>
        </p>
        <button 
          @click="showErrorModal = false"
          class="w-full bg-red-600 text-white font-bold py-3 px-4 rounded-xl hover:bg-red-700 transition-colors"
        >
          閉じる
        </button>
      </div>
    </div>

    <!-- Image Preview Modal -->
    <div v-if="showImageModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/80 backdrop-blur-sm transition-opacity" @click.self="showImageModal = false">
      <div class="bg-white rounded-2xl overflow-hidden shadow-2xl flex flex-col md:flex-row max-w-4xl w-full max-h-[90vh]">
        <!-- Image Container -->
        <div class="bg-gray-100 flex-1 flex items-center justify-center p-4 md:p-8 min-h-[300px] overflow-hidden">
          <img :src="selectedPreviewImageUrl" alt="Receipt Preview" class="max-h-full max-w-full object-contain rounded drop-shadow-md" />
        </div>
        <!-- Sidebar Info -->
        <div class="w-full md:w-80 bg-white p-6 flex flex-col shrink-0 border-l border-gray-100">
            <h3 class="text-lg font-bold text-gray-900 mb-4 border-b pb-2">原本プレビュー</h3>
            <p class="text-sm text-gray-500 mb-6 leading-relaxed">
              アップロードされた画像と抽出結果を見比べて、金額や税率などに間違いがないか確認してください。
            </p>
            <div class="mt-auto">
              <button 
                @click="showImageModal = false"
                class="w-full bg-gray-100 text-gray-800 font-bold py-3 px-4 rounded-xl hover:bg-gray-200 transition-colors"
              >
                閉じる
              </button>
            </div>
        </div>
      </div>
    </div>
  </div>
</template>
