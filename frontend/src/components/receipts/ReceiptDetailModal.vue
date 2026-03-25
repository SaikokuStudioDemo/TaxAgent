<script setup lang="ts">
import { ref, computed } from 'vue';
import {
  XCircle,
  FileText,
  Plus,
  CheckCircle
} from 'lucide-vue-next';
import { useApprovals, type AddedStep } from '@/composables/useApprovals';
import { APPROVAL_LEVELS, getRankFromRoleId } from '@/lib/constants/mockData';
import ApprovalStepper from '@/components/approvals/ApprovalStepper.vue';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import type { ReceiptItem } from '@/lib/types/approvalTypes';


const props = defineProps<{
  show: boolean;
  receipt: ReceiptItem | null;
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

const availableApproversToAdd = computed(() => {
  if (!props.receipt || props.receipt.approvalHistory.length === 0) return [];
  
  const currentHistory = props.receipt.approvalHistory[props.receipt.currentStepIndex];
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
  if (!selectedExtraApproverId.value || !props.receipt) return;
  const level = APPROVAL_LEVELS.find(l => l.value === selectedExtraApproverId.value);
  const approver = level ? { id: level.value, roleId: level.value, roleName: level.label, name: level.label, rank: getRankFromRoleId(level.value) } : null;
  if (approver) {
    const newStepIndex = props.receipt.approvalHistory.length;
    props.receipt.approvalHistory.push({
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
  if (!props.receipt) return;
  
  const extSteps: AddedStep[] = props.receipt.approvalHistory
    .filter(h => h.id.startsWith('h_ext_'))
    .map(h => ({
      roleId: h.roleId,
      roleName: h.roleName,
      approverName: h.approverName
    }));

  const success = await submitApprovalAction({
    documentType: 'receipt',
    documentId: props.receipt.id,
    action: 'approved',
    step: props.receipt.currentStepIndex + 1,
    comment: actionComment.value,
    addedSteps: extSteps
  });

  if (success) {
    emit('action-completed');
  }
};

const handleReject = async () => {
  if (!props.receipt) return;
  if (!actionComment.value.trim()) {
    alert('差戻しの場合はコメント（理由）を入力してください。');
    return;
  }

  const success = await submitApprovalAction({
    documentType: 'receipt',
    documentId: props.receipt.id,
    action: 'rejected',
    step: props.receipt.currentStepIndex + 1,
    comment: actionComment.value
  });

  if (success) {
    emit('action-completed');
  }
};
</script>

<template>
  <div v-if="show && receipt" class="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6 overflow-hidden" role="dialog" aria-modal="true">
    <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity" @click="handleClose"></div>

    <div class="relative w-full max-w-6xl h-[95vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
      <div class="h-full flex flex-col w-full overflow-y-auto bg-slate-50 relative">
        <!-- Header -->
        <div class="px-6 py-4 pr-20 bg-white border-b border-gray-200 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div>
            <h2 class="text-lg font-bold text-gray-900">申請詳細 : {{ receipt.id }}</h2>
            <p class="text-xs text-gray-500 mt-1">提出者: <span class="font-medium text-gray-700">{{ receipt.submitterName }}</span></p>
          </div>
          <button @click="handleClose" class="rounded-full p-2 bg-gray-50 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
            <XCircle class="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        <!-- Content Area -->
        <div class="flex-1 overflow-y-auto p-6">
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full min-h-[600px]">
            
            <!-- Left Panel: Data & Flow (Occupies 5 columns) -->
            <div class="lg:col-span-5 space-y-6 flex flex-col">
              <!-- Receipt Info -->
              <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-3">領収書内容</h3>
                <dl class="grid grid-cols-1 gap-x-4 gap-y-4 text-sm">
                  <div class="flex justify-between items-center bg-gray-50 p-3 rounded-lg border border-gray-100">
                    <span class="text-gray-600 font-medium">合計金額</span>
                    <span class="text-2xl font-bold tracking-tight">¥{{ formatAmount(receipt.amount) }}<span class="text-[11px] font-normal text-gray-500 ml-1">(税込)</span></span>
                  </div>
                  <div class="grid grid-cols-2 gap-4">
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">申請日</dt>
                      <dd class="font-medium text-gray-900">{{ receipt.date }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">適用税率</dt>
                      <dd class="font-medium text-gray-900">{{ receipt.taxRate }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">勘定科目</dt>
                      <dd class="font-medium text-blue-800 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded text-xs inline-block">{{ receipt.category }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">決済手段</dt>
                      <dd class="font-medium text-gray-900">{{ receipt.paymentMethod }}</dd>
                    </div>
                    <div class="col-span-2">
                      <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">発行元 / 店舗</dt>
                      <dd class="font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded inline-block">{{ receipt.issuer }}</dd>
                    </div>
                  </div>
                  <div>
                    <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 mt-2">メモ・備考</dt>
                    <dd class="font-medium text-gray-900 break-words bg-yellow-50/50 p-2 rounded-lg border border-yellow-100/50 text-xs">{{ receipt.memo }}</dd>
                  </div>
                  
                  <div v-if="receipt.projectName" class="pt-2 border-t border-gray-100 mt-2">
                    <dt class="text-purple-600 text-[11px] tracking-wide flex items-center gap-1 mb-1"><Plus class="w-3 h-3"/>紐付けプロジェクト</dt>
                    <dd class="font-medium text-purple-900 bg-purple-50 px-2 py-1 rounded inline-block text-xs border border-purple-100 w-full truncate">
                      {{ receipt.projectName }}
                    </dd>
                  </div>
                </dl>
              </div>

              <!-- Approval Progress Tree -->
              <div class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm flex-1">
                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-3 mb-4">承認フロー (進捗状況)</h3>
                <div class="mt-4 overflow-hidden relative">
                  <ApprovalStepper 
                    document-type="receipt"
                    mode="status"
                    :history="receipt.approvalHistory"
                    :current-step="receipt.currentStepIndex + 1"
                  />
                  
                  <!-- Additional Manual Actions for Ad-Hoc Approver -->
                  <div v-if="receipt.status === 'pending'" class="mt-8 pt-4 border-t border-gray-100 border-dashed">
                    <button v-if="!isAddingApprover" @click="isAddingApprover = true" class="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2.5 py-1.5 rounded-lg border border-blue-100 hover:bg-blue-100 transition-colors">
                      <Plus class="w-3.5 h-3.5 mr-1" />
                      次の承認者を追加 (個別対応)
                    </button>
                    <div v-else class="bg-gray-50 border border-gray-200 rounded-lg p-3 shadow-inner">
                      <p class="text-xs font-bold text-gray-700 mb-2">追加する承認者を選択(現在の階層以上)</p>
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

            <!-- Right Panel: Image & Action (Occupies 7 columns) -->
            <div class="lg:col-span-7 flex flex-col gap-4">
              <!-- Image View -->
              <div class="bg-slate-200/50 rounded-xl overflow-hidden border border-gray-200 shadow-inner relative group flex-1 min-h-[400px]">
                <div class="absolute inset-0 flex items-center justify-center text-gray-400" v-if="!receipt.imageUrl">
                  <FileText class="w-16 h-16" />
                  <p class="ml-4 font-medium">画像データはありません</p>
                </div>
                <img v-else :src="receipt.imageUrl" class="absolute inset-0 w-full h-full object-contain" alt="Receipt Preview" />
              </div>

              <!-- Action Area -->
              <div v-if="receipt.status === 'pending'" class="bg-white border text-center relative border-gray-200 rounded-xl p-5 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]">
                <!-- Check if wait for another approver (simplified check for this mock/context) -->
                <!-- In a real app, we would check if the current user matches the current step's role -->
                <div>
                  <div class="mb-4">
                    <h3 class="text-sm font-bold text-gray-900 mb-2 text-left">承認用コメント（任意）</h3>
                    <textarea 
                      v-model="actionComment"
                      rows="2" 
                      class="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-3 border resize-none bg-gray-50/50" 
                      placeholder="確認しました。"
                    ></textarea>
                  </div>

                  <div class="flex gap-3">
                    <button 
                      @click="handleReject"
                      :disabled="isSubmitting"
                      class="flex-[1] bg-white hover:bg-rose-50 border border-rose-200 text-rose-600 hover:text-rose-700 font-semibold py-3 px-4 rounded-xl shadow-sm transition-colors text-sm disabled:opacity-50 ring-1 ring-inset ring-rose-100 flex items-center justify-center gap-2"
                    >
                      <XCircle class="w-4 h-4"/>
                      差戻し
                    </button>
                    <button 
                      @click="handleApprove"
                      :disabled="isSubmitting"
                      class="flex-[2] bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 px-4 rounded-xl shadow-md flex justify-center items-center transition-all hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 text-sm disabled:opacity-50 gap-2"
                    >
                      <svg v-if="isSubmitting" class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      <CheckCircle v-if="!isSubmitting" class="w-4 h-4" />
                      {{ isSubmitting ? '処理中...' : '承認する' }}
                    </button>
                  </div>
                  <p v-if="error" class="mt-2 text-xs text-red-600 font-medium">{{ error }}</p>
                </div>
              </div>
              
              <div v-else class="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center text-sm text-gray-500">
                この申請は現在アクションを必要としていません。
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>
</template>
