<script setup lang="ts">
import { computed } from 'vue';
import { Building2 } from 'lucide-vue-next';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import { useInvoices, type Invoice } from '@/composables/useInvoices';
import { useAuth } from '@/composables/useAuth';
import DocumentDetailModal from '@/components/shared/DocumentDetailModal.vue';

const props = defineProps<{
  show: boolean;
  invoice: Invoice | null;
  document_type?: 'issued' | 'received';
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'action-completed'): void;
  (e: 'step-added', updatedInvoice: Invoice): void;
}>();

const docType = computed(() =>
  props.document_type === 'issued' ? 'issued_invoice' : 'received_invoice'
);
const title = computed(() =>
  `${props.document_type === 'issued' ? '発行' : '受領'}請求書詳細 : ${props.invoice?.id ?? ''}`
);
const subtitle = computed(() =>
  `${props.document_type === 'issued' ? '取引先' : '仕入先'}: <span class="font-medium text-gray-700">${props.invoice?.client_name ?? ''}</span>`
);
const imageUrl = computed(() =>
  (props.invoice?.attachments ?? [])[0] ?? props.invoice?.image_url ?? ''
);
const isPending = computed(() =>
  !['approved', 'auto_approved', 'rejected'].includes(props.invoice?.approval_status ?? '')
);
const approveLabel = computed(() =>
  props.document_type === 'issued' ? '承認して次へ' : '支払承認する'
);

// ─── 認証・ロール ─────────────────────────────────────
const { userProfile } = useAuth();

const userId = computed(() => userProfile.value?.data?._id ?? '');
const isAccountingRole = computed(() => {
  if (userProfile.value?.type === 'corporate') return true;
  const role = userProfile.value?.data?.role ?? 'staff';
  return ['admin', 'manager', 'accounting'].includes(role);
});
const isOwner = computed(() => !!props.invoice && props.invoice.created_by === userId.value);

// ─── 編集権限 ─────────────────────────────────────────
const editable = computed(() => {
  if (!props.invoice) return false;
  const status = props.invoice.approval_status;
  if (isOwner.value && ['pending_approval', 'rejected', 'draft'].includes(status)) return true;
  if (isAccountingRole.value && !['approved', 'auto_approved'].includes(status)) return true;
  return false;
});

const editableFields = computed((): string[] => {
  if (!props.invoice) return [];
  if (isOwner.value) return ['total_amount', 'client_name', 'issue_date', 'due_date', 'category', 'payment_method', 'memo'];
  if (isAccountingRole.value) return ['category', 'payment_method'];
  return [];
});

// ─── 保存処理 ─────────────────────────────────────────
const { updateInvoice } = useInvoices();

const onSave = async (data: Record<string, any>): Promise<boolean> => {
  if (!props.invoice) return false;
  const payload: Record<string, any> = {};
  for (const field of editableFields.value) {
    if (data[field] !== undefined) payload[field] = data[field];
  }
  // 差戻し後の再提出
  if (props.invoice.approval_status === 'rejected') {
    payload.approval_status = 'pending_approval';
  }
  const result = await updateInvoice(props.invoice.id, payload);
  if (result) {
    emit('action-completed');
    return true;
  }
  return false;
};
</script>

<template>
  <DocumentDetailModal
    :show="show"
    :document="invoice"
    :document-type="docType"
    :title="title"
    :subtitle="subtitle"
    :image-url="imageUrl"
    :is-pending="isPending"
    :approve-label="approveLabel"
    :editable="editable"
    :editable-fields="editableFields"
    :on-save="onSave"
    @close="emit('close')"
    @action-completed="emit('action-completed')"
    @step-added="(doc) => emit('step-added', doc as Invoice)"
  >
    <!-- 表示モード -->
    <template #document-info>
      <div v-if="invoice" class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
        <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-3">請求書詳細内容</h3>
        <dl class="grid grid-cols-1 gap-x-4 gap-y-4 text-sm">
          <div class="flex justify-between items-center bg-gray-50 p-3 rounded-lg border border-gray-100">
            <span class="text-gray-600 font-medium">合計請求金額</span>
            <span class="text-2xl font-bold tracking-tight">¥{{ formatAmount(invoice.total_amount) }}<span class="text-[11px] font-normal text-gray-500 ml-1">(税込)</span></span>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">{{ document_type === 'issued' ? '発行日' : '発行元記載日' }}</dt>
              <dd class="font-medium text-gray-900">{{ invoice.issue_date }}</dd>
            </div>
            <div>
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5" :class="document_type === 'received' ? 'text-red-600' : ''">支払期限</dt>
              <dd class="font-bold" :class="document_type === 'received' ? 'text-red-700' : 'text-gray-900'">{{ invoice.due_date }}</dd>
            </div>
            <div>
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">勘定科目</dt>
              <dd class="font-medium text-orange-700 bg-orange-50 border border-orange-200 px-2 py-0.5 rounded text-xs inline-block">{{ invoice.line_items?.[0]?.category ?? '未分類' }}</dd>
            </div>
            <div>
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">支払方法</dt>
              <dd class="font-medium text-gray-900">{{ invoice.payment_method ?? '請求書払い' }}</dd>
            </div>
            <div class="col-span-2">
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">{{ document_type === 'issued' ? '件名 / 取引内容' : '仕入元' }}</dt>
              <dd class="font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded inline-block w-full flex items-center gap-2">
                <Building2 class="w-3 h-3 text-gray-400" />
                {{ document_type === 'issued' ? (invoice.invoice_number ?? invoice.client_name ?? '請求書') : invoice.client_name }}
              </dd>
            </div>
          </div>
          <div>
            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 mt-2">社内用メモ</dt>
            <dd class="font-medium text-gray-900 break-words bg-yellow-50/50 p-2 rounded-lg border border-yellow-100/50 text-xs">{{ invoice.memo ?? 'なし' }}</dd>
          </div>
        </dl>
      </div>
    </template>

    <!-- 編集モード -->
    <template #document-edit="{ form, editableFields: fields }">
      <div class="bg-white p-5 border border-blue-200 rounded-xl shadow-sm ring-1 ring-blue-100">
        <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-4 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-blue-500 inline-block"></span>
          請求書を編集
          <span v-if="invoice?.approval_status === 'rejected'" class="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">保存時に再申請されます</span>
        </h3>
        <div class="space-y-4">
          <!-- 合計金額 -->
          <div v-if="fields.includes('total_amount')">
            <label class="block text-xs font-medium text-gray-500 mb-1">合計請求金額 (税込)</label>
            <input v-model.number="form.total_amount" type="number" min="0"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 取引先 -->
          <div v-if="fields.includes('client_name')">
            <label class="block text-xs font-medium text-gray-500 mb-1">{{ document_type === 'issued' ? '取引先' : '仕入元' }}</label>
            <input v-model="form.client_name" type="text"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 発行日・支払期限 -->
          <div class="grid grid-cols-2 gap-4">
            <div v-if="fields.includes('issue_date')">
              <label class="block text-xs font-medium text-gray-500 mb-1">{{ document_type === 'issued' ? '発行日' : '発行元記載日' }}</label>
              <input v-model="form.issue_date" type="date"
                class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
            <div v-if="fields.includes('due_date')">
              <label class="block text-xs font-medium text-gray-500 mb-1">支払期限</label>
              <input v-model="form.due_date" type="date"
                class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
          </div>
          <!-- 勘定科目・支払方法 -->
          <div class="grid grid-cols-2 gap-4">
            <div v-if="fields.includes('category')">
              <label class="block text-xs font-medium text-gray-500 mb-1">勘定科目</label>
              <select v-model="form.category"
                class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white">
                <option>売上高</option>
                <option>仕入高</option>
                <option>外注費</option>
                <option>消耗品費</option>
                <option>交際費</option>
                <option>会議費</option>
                <option>通信費</option>
                <option>旅費交通費</option>
                <option>広告宣伝費</option>
              </select>
            </div>
            <div v-if="fields.includes('payment_method')">
              <label class="block text-xs font-medium text-gray-500 mb-1">支払方法</label>
              <select v-model="form.payment_method"
                class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white">
                <option>請求書払い</option>
                <option>銀行振込</option>
                <option>法人カード</option>
                <option>現金</option>
              </select>
            </div>
          </div>
          <!-- メモ -->
          <div v-if="fields.includes('memo')">
            <label class="block text-xs font-medium text-gray-500 mb-1">社内用メモ</label>
            <textarea v-model="form.memo" rows="2"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"></textarea>
          </div>
        </div>
      </div>
    </template>
  </DocumentDetailModal>
</template>
