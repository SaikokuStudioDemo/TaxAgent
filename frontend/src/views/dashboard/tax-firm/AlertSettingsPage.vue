<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { api } from '@/lib/api';
import { ArrowLeft, Save } from 'lucide-vue-next';

const route = useRoute();
const router = useRouter();

const corporateId = route.params.id as string;

interface EmailEnabled {
  rejected_stale_alert: boolean;
  no_attachment_alert: boolean;
  unreconciled_alert: boolean;
  approval_delay_alert: boolean;
  tax_advisor_escalation_alert: boolean;
}

interface AlertsConfig {
  corporate_id: string;
  rejected_stale_days: number;
  no_attachment_days: number;
  unreconciled_days: number;
  approval_delay_days: number;
  tax_advisor_escalation_days: number;
  email_enabled: EmailEnabled;
}

const config = ref<AlertsConfig>({
  corporate_id: corporateId,
  rejected_stale_days: 3,
  no_attachment_days: 3,
  unreconciled_days: 7,
  approval_delay_days: 3,
  tax_advisor_escalation_days: 3,
  email_enabled: {
    rejected_stale_alert: false,
    no_attachment_alert: false,
    unreconciled_alert: false,
    approval_delay_alert: false,
    tax_advisor_escalation_alert: false,
  },
});

const isLoading = ref(false);
const isSaving = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const configFields = [
  { key: 'rejected_stale_days',         emailKey: 'rejected_stale_alert',         label: '差し戻し放置',        desc: '差し戻し後 N 日以上更新がない書類にアラートを発生させます' },
  { key: 'no_attachment_days',          emailKey: 'no_attachment_alert',          label: '証憑未提出',          desc: '証憑ファイルなしで N 日以上放置された領収書にアラートを発生させます' },
  { key: 'unreconciled_days',           emailKey: 'unreconciled_alert',           label: '消込滞留',            desc: '承認済みで N 日以上消込されていない書類にアラートを発生させます' },
  { key: 'approval_delay_days',         emailKey: 'approval_delay_alert',         label: '承認フロー遅延',       desc: '承認待ちで N 日以上止まっている書類にアラートを発生させます' },
  { key: 'tax_advisor_escalation_days', emailKey: 'tax_advisor_escalation_alert', label: '税理士エスカレーション', desc: '税理士へのエスカレーションが N 日以上保留の場合にアラートを発生させます' },
] as const;

const fetchConfig = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.get<AlertsConfig>(`/alerts-config/${corporateId}`);
    config.value = {
      ...config.value,
      ...res,
      email_enabled: { ...config.value.email_enabled, ...(res.email_enabled ?? {}) },
    };
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
      rejected_stale_days:         config.value.rejected_stale_days,
      no_attachment_days:          config.value.no_attachment_days,
      unreconciled_days:           config.value.unreconciled_days,
      approval_delay_days:         config.value.approval_delay_days,
      tax_advisor_escalation_days: config.value.tax_advisor_escalation_days,
      email_enabled:               config.value.email_enabled,
    });
    successMessage.value = '設定を保存しました';
    setTimeout(() => { successMessage.value = null; }, 3000);
  } catch (e: any) {
    error.value = e.message ?? '保存に失敗しました';
  } finally {
    isSaving.value = false;
  }
};

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
      <div v-for="i in 5" :key="i" class="h-20 bg-slate-100 rounded-xl animate-pulse" />
    </div>

    <!-- フォーム -->
    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-100 bg-slate-50">
        <p class="text-sm text-slate-600">
          各アラートが発生するまでの日数を設定します（最小: 1日）。
        </p>
      </div>

      <!-- ヘッダー行 -->
      <div class="grid grid-cols-[1fr_auto_auto] gap-4 px-6 py-2 bg-slate-50 border-b border-slate-100 text-xs font-semibold text-slate-500 uppercase tracking-wider">
        <span>アラート種別</span>
        <span class="w-28 text-center">閾値（日）</span>
        <span class="w-24 text-center">メール通知</span>
      </div>

      <div class="divide-y divide-slate-100">
        <div
          v-for="field in configFields"
          :key="field.key"
          class="grid grid-cols-[1fr_auto_auto] gap-4 px-6 py-4 items-center"
        >
          <div class="min-w-0">
            <p class="text-sm font-medium text-slate-800">{{ field.label }}</p>
            <p class="text-xs text-slate-500 mt-0.5">{{ field.desc }}</p>
          </div>
          <div class="w-28 flex items-center justify-center gap-1.5 shrink-0">
            <input
              v-model.number="(config as any)[field.key]"
              type="number"
              :min="1"
              class="w-16 text-center border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <span class="text-sm text-slate-500">日</span>
          </div>
          <!-- メール通知トグル -->
          <div class="w-24 flex justify-center shrink-0">
            <button
              type="button"
              @click="config.email_enabled[field.emailKey] = !config.email_enabled[field.emailKey]"
              :class="[
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
                config.email_enabled[field.emailKey] ? 'bg-indigo-600' : 'bg-slate-300'
              ]"
              :title="config.email_enabled[field.emailKey] ? 'メール通知 ON' : 'メール通知 OFF'"
            >
              <span
                :class="[
                  'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                  config.email_enabled[field.emailKey] ? 'translate-x-6' : 'translate-x-1'
                ]"
              />
            </button>
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
