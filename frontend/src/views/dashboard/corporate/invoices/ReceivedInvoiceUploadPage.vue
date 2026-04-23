<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { UploadCloud, ScanLine, AlertCircle, FileText, Loader2, Trash2, CheckCircle2 } from 'lucide-vue-next';
import { formatCurrency, formatInputAmount, parseInputAmount, getFiscalPeriod, formatDateISO } from '@/lib/utils/formatters';
import { calcTaxFromInclusive } from '@/lib/utils/taxUtils';
import { useInvoices } from '@/composables/useInvoices';
import { useAuth } from '@/composables/useAuth';
import { useProjects } from '@/composables/useProjects';
import { useFileUpload } from '@/composables/useFileUpload';

// Type definitions for staging received invoices
interface StagedInvoice {
  id: string; // Temporary ID for staging
  selected: boolean;
  issueDate: string;  // YYYY-MM-DD
  dueDate: string;    // YYYY-MM-DD
  amount: number;
  taxRate: number;    // 10, 8, 0
  issuer: string;     // 発行元
  projectId?: string; // Link to project
  status: 'new' | 'edited' | 'error';
  errorMessage?: string; // Optional error reason
  fileUrl?: string;
  storagePath?: string;
  fileName?: string;
}

const { createInvoice } = useInvoices();
const { userProfile } = useAuth();
const { projects, fetchProjects } = useProjects();
const { fileInput, isUploading: isExtracting, uploadSingleFileWithPath, openFilePicker: triggerFileInput, clearFileInput } = useFileUpload({
  storagePath: 'invoices/',
  corporateId: computed(() => userProfile.value?.corporate_id),
});

const stagedInvoices = ref<StagedInvoice[]>([]);
const isSubmitting = ref(false);
const showSuccessModal = ref(false);
const showErrorModal = ref(false);
const showImageModal = ref(false);
const selectedPreviewImageUrl = ref<string>('');
const successCount = ref(0);

onMounted(fetchProjects);

// Handle actual file selection and upload
const handleFileSelect = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (!target.files?.length) return;

  const files = Array.from(target.files);
  const newInvoices: StagedInvoice[] = [];

  for (const file of files) {
    const uploaded = await uploadSingleFileWithPath(file);
    if (!uploaded) {
      console.error('Upload failed for', file.name);
      alert('ファイルのアップロードに失敗しました。');
      break;
    }
    const issueDateObj = new Date();
    const issueDate = formatDateISO(issueDateObj);
    const dueDateObj = new Date(issueDateObj);
    dueDateObj.setMonth(dueDateObj.getMonth() + 1);
    const dueDate = formatDateISO(dueDateObj);

    newInvoices.push({
      id: crypto.randomUUID(),
      selected: true,
      issueDate,
      dueDate,
      amount: 0,
      taxRate: 10,
      issuer: file.name.split('.')[0],
      status: 'new',
      fileUrl: uploaded.url,
      storagePath: uploaded.storagePath,
      fileName: file.name,
    });
  }

  stagedInvoices.value.push(...newInvoices);
  clearFileInput();
};

// Selection logic
const selectAll = computed({
  get: () => stagedInvoices.value.length > 0 && stagedInvoices.value.every(r => r.selected),
  set: (val: boolean) => stagedInvoices.value.forEach(r => r.selected = val)
});

const selectedCount = computed(() => stagedInvoices.value.filter(r => r.selected).length);
const selectedTotalAmount = computed(() => stagedInvoices.value.filter(r => r.selected).reduce((sum, r) => sum + r.amount, 0));

// Remove row
const removeInvoice = (id: string) => {
  stagedInvoices.value = stagedInvoices.value.filter(r => r.id !== id);
};

// Preview Image
const previewInvoice = (invoice: StagedInvoice) => {
  if (invoice.fileUrl) {
    selectedPreviewImageUrl.value = invoice.fileUrl;
    showImageModal.value = true;
  }
};

// Submission Logic
const submitSelected = async () => {
  const selectedToSubmit = stagedInvoices.value.filter(r => r.selected);
  if (selectedToSubmit.length === 0) return;
  
  const hasErrors = selectedToSubmit.some(r => r.status === 'error');
  if (hasErrors) {
    showErrorModal.value = true;
    return;
  }
  
  isSubmitting.value = true;
  let saved = 0;
  
  try {
    const fiscal_period = getFiscalPeriod();
    for (const inv of selectedToSubmit) {
      const submittedBy = userProfile.value?.type === 'employee'
        ? userProfile.value?.data?._id
        : userProfile.value?.data?._id;
      const result = await createInvoice({
        document_type: 'received',
        invoice_number: `REC-${Date.now().toString().slice(-6)}`,
        client_name: inv.issuer,
        recipient_email: '',
        issue_date: inv.issueDate,
        due_date: inv.dueDate,
        subtotal: inv.amount - calcTaxFromInclusive(inv.amount, inv.taxRate ?? 10),
        tax_amount: calcTaxFromInclusive(inv.amount, inv.taxRate ?? 10),
        total_amount: inv.amount,
        fiscal_period,
        line_items: [{
          description: '請求書一括登録',
          category: '仕入',
          amount: inv.amount,
          tax_rate: inv.taxRate
        }],
        attachments: inv.fileUrl ? [inv.fileUrl] : [],
        storage_path: inv.storagePath,
        storage_url: inv.fileUrl,
        ...(submittedBy ? { submitted_by: submittedBy } : {}),
      });
      if (result) saved++;
    }
    
    const submittedIds = selectedToSubmit.map(r => r.id);
    successCount.value = saved;
    showSuccessModal.value = true;
    stagedInvoices.value = stagedInvoices.value.filter(r => !submittedIds.includes(r.id));
  } catch (err) {
    console.error('Submission failed', err);
    alert('登録に失敗しました。');
  } finally {
    isSubmitting.value = false;
  }
};

const handleAmountInput = (invoice: StagedInvoice, event: Event) => {
  const target = event.target as HTMLInputElement;
  const cursorPostion = target.selectionStart;
  const oldLength = target.value.length;
  
  const parsed = parseInputAmount(target.value);
  invoice.amount = parsed;
  
  const formatted = formatInputAmount(parsed);
  target.value = formatted;
  
  // Adjust cursor
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
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">受領請求書アップロード</h1>
        <p class="text-gray-500 mt-1">取引先から受領した請求書の画像やPDFを読み込み、データを抽出してシステムに登録します。</p>
      </div>
    </div>

    <!-- Hidden File Input -->
    <input 
      type="file" 
      ref="fileInput" 
      multiple 
      accept=".pdf,.jpg,.jpeg,.png" 
      class="hidden" 
      @change="handleFileSelect"
    />

    <!-- Upload Action Buttons -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Import Button -->
      <button 
        @click="triggerFileInput"
        :disabled="isExtracting"
        class="bg-white border-2 border-dashed border-indigo-200 hover:border-indigo-400 hover:bg-indigo-50 transition-all rounded-2xl p-8 flex flex-col items-center justify-center gap-3 group relative overflow-hidden"
      >
        <div class="w-16 h-16 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
          <UploadCloud :size="32" v-if="!isExtracting" />
          <UploadCloud :size="32" class="animate-pulse" v-else />
        </div>
        <div class="text-center">
          <h3 class="text-lg font-bold text-gray-900">画像/PDFインポート</h3>
          <p class="text-sm text-gray-500 mt-1">端末内の請求書ファイルを選択して読み込み</p>
        </div>
      </button>

      <!-- OCR Button -->
      <button 
        @click="triggerFileInput"
        :disabled="isExtracting"
        class="bg-white border-2 border-dashed border-emerald-200 hover:border-emerald-400 hover:bg-emerald-50 transition-all rounded-2xl p-8 flex flex-col items-center justify-center gap-3 group relative overflow-hidden"
      >
        <div class="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform">
          <ScanLine :size="32" v-if="!isExtracting" />
          <ScanLine :size="32" class="animate-pulse" v-else />
        </div>
        <div class="text-center">
          <h3 class="text-lg font-bold text-gray-900">カメラでOCR読み込み</h3>
          <p class="text-sm text-gray-500 mt-1">紙の請求書を撮影して文字を自動抽出</p>
        </div>
      </button>
    </div>

    <!-- Staging Data Area -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 flex flex-col mt-8" v-if="stagedInvoices.length > 0">
      <div class="px-6 py-5 border-b border-gray-100 flex justify-between items-center bg-gray-50/50 rounded-t-2xl">
        <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
          登録プレビュー <span class="bg-indigo-100 text-indigo-700 text-xs px-2.5 py-1 rounded-full font-bold">{{ stagedInvoices.length }}件</span>
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
              <th class="py-4 px-4 w-32">発行日</th>
              <th class="py-4 px-4 w-32">支払期日</th>
              <th class="py-4 px-4 min-w-[200px]">発行元 (請求元)</th>
              <th class="py-4 px-4 w-36 text-right">請求金額 (税込)</th>
              <th class="py-4 px-4 w-28">税率</th>
              <th class="py-4 px-4 w-40">紐付けプロジェクト</th>
              <th class="py-4 px-4 w-24 text-center">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 text-sm">
            <tr v-for="invoice in stagedInvoices" :key="invoice.id" class="hover:bg-gray-50/50 transition-colors" :class="{'bg-indigo-50/20': invoice.selected, 'bg-red-50/20': invoice.status === 'error'}">
              <td class="py-4 px-4 text-center">
                <div class="flex items-center justify-center gap-2 group relative">
                  <input type="checkbox" v-model="invoice.selected" class="w-4 h-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500">
                  <div v-if="invoice.status === 'error'" class="cursor-help relative">
                    <AlertCircle :size="16" class="text-red-500" />
                    <div class="absolute bottom-full left-0 mb-2 w-56 p-2 bg-gray-900 text-white text-xs rounded shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10 break-words text-left">
                      {{ invoice.errorMessage }}
                      <div class="absolute top-full left-2 border-4 border-transparent border-t-gray-900"></div>
                    </div>
                  </div>
                </div>
              </td>
              <td class="py-4 px-4">
                <input type="date" v-model="invoice.issueDate" :class="{'text-red-600': invoice.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors font-mono text-sm">
              </td>
              <td class="py-4 px-4">
                <input type="date" v-model="invoice.dueDate" :class="{'text-red-600': invoice.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors font-mono text-sm">
              </td>
              <td class="py-4 px-4">
                <input type="text" v-model="invoice.issuer" placeholder="発行元を入力" :class="{'text-red-600': invoice.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors font-medium text-gray-900">
              </td>
              <td class="py-4 px-4">
                <div class="relative">
                  <span class="absolute left-2 top-1 text-gray-400 font-bold" :class="{'text-red-400': invoice.status === 'error'}">¥</span>
                  <input type="text" :value="formatInputAmount(invoice.amount)" @input="handleAmountInput(invoice, $event)" :class="{'text-red-600': invoice.status === 'error'}" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded pl-6 pr-2 py-1 w-full text-right font-bold transition-colors text-gray-900">
                </div>
              </td>
              <td class="py-4 px-4">
                <select v-model="invoice.taxRate" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors text-right pl-4 pr-6 appearance-none shadow-none" style="background-image: url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 20 20\'%3E%3Cpath stroke=\'%236b7280\' stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'1.5\' d=\'m6 8 4 4 4-4\'/%3E%3C/svg%3E'); background-position: right 0.25rem center; background-size: 1.2em 1.2em; background-repeat: no-repeat;">
                  <option :value="10">10%</option>
                  <option :value="8">8%</option>
                  <option :value="0">0%</option>
                </select>
              </td>
              <td class="py-4 px-4">
                <select v-model="invoice.projectId" class="bg-transparent border border-transparent hover:border-gray-300 focus:bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded px-2 py-1 w-full transition-colors truncate pr-6 appearance-none shadow-none" style="background-image: url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 20 20\'%3E%3Cpath stroke=\'%236b7280\' stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'1.5\' d=\'m6 8 4 4 4-4\'/%3E%3C/svg%3E'); background-position: right 0.25rem center; background-size: 1.2em 1.2em; background-repeat: no-repeat;">
                  <option value="">指定なし (部門費)</option>
                  <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}</option>
                </select>
              </td>
              <td class="py-4 px-4 text-center">
                <div class="flex items-center justify-center gap-3">
                  <button @click="previewInvoice(invoice)" class="text-gray-400 hover:text-indigo-600 transition-colors p-1 rounded-md hover:bg-indigo-50" title="画像を確認">
                    <FileText :size="18" />
                  </button>
                  <button @click="removeInvoice(invoice.id)" class="text-gray-400 hover:text-red-500 transition-colors p-1 rounded-md hover:bg-red-50" title="削除">
                    <Trash2 :size="18" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div class="px-6 py-5 border-t border-gray-100 bg-gray-50/50 rounded-b-2xl flex justify-between items-center">
        <div class="text-sm text-gray-500">
          ※ AIが読み取れなかった項目は手入力で補完してください
        </div>
        <button 
          @click="submitSelected"
          :disabled="isSubmitting || selectedCount === 0"
          class="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white px-8 py-2.5 rounded-lg font-bold shadow-sm transition-all flex items-center gap-2"
        >
          <Loader2 v-if="isSubmitting" :size="18" class="animate-spin" />
          <span v-else>選択した請求書を登録する</span>
        </button>
      </div>
    </div>
    
  </div>

  <!-- Success Modal -->
  <div v-if="showSuccessModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
    <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 text-center transform scale-100 transition-transform">
      <div class="w-16 h-16 bg-green-100 text-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
        <CheckCircle2 :size="32" />
      </div>
      <h3 class="text-xl font-bold text-gray-900 mb-2">登録が完了しました</h3>
      <p class="text-gray-500 text-sm mb-6">
        選択された <span class="font-bold text-gray-900">{{ successCount }}件</span> の受領請求書をデータとして登録しました。
      </p>
      <button @click="showSuccessModal = false" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-xl transition-colors">
        閉じる
      </button>
    </div>
  </div>

  <!-- Error Modal -->
  <div v-if="showErrorModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
    <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 text-center transform scale-100 transition-transform">
      <div class="w-16 h-16 bg-red-100 text-red-500 rounded-full flex items-center justify-center mx-auto mb-4">
        <AlertCircle :size="32" />
      </div>
      <h3 class="text-xl font-bold text-gray-900 mb-2">エラーがあります</h3>
      <p class="text-gray-500 text-sm mb-6">
        選択された請求書の中にエラー（赤色）が含まれています。登録前に内容を修正するか、選択を解除してください。
      </p>
      <button @click="showErrorModal = false" class="w-full bg-gray-100 hover:bg-gray-200 text-gray-800 font-bold py-2.5 rounded-xl transition-colors">
        確認する
      </button>
    </div>
  </div>

  <!-- Image Preview Modal -->
  <div v-if="showImageModal" class="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/80 backdrop-blur-sm p-4">
    <div class="w-full max-w-4xl bg-white rounded-t-xl flex justify-between items-center p-4">
      <h3 class="font-bold text-gray-900">ファイルプレビュー</h3>
      <button @click="showImageModal = false" class="text-gray-400 hover:text-gray-600 font-bold p-2 bg-gray-100 rounded-lg">閉じる</button>
    </div>
    <div class="w-full max-w-4xl bg-gray-100 rounded-b-xl overflow-hidden flex items-center justify-center p-4">
      <img :src="selectedPreviewImageUrl" alt="Invoice Preview" class="max-h-[70vh] object-contain shadow-sm border border-gray-300">
    </div>
  </div>
</template>
