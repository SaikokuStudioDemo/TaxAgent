<script setup lang="ts">
import { ref, computed } from 'vue';
import {
  XCircle,
  FileText,
  Plus,
  CheckCircle,
  Building2
} from 'lucide-vue-next';
import { useApprovals, type AddedStep } from '@/composables/useApprovals';
import { APPROVAL_LEVELS, getRankFromRoleId } from '@/lib/constants/mockData';
import ApprovalStepper from '@/components/approvals/ApprovalStepper.vue';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import type { InvoiceItem } from '@/lib/types/approvalTypes';


const props = defineProps<{
  show: boolean;
  invoice: InvoiceItem | null;
  document_type?: 'issued' | 'received'; // Default to received if not specified
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'action-completed'): void;
}>();

// --- STATE ---
const { submitApprovalAction, isSubmitting, error } = useApprovals();
const actionComment = ref('');
const isAddingApprover = ref(false);
const selectedExtraApproverId = ref('');

const docType = computed(() => props.document_type === 'issued' ? 'issued_invoice' : 'received_invoice');

const availableApproversToAdd = computed(() => {
  if (!props.invoice || props.invoice.approvalHistory.length === 0) return [];
  
  const currentHistory = props.invoice.approvalHistory[props.invoice.currentStepIndex];
  if (!currentHistory) return APPROVAL_LEVELS.map(l => ({ id: l.value, roleId: l.value, roleName: l.label, name: l.label, rank: getRankFromRoleId(l.value) }));
  
  const currentRank = getRankFromRoleId(currentHistory.roleId);
  return APPROVAL_LEVELS
    .map(l => ({ id: l.value, roleId: l.value, roleName: l.label, name: l.label, rank: getRankFromRoleId(l.value) }))
    .filter(a => a.rank > currentRank);
});

// --- ACTIONS ---
const handleClose = () => {
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
  actionComment.value = '';
  emit('close');
};

const handleAddApprover = () => {
  if (!selectedExtraApproverId.value || !props.invoice) return;
  const level = APPROVAL_LEVELS.find(l => l.value === selectedExtraApproverId.value);
  const approver = level ? { id: level.value, roleId: level.value, roleName: level.label, name: level.label, rank: getRankFromRoleId(level.value) } : null;
  if (approver) {
    const newStepIndex = props.invoice.approvalHistory.length;
    props.invoice.approvalHistory.push({
      id: 'h_ext_' + Date.now(),
      step: newStepIndex + 1,
      roleId: approver.roleId,
      roleName: approver.roleName,
      approverName: approver.name,
      status: 'pending'
    });
  }
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
};

const handleApprove = async () => {
  if (!props.invoice) return;
  
  const extSteps: AddedStep[] = (props.invoice.approvalHistory || [])
    .filter(h => h.id.startsWith('h_ext_'))
    .map(h => ({
      roleId: h.roleId,
      roleName: h.roleName,
      approverName: h.approverName
    }));

  const success = await submitApprovalAction({
    documentType: docType.value,
    documentId: props.invoice.id,
    action: 'approved',
    step: props.invoice.currentStepIndex + 1,
    comment: actionComment.value,
    addedSteps: extSteps
  });

  if (success) {
    emit('action-completed');
  }
};

const handleReject = async () => {
  if (!props.invoice) return;
  if (!actionComment.value.trim()) {
    alert('差戻しの場合はコメント（理由）を入力してください。');
    return;
  }

  const success = await submitApprovalAction({
    documentType: docType.value,
    documentId: props.invoice.id,
    action: 'rejected',
    step: props.invoice.currentStepIndex + 1,
    comment: actionComment.value
  });

  if (success) {
    emit('action-completed');
  }
};
</script>

<template>
  <div v-if="show && invoice" class="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6 overflow-hidden" role="dialog" aria-modal="true">
    <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity" @click="handleClose"></div>

    <div class="relative w-full max-w-6xl h-[95vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
      <div class="h-full flex flex-col w-full overflow-y-auto bg-slate-50 relative">
        <!-- Header -->
        <div class="px-6 py-4 pr-20 bg-white border-b border-gray-200 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div>
            <h2 class="text-lg font-bold text-gray-900">{{ document_type === 'issued' ? '発行' : '受領' }}請求書詳細 : {{ invoice.id }}</h2>
            <p class="text-xs text-gray-500 mt-1">{{ document_type === 'issued' ? '取引先' : '仕入先' }}: <span class="font-medium text-gray-700">{{ invoice.vendorName }}</span></p>
          </div>
          <button @click="handleClose" class="rounded-full p-2 bg-gray-50 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
            <XCircle class="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        <!-- Content Area -->
        <div class="flex-1 overflow-y-auto p-6">
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full min-h-[600px]">
            
            <!-- Left Panel: Data & Flow -->
            <div class="lg:col-span-5 space-y-6 flex flex-col">
              <!-- Invoice Info -->
              <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-3">請求書詳細内容</h3>
                <dl class="grid grid-cols-1 gap-x-4 gap-y-4 text-sm">
                  <div class="flex justify-between items-center bg-gray-50 p-3 rounded-lg border border-gray-100">
                    <span class="text-gray-600 font-medium">合計請求金額</span>
                    <span class="text-2xl font-bold tracking-tight">¥{{ formatAmount(invoice.amount) }}<span class="text-[11px] font-normal text-gray-500 ml-1">(税込)</span></span>
                  </div>
                  <div class="grid grid-cols-2 gap-4">
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">{{ document_type === 'issued' ? '発行日' : '発行元記載日' }}</dt>
                      <dd class="font-medium text-gray-900">{{ invoice.issuedDate }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5" :class="document_type === 'received' ? 'text-red-600' : ''">支払期限</dt>
                      <dd class="font-bold" :class="document_type === 'received' ? 'text-red-700' : 'text-gray-900'">{{ invoice.dueDate }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">勘定科目</dt>
                      <dd class="font-medium text-blue-800 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded text-xs inline-block">{{ invoice.category }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">支払方法</dt>
                      <dd class="font-medium text-gray-900">{{ invoice.paymentMethod }}</dd>
                    </div>
                    <div class="col-span-2">
                        <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">{{ document_type === 'issued' ? '件名 / 取引内容' : '仕入元' }}</dt>
                        <dd class="font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded inline-block w-full flex items-center gap-2">
                            <Building2 class="w-3 h-3 text-gray-400" />
                            {{ document_type === 'issued' ? invoice.title : invoice.vendorName }}
                        </dd>
                    </div>
                  </div>
                  <div>
                    <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 mt-2">社内用メモ</dt>
                    <dd class="font-medium text-gray-900 break-words bg-yellow-50/50 p-2 rounded-lg border border-yellow-100/50 text-xs">{{ invoice.memo || 'なし' }}</dd>
                  </div>
                </dl>
              </div>

              <!-- Approval Progress Tree -->
              <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm flex-1">
                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-3 mb-4">承認フロー (進捗状況)</h3>
                <div class="mt-4 overflow-hidden relative">
                  <ApprovalStepper 
                    :document-type="docType"
                    mode="status"
                    :history="invoice.approvalHistory"
                    :current-step="invoice.currentStepIndex + 1"
                  />
                  
                  <!-- Additional Manual Actions -->
                  <div v-if="invoice.status === 'pending'" class="mt-8 pt-4 border-t border-gray-100 border-dashed">
                    <button v-if="!isAddingApprover" @click="isAddingApprover = true" class="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2.5 py-1.5 rounded-lg border border-blue-100 hover:bg-blue-100 transition-colors">
                      <Plus class="w-3.5 h-3.5 mr-1" />
                      承認者を追加 (個別対応)
                    </button>
                    <div v-else class="bg-gray-50 border border-gray-200 rounded-lg p-3 shadow-inner">
                      <p class="text-xs font-bold text-gray-700 mb-2">追加する承認者を選択</p>
                      <div class="flex items-center gap-2">
                        <select v-model="selectedExtraApproverId" class="block w-full rounded-md border-gray-300 border shadow-sm focus:border-blue-500 focus:ring-blue-500 text-xs py-1.5 px-2 bg-white">
                          <option value="" disabled>選択してください</option>
                          <option v-for="user in availableApproversToAdd" :key="user.id" :value="user.id">
                            {{ user.roleName }} - {{ user.name }}
                          </option>
                        </select>
                        <button @click="handleAddApprover" class="bg-blue-600 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-blue-700 whitespace-nowrap disabled:opacity-50" :disabled="!selectedExtraApproverId">追加</button>
                        <button @click="isAddingApprover = false" class="text-gray-500 hover:text-gray-700 px-2 py-1.5 rounded-md text-xs font-medium whitespace-nowrap bg-white border border-gray-200 shadow-sm">キャンセル</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right Panel: Viewer & Action -->
            <div class="lg:col-span-7 flex flex-col gap-4">
              <!-- PDF/Image Viewer -->
              <div class="bg-slate-200/50 rounded-xl overflow-hidden border border-gray-200 shadow-inner relative flex-1 min-h-[400px] flex items-center justify-center">
                <template v-if="invoice.imageUrl">
                  <iframe 
                    v-if="invoice.imageUrl.includes('.pdf')" 
                    :src="invoice.imageUrl" 
                    class="w-full h-full border-none"
                  ></iframe>
                  <img 
                    v-else 
                    :src="invoice.imageUrl" 
                    class="max-w-full max-h-full object-contain"
                    alt="Invoice Preview"
                  />
                </template>
                <div v-else class="text-center text-gray-400">
                  <FileText class="w-16 h-16 mx-auto mb-2 opacity-50" />
                  <p class="font-medium">請求書プレビュー</p>
                  <p class="text-xs">(原本がありません)</p>
                </div>
              </div>

              <!-- Action Area -->
              <div v-if="invoice.status === 'pending'" class="bg-white border border-gray-200 rounded-xl p-5 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]">
                <div class="mb-4">
                  <h3 class="text-sm font-bold text-gray-900 mb-2">承認/差戻しコメント（任意）</h3>
                  <textarea 
                    v-model="actionComment"
                    rows="2" 
                    class="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-3 border resize-none bg-gray-50/50" 
                    placeholder="確認いたしました。内容に問題ありません。"
                  ></textarea>
                </div>

                <div class="flex gap-3">
                  <button 
                    @click="handleReject"
                    :disabled="isSubmitting"
                    class="flex-[1] bg-white hover:bg-rose-50 border border-rose-200 text-rose-600 hover:text-rose-700 font-semibold py-3 px-4 rounded-xl shadow-sm transition-colors text-sm flex items-center justify-center gap-2"
                  >
                    <XCircle class="w-4 h-4"/>
                    差戻し
                  </button>
                  <button 
                    @click="handleApprove"
                    :disabled="isSubmitting"
                    class="flex-[2] bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-xl shadow-md flex justify-center items-center transition-all text-sm gap-2"
                  >
                    <svg v-if="isSubmitting" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <CheckCircle v-if="!isSubmitting" class="w-4 h-4" />
                    {{ isSubmitting ? '処理中...' : (document_type === 'issued' ? '承認して次へ' : '支払承認する') }}
                  </button>
                </div>
                <p v-if="error" class="mt-2 text-xs text-red-600 font-medium">{{ error }}</p>
              </div>
              
              <div v-else class="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center text-sm text-gray-500">
                この請求書は現在アクションを必要としていません。
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>
</template>
