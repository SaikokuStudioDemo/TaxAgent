<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '@/lib/api';
import { ArrowLeft, Save } from 'lucide-vue-next';

const route = useRoute();
const router = useRouter();

const corporateId = route.params.id as string;

interface AlertsConfig {
  corporate_id: string;
  rejected_stale_days: number;
  no_attachment_days: number;
  unreconciled_days: number;
  approval_delay_days: number;
}

const config = ref<AlertsConfig>({
  corporate_id: corporateId,
  rejected_stale_days: 3,
  no_attachment_days: 3,
  unreconciled_days: 7,
  approval_delay_days: 3,
});

const isLoading = ref(false);
const isSaving = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const FIELD_LABELS: Record<string, string> = {
  rejected_stale_days: '差し戻し放置アラート（日）',
  no_attachment_days: '証憑未提出アラート（日）',
  unreconciled_days: '消込滞留アラート（日）',
  approval_delay_days: '承認遅延アラート（日）',
};

const FIELD_DESCRIPTIONS: Record<string, string> = {
  rejected_stale_days: '差し戻し後 N 日以上更新がない書類にアラートを発生させます',
  no_attachment_days: '証憑ファイルなしで N 日以上放置された領収書にアラートを発生させます',
  unreconciled_days: '承認済みで N 日以上消込されていない書類にアラートを発生させます',
  approval_delay_days: '承認待ちで N 日以上止まっている書類にアラートを発生させます',
};

const fetchConfig = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.get<AlertsConfig>(`/alerts-config/${corporateId}`);
    config.value = res;
  } catch (e: any) {
    error.value = e.message ?? '設定の取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

const handleSave = async () => {
  isSaving.value = true;
  error.value = null;
  successMessage.value = null;
  try {
    await api.put(`/alerts-config/${corporateId}`, {
      rejected_stale_days: config.value.rejected_stale_days,
      no_attachment_days: config.value.no_attachment_days,
      unreconciled_days: config.value.unreconciled_days,
      approval_delay_days: config.value.approval_delay_days,
    });
    successMessage.value = '設定を保存しました';
    setTimeout(() => { successMessage.value = null; }, 3000);
  } catch (e: any) {
    error.value = e.message ?? '保存に失敗しました';
  } finally {
    isSaving.value = false;
  }
};

const configFields = [
  'rejected_stale_days',
  'no_attachment_days',
  'unreconciled_days',
  'approval_delay_days',
] as const;

onMounted(fetchConfig);
</script>

<template>
  <div class="p-6 max-w-2xl mx-auto">
    <!-- ヘッダー -->
    <div class="flex items-center gap-3 mb-6">
      <button
        @click="router.back()"
        class="p-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
      >
        <ArrowLeft :size="18" />
      </button>
      <div>
        <h1 class="text-xl font-bold text-slate-800">アラート閾値設定</h1>
        <p class="text-sm text-slate-500">法人ID: {{ corporateId }}</p>
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

    <!-- ローディング -->
    <div v-if="isLoading" class="space-y-4">
      <div v-for="i in 4" :key="i" class="h-20 bg-slate-100 rounded-xl animate-pulse" />
    </div>

    <!-- フォーム -->
    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100 bg-slate-50">
        <p class="text-sm text-slate-600">
          各アラートが発生するまでの日数を設定します（最小: 1日）。
        </p>
      </div>

      <div class="divide-y divide-slate-100">
        <div
          v-for="field in configFields"
          :key="field"
          class="px-6 py-5 flex items-center justify-between gap-6"
        >
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-slate-800">{{ FIELD_LABELS[field] }}</p>
            <p class="text-xs text-slate-500 mt-0.5">{{ FIELD_DESCRIPTIONS[field] }}</p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <input
              v-model.number="config[field]"
              type="number"
              :min="1"
              class="w-20 text-center border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <span class="text-sm text-slate-500">日</span>
          </div>
        </div>
      </div>

      <!-- 保存ボタン -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end">
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
.toast-enter-active, .toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from, .toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
