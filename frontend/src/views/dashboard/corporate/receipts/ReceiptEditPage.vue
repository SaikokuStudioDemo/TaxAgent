<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useSystemSettings } from '@/composables/useSystemSettings';
import { Save, Loader2, AlertCircle, ChevronLeft, LockKeyhole, Image, ExternalLink } from 'lucide-vue-next';
import { useReceipts } from '@/composables/useReceipts';
import { useProjects } from '@/composables/useProjects';
import { formatInputAmount, parseInputAmount } from '@/lib/utils/formatters';
import { api } from '@/lib/api';

const route = useRoute();
const router = useRouter();
const { getReceipt, updateReceipt } = useReceipts();
const { projects, fetchProjects } = useProjects();
const { taxRates, fetchTaxRates } = useSystemSettings();

const id = route.params.id as string;

// ─── 状態 ─────────────────────────────────────────────────────
const isLoading = ref(true);
const isSaving = ref(false);
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const isApproved = ref(false);
const attachmentUrl = ref<string | null>(null);
const hasStoragePath = ref(false);

const form = ref({
  date: '',
  payee: '',
  amount: 0,
  tax_rate: taxRates.value.standard,
  payment_method: '立替' as '立替' | '法人カード' | '銀行振込' | '現金',
  receipt_type: 'expense' as 'expense' | 'payment_proof',
  category: '',
  memo: '',
  project_id: '',
});

const categories = ['消耗品費', '交際費', '旅費交通費', '通信費', '会議費'];

// ─── データ取得 ────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([fetchProjects(), fetchTaxRates()]);
  const receipt = await getReceipt(id);
  if (!receipt) {
    loadError.value = '領収書データの取得に失敗しました';
    isLoading.value = false;
    return;
  }
  isApproved.value = ['approved', 'auto_approved'].includes(receipt.approval_status);
  attachmentUrl.value = receipt.attachments?.[0] ?? null;
  hasStoragePath.value = !!receipt.storage_path;
  form.value = {
    date: receipt.date ?? '',
    payee: receipt.payee ?? '',
    amount: receipt.amount ?? 0,
    tax_rate: receipt.tax_rate ?? taxRates.value.standard,
    payment_method: (receipt.payment_method as any) ?? '立替',
    receipt_type: (receipt.receipt_type ?? 'expense') as 'expense' | 'payment_proof',
    category: receipt.category ?? '',
    memo: (receipt as any).memo ?? '',
    project_id: receipt.project_id ?? '',
  };
  isLoading.value = false;
});

// ─── 金額入力ハンドラ ──────────────────────────────────────────
const amountDisplay = computed(() => formatInputAmount(form.value.amount));

const handleAmountInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const parsed = parseInputAmount(target.value);
  form.value.amount = parsed;
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
  const payload: Record<string, any> = {
    date: form.value.date,
    payee: form.value.payee,
    amount: form.value.amount,
    tax_rate: form.value.tax_rate,
    payment_method: form.value.payment_method,
    receipt_type: form.value.receipt_type,
    category: form.value.category,
    memo: form.value.memo || null,
    ...(form.value.project_id ? { project_id: form.value.project_id } : {}),
  };
  const result = await updateReceipt(id, payload);
  isSaving.value = false;
  if (result) {
    router.push('/dashboard/corporate/receipts/list');
  } else {
    saveError.value = '保存に失敗しました。再度お試しください。';
  }
};

const openFile = async () => {
  try {
    const res = await api.get<{ url: string }>(`/receipts/${id}/file-url`);
    window.open(res.url, '_blank');
  } catch {
    alert('ファイルの取得に失敗しました。');
  }
};
</script>

<template>
  <div class="space-y-6 max-w-2xl mx-auto">
    <!-- Header -->
    <div class="flex items-center gap-3">
      <button
        @click="router.push('/dashboard/corporate/receipts/list')"
        class="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <ChevronLeft :size="20" />
      </button>
      <div>
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">領収書編集</h1>
        <p class="text-sm text-gray-500 mt-0.5">登録済み領収書の内容を修正します</p>
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
      <p class="text-sm text-amber-600">承認済みの領収書は変更できません。</p>
      <button
        @click="router.push('/dashboard/corporate/receipts/list')"
        class="mt-2 px-6 py-2 bg-amber-100 text-amber-800 font-bold rounded-xl hover:bg-amber-200 transition-colors"
      >
        一覧に戻る
      </button>
    </div>

    <!-- Edit Form -->
    <div v-else class="space-y-6">
      <!-- Attachment Preview -->
      <div v-if="attachmentUrl || hasStoragePath" class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <div class="px-5 py-3 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Image :size="15" class="text-gray-400" />
            <span class="text-sm font-semibold text-gray-600">添付ファイル</span>
          </div>
          <button
            v-if="hasStoragePath"
            @click="openFile"
            class="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
          >
            <ExternalLink :size="13" />
            ファイルを表示する
          </button>
        </div>
        <div class="p-4 flex items-center justify-center bg-gray-50 min-h-[180px]">
          <img v-if="attachmentUrl" :src="attachmentUrl" alt="領収書画像" class="max-h-64 max-w-full object-contain rounded-lg shadow-sm border border-gray-200" />
          <span v-else class="text-sm text-gray-400">ファイルを表示するボタンから確認できます</span>
        </div>
      </div>

      <!-- Form Card -->
      <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-5">

        <!-- Save Error -->
        <div v-if="saveError" class="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle :size="16" />
          <span>{{ saveError }}</span>
        </div>

        <!-- 日付 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">日付</label>
          <input
            type="date"
            v-model="form.date"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          />
        </div>

        <!-- 支払先 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">支払先</label>
          <input
            type="text"
            v-model="form.payee"
            placeholder="例：株式会社○○"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          />
        </div>

        <!-- 金額 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">金額（税込）</label>
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
            <option value="立替">立替精算</option>
            <option value="法人カード">法人カード</option>
            <option value="銀行振込">銀行振込</option>
            <option value="現金">現金</option>
          </select>
        </div>

        <!-- 種別 -->
        <div>
          <label class="block text-sm font-semibold text-gray-700 mb-1.5">種別</label>
          <select
            v-model="form.receipt_type"
            class="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"
          >
            <option value="expense">経費精算</option>
            <option value="payment_proof">支払証明</option>
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
            @click="router.push('/dashboard/corporate/receipts/list')"
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
