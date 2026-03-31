<script setup lang="ts">
import { computed } from 'vue';
import { Plus } from 'lucide-vue-next';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';
import { useReceipts, type Receipt } from '@/composables/useReceipts';
import { useAuth } from '@/composables/useAuth';
import DocumentDetailModal from '@/components/shared/DocumentDetailModal.vue';

const props = defineProps<{
  show: boolean;
  receipt: Receipt | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'action-completed'): void;
  (e: 'step-added', updatedReceipt: Receipt): void;
}>();

// ─── 認証・ロール ─────────────────────────────────────
const { userProfile } = useAuth();

const userId = computed(() => userProfile.value?.data?._id ?? '');
const isAccountingRole = computed(() => {
  if (userProfile.value?.type === 'corporate') return true; // 法人管理者
  const role = userProfile.value?.data?.role ?? 'staff';
  return ['admin', 'manager', 'accounting'].includes(role);
});
const isOwner = computed(() => !!props.receipt && props.receipt.submitted_by === userId.value);

// ─── 表示用 ──────────────────────────────────────────
const title = computed(() => `申請詳細 : ${props.receipt?.id ?? ''}`);
const subtitle = computed(() =>
  `提出者: <span class="font-medium text-gray-700">${props.receipt?.submitter_name ?? props.receipt?.submitted_by ?? '不明'}</span>`
);
const imageUrl = computed(() => props.receipt?.image_url ?? '');
const isPending = computed(() =>
  !['approved', 'auto_approved', 'rejected'].includes(props.receipt?.approval_status ?? '')
);

// ─── 編集権限 ─────────────────────────────────────────
const editable = computed(() => {
  if (!props.receipt) return false;
  const status = props.receipt.approval_status;
  if (isOwner.value && ['pending_approval', 'rejected', 'draft'].includes(status)) return true;
  if (isAccountingRole.value && !['approved', 'auto_approved'].includes(status)) return true;
  return false;
});

const editableFields = computed((): string[] => {
  if (!props.receipt) return [];
  if (isOwner.value) return ['amount', 'tax_rate', 'payee', 'category', 'payment_method', 'memo', 'date'];
  if (isAccountingRole.value) return ['category', 'tax_rate'];
  return [];
});

// ─── 保存処理 ─────────────────────────────────────────
const { updateReceipt } = useReceipts();

const onSave = async (data: Record<string, any>): Promise<boolean> => {
  if (!props.receipt) return false;
  // editableFields のみ送信
  const payload: Record<string, any> = {};
  for (const field of editableFields.value) {
    if (data[field] !== undefined) payload[field] = data[field];
  }
  // 差戻し後の再提出: ステータスを pending_approval に戻す
  if (props.receipt.approval_status === 'rejected') {
    payload.approval_status = 'pending_approval';
  }
  const result = await updateReceipt(props.receipt.id, payload);
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
    :document="receipt"
    document-type="receipt"
    :title="title"
    :subtitle="subtitle"
    :image-url="imageUrl"
    :is-pending="isPending"
    :editable="editable"
    :editable-fields="editableFields"
    :on-save="onSave"
    @close="emit('close')"
    @action-completed="emit('action-completed')"
    @step-added="(doc) => emit('step-added', doc as Receipt)"
  >
    <!-- 表示モード -->
    <template #document-info>
      <div v-if="receipt" class="bg-white p-5 border border-gray-200 rounded-xl shadow-sm">
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
              <dd class="font-medium text-gray-900">{{ receipt.tax_rate ?? 10 }}%</dd>
            </div>
            <div>
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">勘定科目</dt>
              <dd class="font-medium text-orange-700 bg-orange-50 border border-orange-200 px-2 py-0.5 rounded text-xs inline-block">{{ receipt.category }}</dd>
            </div>
            <div>
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">決済手段</dt>
              <dd class="font-medium text-gray-900">{{ receipt.payment_method }}</dd>
            </div>
            <div class="col-span-2">
              <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5">発行元 / 店舗</dt>
              <dd class="font-medium text-gray-900 bg-gray-50 px-2 py-1 rounded inline-block">{{ receipt.payee }}</dd>
            </div>
          </div>
          <div>
            <dt class="text-gray-500 text-[11px] tracking-wide mb-0.5 mt-2">メモ・備考</dt>
            <dd class="font-medium text-gray-900 break-words bg-yellow-50/50 p-2 rounded-lg border border-yellow-100/50 text-xs">{{ receipt.memo ?? '' }}</dd>
          </div>
          <div v-if="receipt.project_name" class="pt-2 border-t border-gray-100 mt-2">
            <dt class="text-purple-600 text-[11px] tracking-wide flex items-center gap-1 mb-1"><Plus class="w-3 h-3" />紐付けプロジェクト</dt>
            <dd class="font-medium text-purple-900 bg-purple-50 px-2 py-1 rounded inline-block text-xs border border-purple-100 w-full truncate">
              {{ receipt.project_name }}
            </dd>
          </div>
        </dl>
      </div>
    </template>

    <!-- 編集モード -->
    <template #document-edit="{ form, editableFields: fields }">
      <div class="bg-white p-5 border border-blue-200 rounded-xl shadow-sm ring-1 ring-blue-100">
        <h3 class="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2 mb-4 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-blue-500 inline-block"></span>
          領収書を編集
          <span v-if="receipt?.approval_status === 'rejected'" class="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">保存時に再申請されます</span>
        </h3>
        <div class="space-y-4">
          <!-- 合計金額 -->
          <div v-if="fields.includes('amount')">
            <label class="block text-xs font-medium text-gray-500 mb-1">合計金額 (税込)</label>
            <input v-model.number="form.amount" type="number" min="0"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 申請日 -->
          <div v-if="fields.includes('date')">
            <label class="block text-xs font-medium text-gray-500 mb-1">申請日</label>
            <input v-model="form.date" type="date"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- 税率・勘定科目 -->
          <div class="grid grid-cols-2 gap-4">
            <div v-if="fields.includes('tax_rate')">
              <label class="block text-xs font-medium text-gray-500 mb-1">適用税率</label>
              <select v-model.number="form.tax_rate"
                class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white">
                <option :value="10">10%</option>
                <option :value="8">8%（軽減税率）</option>
              </select>
            </div>
            <div v-if="fields.includes('category')">
              <label class="block text-xs font-medium text-gray-500 mb-1">勘定科目</label>
              <select v-model="form.category"
                class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white">
                <option>消耗品費</option>
                <option>交際費</option>
                <option>会議費</option>
                <option>通信費</option>
                <option>旅費交通費</option>
                <option>新聞図書費</option>
              </select>
            </div>
          </div>
          <!-- 決済手段 -->
          <div v-if="fields.includes('payment_method')">
            <label class="block text-xs font-medium text-gray-500 mb-1">決済手段</label>
            <select v-model="form.payment_method"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white">
              <option>法人カード</option>
              <option>立替</option>
              <option>銀行振込</option>
              <option>現金</option>
            </select>
          </div>
          <!-- 発行元 -->
          <div v-if="fields.includes('payee')">
            <label class="block text-xs font-medium text-gray-500 mb-1">発行元 / 店舗</label>
            <input v-model="form.payee" type="text"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
          </div>
          <!-- メモ -->
          <div v-if="fields.includes('memo')">
            <label class="block text-xs font-medium text-gray-500 mb-1">メモ・備考</label>
            <textarea v-model="form.memo" rows="2"
              class="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"></textarea>
          </div>
        </div>
      </div>
    </template>
  </DocumentDetailModal>
</template>
