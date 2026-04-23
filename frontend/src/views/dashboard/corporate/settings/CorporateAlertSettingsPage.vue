<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { api } from '@/lib/api';
import { isAccountingOrAbove } from '@/composables/useAuth';
import { Save } from 'lucide-vue-next';

interface EmailEnabled {
  rejected_stale_alert: boolean;
  no_attachment_alert: boolean;
  unreconciled_alert: boolean;
  approval_delay_alert: boolean;
  tax_advisor_escalation_alert: boolean;
}

interface AlertsConfigSelf {
  corporate_id: string;
  rejected_stale_days: number;
  no_attachment_days: number;
  unreconciled_days: number;
  approval_delay_days: number;
  tax_advisor_escalation_days: number;
  email_enabled: EmailEnabled;
}

const DEFAULT_EMAIL_ENABLED: EmailEnabled = {
  rejected_stale_alert: false,
  no_attachment_alert: false,
  unreconciled_alert: false,
  approval_delay_alert: false,
  tax_advisor_escalation_alert: false,
};

const config = ref<AlertsConfigSelf | null>(null);
const emailEnabled = ref<EmailEnabled>({ ...DEFAULT_EMAIL_ENABLED });

const isLoading = ref(true);
const isSaving = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const canEdit = computed(() => isAccountingOrAbove.value);

const alertFields = [
  { emailKey: 'rejected_stale_alert'         as const, label: '差し戻し放置',         desc: '差し戻し後 N 日以上放置された書類' },
  { emailKey: 'no_attachment_alert'          as const, label: '証憑未提出',            desc: '証憑ファイルなしで N 日以上放置された領収書' },
  { emailKey: 'unreconciled_alert'           as const, label: '消込滞留',              desc: '承認済みで N 日以上消込されていない書類' },
  { emailKey: 'approval_delay_alert'         as const, label: '承認フロー遅延',         desc: '承認待ちで N 日以上止まっている書類' },
  { emailKey: 'tax_advisor_escalation_alert' as const, label: '税理士エスカレーション', desc: '税理士へのエスカレーションが長期保留の書類' },
];

const fetchConfig = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.get<AlertsConfigSelf>('/alerts-config/self');
    config.value = res;
    emailEnabled.value = { ...DEFAULT_EMAIL_ENABLED, ...(res.email_enabled ?? {}) };
  } catch (e: any) {
    error.value = e.message ?? '設定の取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

const handleSave = async () => {
  if (!canEdit.value) return;
  isSaving.value = true;
  error.value = null;
  successMessage.value = null;
  try {
    await api.put('/alerts-config/self', { email_enabled: emailEnabled.value });
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
    <div class="mb-6">
      <h1 class="text-xl font-bold text-slate-800">アラートメール通知設定</h1>
      <p class="text-sm text-slate-500 mt-1">
        アラートが発生したときにメールを受け取るかどうかを設定します。
        <span v-if="!canEdit" class="text-amber-600 ml-1">（閲覧のみ：経理担当者以上が編集可能）</span>
      </p>
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
    <div v-if="isLoading" class="space-y-3">
      <div v-for="i in 5" :key="i" class="h-16 bg-slate-100 rounded-xl animate-pulse" />
    </div>

    <!-- 設定フォーム -->
    <div v-else class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <!-- 閾値表示（読み取り専用）-->
      <div v-if="config" class="px-6 py-3 bg-slate-50 border-b border-slate-100">
        <p class="text-xs text-slate-500">
          閾値（日数）は税理士法人が管理しています。メール通知の ON/OFF のみ設定できます。
        </p>
      </div>

      <!-- アラート別トグル -->
      <div class="divide-y divide-slate-100">
        <div
          v-for="field in alertFields"
          :key="field.emailKey"
          class="flex items-center justify-between gap-4 px-6 py-4"
        >
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-slate-800">{{ field.label }}</p>
            <p class="text-xs text-slate-500 mt-0.5">{{ field.desc }}</p>
          </div>

          <!-- トグル -->
          <button
            type="button"
            :disabled="!canEdit"
            @click="if (canEdit) emailEnabled[field.emailKey] = !emailEnabled[field.emailKey]"
            :class="[
              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none',
              canEdit ? 'focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 cursor-pointer' : 'cursor-not-allowed opacity-60',
              emailEnabled[field.emailKey] ? 'bg-indigo-600' : 'bg-slate-300',
            ]"
            :title="emailEnabled[field.emailKey] ? 'メール通知 ON' : 'メール通知 OFF'"
          >
            <span
              :class="[
                'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                emailEnabled[field.emailKey] ? 'translate-x-6' : 'translate-x-1',
              ]"
            />
          </button>

          <span class="text-xs font-medium w-8 text-right" :class="emailEnabled[field.emailKey] ? 'text-indigo-600' : 'text-slate-400'">
            {{ emailEnabled[field.emailKey] ? 'ON' : 'OFF' }}
          </span>
        </div>
      </div>

      <!-- 保存ボタン（editing 可能な場合のみ） -->
      <div v-if="canEdit" class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end">
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
