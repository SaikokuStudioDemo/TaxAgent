<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import { XCircle, FileText, Plus, CheckCircle, Pen, Send, Mail, HandMetal } from 'lucide-vue-next';
import { useApprovals, type AddedStep } from '@/composables/useApprovals';
import { APPROVAL_LEVELS, getRankFromRoleId } from '@/lib/constants/mockData';
import ApprovalStepper from '@/components/approvals/ApprovalStepper.vue';
import { buildApprovalHistory } from '@/composables/useApprovalHistory';
import type { ApprovalHistory } from '@/lib/types/approvalTypes';
import { api } from '@/lib/api';

const props = defineProps<{
  show: boolean;
  /** Receipt | Invoice — id, current_step, approval_status, extra_approval_steps を持つこと */
  document: any;
  documentType: 'receipt' | 'received_invoice' | 'issued_invoice';
  title: string;
  subtitle?: string;
  /** 親で計算済みの画像URL */
  imageUrl: string;
  /** 承認アクションが必要な状態か */
  isPending: boolean;
  /** 承認ボタンのラベル（デフォルト: "承認する"） */
  approveLabel?: string;
  /** 編集ボタンを表示するか（呼び出し元がロール判定して渡す） */
  editable?: boolean;
  /** 編集可能なフィールド名リスト */
  editableFields?: string[];
  /** 保存処理（成功なら true を返す）。submit=true の場合は申請として保存 */
  onSave?: (data: Record<string, any>, submit?: boolean) => Promise<boolean>;
  /** 下書き状態か（「申請する」ボタンを編集エリアに追加表示） */
  isDraft?: boolean;
  /** 承認済みで未送付か（発行請求書のみ） */
  isPendingSend?: boolean;
  /** 送付処理（method: 'email' | 'hand'） */
  onSend?: (method: 'email' | 'hand') => Promise<boolean>;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'action-completed'): void;
  (e: 'step-added', updatedDoc: any): void;
}>();

// ─── 編集モード ──────────────────────────────────────
const isEditing = ref(false);
const editForm = reactive<Record<string, any>>({});
const isSaving = ref(false);

const startEdit = () => {
  Object.keys(editForm).forEach(k => { delete editForm[k]; });
  Object.assign(editForm, props.document ?? {});
  isEditing.value = true;
};

const cancelEdit = () => {
  isEditing.value = false;
};

const saveEdit = async (submit = false) => {
  if (!props.onSave) return;
  isSaving.value = true;
  try {
    const success = await props.onSave(editForm, submit);
    if (success) isEditing.value = false;
  } finally {
    isSaving.value = false;
  }
};

// モーダルが閉じたら編集状態をリセット
watch(() => props.show, (show) => { if (!show) isEditing.value = false; });

// ─── 承認アクション ──────────────────────────────────
const { submitApprovalAction, isSubmitting, error } = useApprovals();
const actionComment = ref('');
const isAddingApprover = ref(false);
const selectedExtraApproverId = ref('');

// ─── ローカル承認履歴 ────────────────────────────────
// document_type によって base 履歴の構築方法が異なる
const buildBaseHistory = (doc: any): ApprovalHistory[] => {
  if (!doc) return [];
  if (props.documentType === 'receipt') {
    return doc.approval_history ?? [];
  }
  // received_invoice / issued_invoice
  return buildApprovalHistory(
    doc.approval_steps ?? [],
    doc.approval_history ?? [],
    doc.approval_status,
  );
};

const localApprovalHistory = ref<ApprovalHistory[]>([]);

watch(
  () => props.document,
  (doc) => {
    if (!doc) { localApprovalHistory.value = []; return; }
    const base = buildBaseHistory(doc);
    const extras = (doc.extra_approval_steps ?? []).map((s: any, idx: number) => ({
      id: `ext_${idx}`,
      step: base.length + idx + 1,
      roleId: s.roleId,
      roleName: s.roleName,
      approverName: s.approverName,
      status: 'pending' as const,
    }));
    localApprovalHistory.value = [...base, ...extras];
  },
  { immediate: true },
);

// ─── 追加可能な承認者リスト ──────────────────────────
const availableApproversToAdd = computed(() => {
  const allLevels = APPROVAL_LEVELS.map(l => ({
    id: l.value, roleId: l.value, roleName: l.label, name: l.label, rank: getRankFromRoleId(l.value),
  }));
  if (!props.document || localApprovalHistory.value.length === 0) return allLevels;

  const currentHistory = localApprovalHistory.value[(props.document.current_step ?? 1) - 1];
  if (!currentHistory) return allLevels;

  const currentRank = getRankFromRoleId(currentHistory.roleId);
  return allLevels.filter(a => a.rank > currentRank);
});

// ─── PATCH エンドポイント ────────────────────────────
const patchPath = computed(() =>
  `/${props.documentType === 'receipt' ? 'receipts' : 'invoices'}/${props.document?.id}`,
);

// ─── アクション ─────────────────────────────────────
const handleClose = () => {
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
  actionComment.value = '';
  emit('close');
};

const handleAddApprover = async () => {
  if (!selectedExtraApproverId.value || !props.document) return;
  const level = APPROVAL_LEVELS.find(l => l.value === selectedExtraApproverId.value);
  const approver = level
    ? { id: level.value, roleId: level.value, roleName: level.label, name: level.label, rank: getRankFromRoleId(level.value) }
    : null;
  if (approver) {
    const newStep: ApprovalHistory = {
      id: 'h_ext_' + Date.now(),
      step: localApprovalHistory.value.length + 1,
      roleId: approver.roleId,
      roleName: approver.roleName,
      approverName: approver.name,
      status: 'pending',
    };
    localApprovalHistory.value = [...localApprovalHistory.value, newStep];

    const extraSteps = localApprovalHistory.value
      .filter(h => h.id?.startsWith('h_ext_') || h.id?.startsWith('ext_'))
      .map(h => ({ roleId: h.roleId, roleName: h.roleName, approverName: h.approverName }));
    try {
      const updated = await api.patch<any>(patchPath.value, { extra_approval_steps: extraSteps });
      emit('step-added', updated);
    } catch {
      localApprovalHistory.value = localApprovalHistory.value.slice(0, -1);
    }
  }
  isAddingApprover.value = false;
  selectedExtraApproverId.value = '';
};

const handleApprove = async () => {
  if (!props.document) return;

  const extSteps: AddedStep[] = localApprovalHistory.value
    .filter(h => h.id?.startsWith('h_ext_') || h.id?.startsWith('ext_'))
    .map(h => ({ roleId: h.roleId, roleName: h.roleName, approverName: h.approverName }));

  const success = await submitApprovalAction({
    documentType: props.documentType,
    documentId: props.document.id,
    action: 'approved',
    step: props.document.current_step,
    comment: actionComment.value,
    addedSteps: extSteps.length > 0 ? extSteps : undefined,
  });

  if (success) emit('action-completed');
};

const handleReject = async () => {
  if (!props.document) return;
  if (!actionComment.value.trim()) {
    alert('差戻しの場合はコメント（理由）を入力してください。');
    return;
  }

  const success = await submitApprovalAction({
    documentType: props.documentType,
    documentId: props.document.id,
    action: 'rejected',
    step: props.document.current_step,
    comment: actionComment.value,
  });

  if (success) emit('action-completed');
};

// ─── 送付アクション（発行請求書） ────────────────────────
const selectedSendMethod = ref<'email' | 'hand' | ''>('');
const isSending = ref(false);
const handleSend = async () => {
  if (!selectedSendMethod.value || !props.onSend) return;
  isSending.value = true;
  try {
    const success = await props.onSend(selectedSendMethod.value);
    if (success) {
      selectedSendMethod.value = '';
      emit('action-completed');
    }
  } finally {
    isSending.value = false;
  }
};
</script>

<template>
  <div
    v-if="show && document"
    class="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6 overflow-hidden"
    role="dialog"
    aria-modal="true"
  >
    <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity" @click="handleClose"></div>

    <div class="relative w-full max-w-6xl h-[95vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
      <div class="h-full flex flex-col w-full overflow-y-auto bg-slate-50 relative">

        <!-- Header -->
        <div class="px-6 py-4 bg-white border-b border-gray-200 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div class="min-w-0 mr-4">
            <h2 class="text-lg font-bold text-gray-900">{{ title }}</h2>
            <p v-if="subtitle" class="text-xs text-gray-500 mt-1" v-html="subtitle"></p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <!-- 編集ボタン（非編集中かつeditable時のみ） -->
            <button
              v-if="editable && !isEditing"
              @click="startEdit"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
            >
              <Pen class="h-3.5 w-3.5" /> 編集
            </button>
            <button
              @click="handleClose"
              class="rounded-full p-2 bg-gray-50 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <XCircle class="h-6 w-6" aria-hidden="true" />
            </button>
          </div>
        </div>

        <!-- Content Area -->
        <div class="flex-1 overflow-y-auto p-6">
          <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full min-h-[600px]">

            <!-- Left Panel: Document info + Approval flow -->
            <div class="lg:col-span-5 space-y-6 flex flex-col">

              <!-- ドキュメント固有フィールド（表示/編集 slot 切り替え） -->
              <template v-if="isEditing">
                <slot name="document-edit" :form="editForm" :editable-fields="editableFields ?? []" />
              </template>
              <template v-else>
                <slot name="document-info" />
              </template>

              <!-- 保存/キャンセルボタン（編集中のみ） -->
              <div v-if="isEditing" class="bg-white border border-gray-200 rounded-xl p-4 shadow-sm flex gap-2">
                <button
                  @click="cancelEdit"
                  class="flex-1 px-3 py-2.5 border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg text-sm font-semibold transition-colors"
                >
                  キャンセル
                </button>
                <button
                  @click="saveEdit(false)"
                  :disabled="isSaving"
                  class="flex-[2] bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-3 rounded-lg shadow-sm flex justify-center items-center transition-all text-sm disabled:opacity-50 gap-1.5"
                >
                  <svg v-if="isSaving" class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <CheckCircle v-else class="w-4 h-4" />
                  {{ isSaving ? '保存中...' : (isDraft ? '下書き保存' : '保存する') }}
                </button>
                <!-- 下書き時のみ「申請する」ボタンを追加 -->
                <button
                  v-if="isDraft"
                  @click="saveEdit(true)"
                  :disabled="isSaving"
                  class="flex-[2] bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2.5 px-3 rounded-lg shadow-sm flex justify-center items-center transition-all text-sm disabled:opacity-50 gap-1.5"
                >
                  <Send class="w-4 h-4" />
                  申請する
                </button>
              </div>

              <!-- 承認フロー（編集中は隠す） -->
              <div v-show="!isEditing" class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm flex-1">
                <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-3 mb-4">承認フロー (進捗状況)</h3>
                <div class="mt-4 overflow-hidden relative">
                  <ApprovalStepper
                    :document-type="documentType"
                    mode="status"
                    :history="localApprovalHistory"
                    :current-step="document.current_step"
                  />

                  <!-- 承認者追加 -->
                  <div v-if="isPending" class="mt-8 pt-4 border-t border-gray-100 border-dashed">
                    <button
                      v-if="!isAddingApprover"
                      @click="isAddingApprover = true"
                      class="text-xs font-medium text-blue-600 hover:text-blue-800 flex items-center bg-blue-50 px-2.5 py-1.5 rounded-lg border border-blue-100 hover:bg-blue-100 transition-colors"
                    >
                      <Plus class="w-3.5 h-3.5 mr-1" />
                      次の承認者を追加 (個別対応)
                    </button>
                    <div v-else class="bg-gray-50 border border-gray-200 rounded-lg p-3 shadow-inner">
                      <p class="text-xs font-bold text-gray-700 mb-2">追加する承認者を選択 (現在の階層以上)</p>
                      <div class="flex items-center gap-2">
                        <select
                          v-model="selectedExtraApproverId"
                          class="block w-full rounded-md border-gray-300 border shadow-sm focus:border-blue-500 focus:ring-blue-500 text-xs py-1.5 px-2 bg-white"
                        >
                          <option value="" disabled>選択してください</option>
                          <option v-for="user in availableApproversToAdd" :key="user.id" :value="user.id">
                            {{ user.roleName }} - {{ user.name }}
                          </option>
                        </select>
                        <button
                          @click="handleAddApprover"
                          :disabled="!selectedExtraApproverId"
                          class="bg-blue-600 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-blue-700 whitespace-nowrap disabled:opacity-50"
                        >追加</button>
                        <button
                          @click="isAddingApprover = false"
                          class="text-gray-500 hover:text-gray-700 px-2 py-1.5 rounded-md text-xs font-medium whitespace-nowrap bg-white border border-gray-200 shadow-sm"
                        >キャンセル</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right Panel: Image preview + Action -->
            <div class="lg:col-span-7 flex flex-col gap-4">

              <!-- 画像プレビュー -->
              <div class="bg-slate-200/50 rounded-xl overflow-hidden border border-gray-200 shadow-inner relative flex-1 min-h-[400px] flex items-center justify-center">
                <template v-if="imageUrl">
                  <iframe
                    v-if="imageUrl.includes('.pdf')"
                    :src="imageUrl"
                    class="w-full h-full border-none"
                  ></iframe>
                  <img
                    v-else
                    :src="imageUrl"
                    class="absolute inset-0 w-full h-full object-contain"
                    alt="Document Preview"
                  />
                </template>
                <div v-else class="text-center text-gray-400">
                  <FileText class="w-16 h-16 mx-auto mb-2 opacity-50" />
                  <p class="font-medium">プレビューデータはありません</p>
                </div>
              </div>

              <!-- 送付アクションエリア（発行請求書 承認済み・未送付） -->
              <div
                v-if="isPendingSend"
                class="bg-white border border-indigo-200 rounded-xl p-5 shadow-sm"
              >
                <h3 class="text-sm font-bold text-gray-900 mb-3">送付方法を選択してください</h3>
                <div class="flex gap-3 mb-4">
                  <button
                    @click="selectedSendMethod = 'email'"
                    :class="selectedSendMethod === 'email'
                      ? 'border-indigo-500 bg-indigo-50 text-indigo-700 ring-2 ring-indigo-300'
                      : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'"
                    class="flex-1 flex flex-col items-center gap-2 py-4 border-2 rounded-xl text-sm font-semibold transition-all"
                  >
                    <Mail class="w-5 h-5" />
                    メール送付
                  </button>
                  <button
                    @click="selectedSendMethod = 'hand'"
                    :class="selectedSendMethod === 'hand'
                      ? 'border-indigo-500 bg-indigo-50 text-indigo-700 ring-2 ring-indigo-300'
                      : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'"
                    class="flex-1 flex flex-col items-center gap-2 py-4 border-2 rounded-xl text-sm font-semibold transition-all"
                  >
                    <HandMetal class="w-5 h-5" />
                    手渡し・郵送
                  </button>
                </div>
                <button
                  @click="handleSend"
                  :disabled="!selectedSendMethod || isSending"
                  class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-4 rounded-xl shadow-md flex justify-center items-center gap-2 text-sm transition-all disabled:opacity-40"
                >
                  <svg v-if="isSending" class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <Send v-else class="w-4 h-4" />
                  {{ isSending ? '送付中...' : '送付を確定する' }}
                </button>
              </div>

              <!-- 承認アクションエリア（承認待ち状態） -->
              <div
                v-else-if="isPending"
                class="bg-white border border-gray-200 rounded-xl p-5 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)]"
              >
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
                    <XCircle class="w-4 h-4" />
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
                    {{ isSubmitting ? '処理中...' : (approveLabel ?? '承認する') }}
                  </button>
                </div>
                <p v-if="error" class="mt-2 text-xs text-red-600 font-medium">{{ error }}</p>
              </div>

              <div v-else class="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center text-sm text-gray-500">
                この書類は現在アクションを必要としていません。
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>
</template>
