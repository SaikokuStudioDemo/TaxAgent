<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Save, Loader2, AlertCircle, ChevronLeft, LockKeyhole, Image } from 'lucide-vue-next';
import { useInvoices } from '@/composables/useInvoices';
import { useProjects } from '@/composables/useProjects';
import { formatInputAmount, parseInputAmount } from '@/lib/utils/formatters';

const route = useRoute();
const router = useRouter();
const { getInvoice, updateInvoice } = useInvoices();
const { projects, fetchProjects } = useProjects();

const id = route.params.id as string;

// ─── 状態 ─────────────────────────────────────────────────────
const isLoading = ref(true);
const isSaving = ref(false);
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const isApproved = ref(false);
const attachmentUrl = ref<string | null>(null);

const form = ref({
  issue_date: '',
  due_date: '',
  client_name: '',
  total_amount: 0,
  tax_rate: 10,
  payment_method: '銀行振込' as string,
  category: '仕入',
  memo: '',
  project_id: '',
});

const categories = ['仕入', '消耗品費', '交際費', '旅費交通費', '通信費', '会議費', '外注費'];

// ─── データ取得 ────────────────────────────────────────────────
onMounted(async () => {
  await fetchProjects();
  const invoice = await getInvoice(id);
  if (!invoice) {
    loadError.value = '請求書データの取得に失敗しました';
    isLoading.value = false;
    return;
  }
  isApproved.value = ['approved', 'auto_approved'].includes(invoice.approval_status);
  attachmentUrl.value = invoice.attachments?.[0] ?? null;
  form.value = {
    issue_date: invoice.issue_date ?? '',
    due_date: invoice.due_date ?? '',
    client_name: invoice.vendor_name || invoice.client_name || '',
    total_amount: invoice.total_amount ?? 0,
    tax_rate: invoice.line_items?.[0]?.tax_rate ?? 10,
    payment_method: invoice.payment_method ?? '銀行振込',
    category: invoice.line_items?.[0]?.category ?? '仕入',
    memo: (invoice as any).memo ?? '',
    project_id: invoice.project_id ?? '',
  };
  isLoading.value = false;
});

// ─── 金額入力ハンドラ ──────────────────────────────────────────
const amountDisplay = computed(() => formatInputAmount(form.value.total_amount));

const handleAmountInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const parsed = parseInputAmount(target.value);
  form.value.total_amount = parsed;
  const formatted = formatInputAmount(parsed);
  const cursor = target.selectionStart ?? 0;
  const diff = formatted.length - target.value.length;
  target.value = formatted;
  target.setSelectionRange(Math.max(0, cursor + diff), Math.max(0, cursor + diff));
};

// ─── 保存 ─────────────────────────────────────────────────────
const handleSave = async () => {
  saveError.value = null;
  isSaving.value = true;
  const subtotal = Math.round(form.value.total_amount / (1 + form.value.tax_rate / 100));
  const tax_amount = form.value.total_amount - subtotal;
  const payload: Record<string, any> = {
    issue_date: form.value.issue_date,
    due_date: form.value.due_date,
    client_name: form.value.client_name,
    vendor_name: form.value.client_name,
    total_amount: form.value.total_amount,
    subtotal,
    tax_amount,
    payment_method: form.value.payment_method,
    memo: form.value.memo || null,
    line_items: [{
      description: '請求書',
      category: form.value.category,
      amount: form.value.total_amount,
      tax_rate: form.value.tax_rate,
    }],
    ...(form.value.project_id ? { project_id: form.value.project_id } : {}),
  };
  const result = await updateInvoice(id, payload);
  isSaving.value = false;
  if (result) {
    router.push('/dashboard/corporate/invoices/received-list');
  } else {
    saveError.value = '保存に失敗しました。再度お試しください。';
  }
};
</script>

<template>
  <div class="space-y-6 max-w-2xl mx-auto">
    <!-- Header -->
    <div class="flex items-center gap-3">
      <button
        @click="router.push('/dashboard/corporate/invoices/received-list')"
        class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <ChevronLeft :size="20" />
      </button>
      <div>
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">受取請求書編集</h1>
        <p class="text-sm text-gray-500 mt-0.5">登録済み受取請求書の内容を修正します</p>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center py-24">
      <Loader2 :size="32" class="animate-spin text-indigo-500" />
    </div>

    <!-- Load Error -->
    <div v-else-if="loadError" class="bg-red-50 border border-red-200 rounded-xl p-6 flex items-center gap-3 text-red-700">
      <AlertCircle :size="20" />
      <span>{{ loadError }}</span>
    </div>

    <!-- Approved: locked -->
    <div v-else-if="isApproved" class="bg-amber-50 border border-amber-200 rounded-xl p-8 flex flex-col items-center text-center gap-3">
      <LockKeyhole :size="36" class="text-amber-400" />
      <p class="font-bold text-amber-800 text-lg">このデータは承認済みのため編集できません</p>
      <p class="text-sm text-amber-600">承認済みの受取請求書は変更できません。</p>
      <button
        @click="router.push('/dashboard/corporate/invoices/received-list')"
        class="mt-2 px-6 py-2 bg-amber-100 text-amber-800 font-bold rounded-xl hover:bg-amber-200 transition-colors"
      >
        一覧に戻る
      </button>
    </div>

    <!-- Edit Form -->
    <div v-else class="space-y-6">
      <!-- Attachment Preview -->
      <div v-if="attachmentUrl" class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <div class="px-5 py-3 border-b border-gray-100 bg-gray-50/50 flex items-center gap-2">
          <Image :size="15" class="text-gray-400" />
          <span class="text-sm font-semibold text-gray-600">添付ファイル</span>
        </div>
        <div class="p-4 flex items-center justify-center bg-gray-50 min-h-[180px]">
          <img :src="attachmentUrl" alt="請求書画像" class="max-h-64 max-w-full object-contain rounded-lg shadow-sm border border-gray-200" />
        </div>
      </div>

      <!-- Form Card -->
      <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-5">

        <!-- Save Error -->
        <div v-if="saveError" class="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle :size="16" />
          <span>{{ saveError }}</span>
        </div>

        <!-- 発行日 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">発行日</label>
          <input
            type="date"
            v-model="form.issue_date"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          />
        </div>

        <!-- 支払期日 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">支払期日</label>
          <input
            type="date"
            v-model="form.due_date"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          />
        </div>

        <!-- 発行元 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">発行元</label>
          <input
            type="text"
            v-model="form.client_name"
            placeholder="例：株式会社○○"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          />
        </div>

        <!-- 請求金額 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">請求金額（税込）</label>
          <div class="relative">
            <span class="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 font-bold">¥</span>
            <input
              type="text"
              :value="amountDisplay"
              @input="handleAmountInput"
              class="w-full border border-gray-200 rounded-xl pl-8 pr-4 py-2.5 text-sm text-right font-bold focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>

        <!-- 税率 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">税率</label>
          <select
            v-model="form.tax_rate"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          >
            <option :value="10">10%</option>
            <option :value="8">8%（軽減税率）</option>
            <option :value="0">対象外</option>
          </select>
        </div>

        <!-- 支払方法 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">支払方法</label>
          <select
            v-model="form.payment_method"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          >
            <option value="銀行振込">銀行振込</option>
            <option value="法人カード">法人カード</option>
            <option value="立替">立替精算</option>
          </select>
        </div>

        <!-- カテゴリ -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">カテゴリ</label>
          <select
            v-model="form.category"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          >
            <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
          </select>
        </div>

        <!-- プロジェクト -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">プロジェクト</label>
          <select
            v-model="form.project_id"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors text-gray-700"
          >
            <option value="">指定なし</option>
            <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}</option>
          </select>
        </div>

        <!-- メモ -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">メモ <span class="font-normal text-gray-400">（任意）</span></label>
          <textarea
            v-model="form.memo"
            rows="3"
            placeholder="備考・補足事項など"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors resize-none"
          />
        </div>

        <!-- Actions -->
        <div class="flex items-center justify-end gap-3 pt-2 border-t border-gray-100">
          <button
            @click="router.push('/dashboard/corporate/invoices/received-list')"
            class="px-5 py-2.5 text-sm font-bold text-gray-600 bg-gray-100 rounded-xl hover:bg-gray-200 transition-colors"
          >
            キャンセル
          </button>
          <button
            @click="handleSave"
            :disabled="isSaving"
            class="flex items-center gap-2 px-6 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            <Loader2 v-if="isSaving" :size="16" class="animate-spin" />
            <Save v-else :size="16" />
            {{ isSaving ? '保存中...' : '変更を保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
