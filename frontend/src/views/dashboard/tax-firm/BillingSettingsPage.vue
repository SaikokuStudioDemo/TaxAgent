<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '@/lib/api';
import { ArrowLeft, Save, ToggleLeft, ToggleRight } from 'lucide-vue-next';

const route = useRoute();
const router = useRouter();

// :id は顧客の firebase_uid
const targetFirebaseUid = route.params.id as string;

interface BillingSettings {
  tax_firm_id: string;
  target_corporate_id: string;
  corporate_unit_price: number;
  user_unit_price: number;
  is_active: boolean;
}

const settings = ref<BillingSettings>({
  tax_firm_id: '',
  target_corporate_id: targetFirebaseUid,
  corporate_unit_price: 0,
  user_unit_price: 0,
  is_active: false,
});

// 従業員数（月額試算に使用）
const employeeCount = ref(0);
const companyName = ref('');

const isLoading = ref(false);
const isSaving = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);

// 月額合計の試算
const estimatedMonthly = computed(() => {
  if (!settings.value.is_active) return 0;
  return (
    settings.value.corporate_unit_price +
    settings.value.user_unit_price * employeeCount.value
  );
});

const fetchSettings = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.get<BillingSettings>(`/billing-settings/${targetFirebaseUid}`);
    settings.value = res;
  } catch (e: any) {
    error.value = e.message ?? '設定の取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

// 顧客情報（従業員数）は clients から取得
const fetchClientInfo = async () => {
  try {
    const res = await api.get<{ data: any[] }>('/users/clients');
    const client = res.data.find((c: any) => c.firebase_uid === targetFirebaseUid);
    if (client) {
      employeeCount.value = client.employeeCount ?? 0;
      companyName.value = client.companyName ?? '';
    }
  } catch {
    // 取得失敗は無視（従業員数0で試算）
  }
};

const handleSave = async () => {
  isSaving.value = true;
  error.value = null;
  successMessage.value = null;
  try {
    await api.put(`/billing-settings/${targetFirebaseUid}`, {
      corporate_unit_price: settings.value.corporate_unit_price,
      user_unit_price: settings.value.user_unit_price,
      is_active: settings.value.is_active,
    });
    successMessage.value = '課金設定を保存しました';
    setTimeout(() => { successMessage.value = null; }, 3000);
  } catch (e: any) {
    error.value = e.message ?? '保存に失敗しました';
  } finally {
    isSaving.value = false;
  }
};

onMounted(async () => {
  await Promise.all([fetchSettings(), fetchClientInfo()]);
});
</script>

<template>
  <div class="p-6 max-w-xl mx-auto">
    <!-- ヘッダー -->
    <div class="flex items-center gap-3 mb-6">
      <button
        @click="router.back()"
        class="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
      >
        <ArrowLeft :size="18" />
      </button>
      <div>
        <h1 class="text-xl font-bold text-slate-800">課金設定</h1>
        <p class="text-sm text-slate-500">{{ companyName || targetFirebaseUid }}</p>
      </div>
    </div>

    <!-- エラー -->
    <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-5 text-sm">
      {{ error }}
    </div>

    <!-- 成功トースト -->
    <Transition name="toast">
      <div
        v-if="successMessage"
        class="fixed top-5 right-5 z-50 bg-green-600 text-white px-5 py-3 rounded-xl shadow-lg text-sm font-medium"
      >
        {{ successMessage }}
      </div>
    </Transition>

    <!-- スケルトン -->
    <div v-if="isLoading" class="space-y-4">
      <div v-for="i in 3" :key="i" class="h-16 bg-slate-100 rounded-xl animate-pulse" />
    </div>

    <!-- フォーム -->
    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <!-- 課金有効フラグ -->
      <div class="px-6 py-5 flex items-center justify-between border-b border-slate-100">
        <div>
          <p class="text-sm font-semibold text-slate-800">課金を有効にする</p>
          <p class="text-xs text-slate-500 mt-0.5">無効の場合、料金は発生しません</p>
        </div>
        <button
          @click="settings.is_active = !settings.is_active"
          class="transition-colors"
          :aria-pressed="settings.is_active"
        >
          <ToggleRight
            v-if="settings.is_active"
            :size="36"
            class="text-indigo-600"
          />
          <ToggleLeft
            v-else
            :size="36"
            class="text-slate-300"
          />
        </button>
      </div>

      <!-- 料金入力（is_active=false はグレーアウト） -->
      <div :class="{ 'opacity-40 pointer-events-none': !settings.is_active }">
        <!-- 法人単位料金 -->
        <div class="px-6 py-5 border-b border-slate-100">
          <label class="text-sm font-medium text-slate-700 block mb-2">
            法人単位 月額料金（円）
          </label>
          <p class="text-xs text-slate-500 mb-3">法人ごとに固定でかかる月額費用</p>
          <div class="flex items-center gap-2">
            <input
              v-model.number="settings.corporate_unit_price"
              type="number"
              min="0"
              class="w-40 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <span class="text-sm text-slate-500">円 / 月</span>
          </div>
        </div>

        <!-- ユーザー単位料金 -->
        <div class="px-6 py-5 border-b border-slate-100">
          <label class="text-sm font-medium text-slate-700 block mb-2">
            ユーザー単位 月額料金（円）
          </label>
          <p class="text-xs text-slate-500 mb-3">登録ユーザー数 × この金額が月額に追加されます</p>
          <div class="flex items-center gap-2">
            <input
              v-model.number="settings.user_unit_price"
              type="number"
              min="0"
              class="w-40 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <span class="text-sm text-slate-500">円 / ユーザー / 月</span>
          </div>
        </div>
      </div>

      <!-- 月額合計試算 -->
      <div class="px-6 py-5 bg-slate-50 border-b border-slate-100">
        <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">月額合計（試算）</p>
        <div class="flex items-baseline gap-2">
          <span class="text-2xl font-bold text-slate-800">
            ¥{{ estimatedMonthly.toLocaleString() }}
          </span>
          <span class="text-xs text-slate-500">/ 月</span>
        </div>
        <p class="text-xs text-slate-400 mt-1">
          ¥{{ settings.corporate_unit_price.toLocaleString() }}（法人）
          + ¥{{ settings.user_unit_price.toLocaleString() }}
          × {{ employeeCount }}名 = ¥{{ estimatedMonthly.toLocaleString() }}
        </p>
      </div>

      <!-- 保存ボタン -->
      <div class="px-6 py-4 flex justify-end">
        <button
          @click="handleSave"
          :disabled="isSaving"
          class="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          <Save :size="15" />
          {{ isSaving ? '保存中...' : '保存する' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
