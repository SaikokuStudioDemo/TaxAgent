<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '@/lib/api';
import { AlertTriangle, CheckCircle, Settings, ExternalLink, RefreshCw } from 'lucide-vue-next';

const router = useRouter();

interface CorporateAlert {
  corporate_id: string;
  company_name: string;
  pending_receipts: number;
  pending_invoices: number;
  unmatched_transactions: number;
  rejected_stale_count: number;
  approval_delay_count: number;
  total_alerts: number;
  has_alerts: boolean;
}

const items = ref<CorporateAlert[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);

const alertCount = computed(() => items.value.filter(i => i.has_alerts).length);

const fetchAlerts = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.get<{ data: CorporateAlert[] }>('/admin/corporate-alerts');
    items.value = res.data;
  } catch (e: any) {
    error.value = e.message ?? 'アラート情報の取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

const goToSettings = (id: string) => {
  router.push({ name: 'dashboard-tax-firm-alert-settings', params: { id } });
};

onMounted(fetchAlerts);
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto">
    <!-- ヘッダー -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-slate-800">アラート一覧</h1>
        <p class="text-sm text-slate-500 mt-1">
          配下法人の未処理状況・アラート状態を確認できます
        </p>
      </div>
      <button
        @click="fetchAlerts"
        :disabled="isLoading"
        class="flex items-center gap-2 px-4 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50"
      >
        <RefreshCw :size="15" :class="{ 'animate-spin': isLoading }" />
        更新
      </button>
    </div>

    <!-- サマリーバナー -->
    <div v-if="!isLoading && items.length > 0" class="mb-6 flex gap-4">
      <div class="bg-red-50 border border-red-200 rounded-xl px-5 py-3 flex items-center gap-3">
        <AlertTriangle class="text-red-500 shrink-0" :size="20" />
        <div>
          <p class="text-sm font-semibold text-red-700">要対応</p>
          <p class="text-2xl font-bold text-red-600">{{ alertCount }}<span class="text-sm font-normal ml-1">法人</span></p>
        </div>
      </div>
      <div class="bg-slate-50 border border-slate-200 rounded-xl px-5 py-3 flex items-center gap-3">
        <CheckCircle class="text-slate-400 shrink-0" :size="20" />
        <div>
          <p class="text-sm font-semibold text-slate-600">管理中</p>
          <p class="text-2xl font-bold text-slate-700">{{ items.length }}<span class="text-sm font-normal ml-1">法人</span></p>
        </div>
      </div>
    </div>

    <!-- エラー -->
    <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 mb-4 text-sm">
      {{ error }}
    </div>

    <!-- スケルトンローディング -->
    <div v-if="isLoading" class="space-y-3">
      <div
        v-for="i in 4" :key="i"
        class="h-24 bg-slate-100 rounded-xl animate-pulse"
      />
    </div>

    <!-- データなし -->
    <div v-else-if="!isLoading && items.length === 0" class="text-center py-16 text-slate-400">
      <CheckCircle :size="40" class="mx-auto mb-3 opacity-40" />
      <p class="text-sm">配下の法人が見つかりません</p>
    </div>

    <!-- 法人カード一覧 -->
    <div v-else class="space-y-3">
      <div
        v-for="item in items"
        :key="item.corporate_id"
        :class="[
          'bg-white rounded-xl border p-5 transition-shadow hover:shadow-md',
          item.has_alerts ? 'border-red-200' : 'border-slate-200',
        ]"
      >
        <div class="flex items-start justify-between gap-4">
          <!-- 左：法人情報 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-3">
              <h3 class="font-semibold text-slate-800 truncate">{{ item.company_name || '（名称未設定）' }}</h3>
              <span
                v-if="item.has_alerts"
                class="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700"
              >
                <AlertTriangle :size="11" />
                要対応
              </span>
              <span
                v-else
                class="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700"
              >
                <CheckCircle :size="11" />
                正常
              </span>
            </div>

            <!-- 件数バッジ群 -->
            <div class="flex flex-wrap gap-2">
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-amber-50 text-amber-700 border border-amber-100">
                未承認領収書: <strong>{{ item.pending_receipts }}</strong>
              </span>
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-amber-50 text-amber-700 border border-amber-100">
                未承認請求書: <strong>{{ item.pending_invoices }}</strong>
              </span>
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-slate-50 text-slate-600 border border-slate-100">
                未消込取引: <strong>{{ item.unmatched_transactions }}</strong>
              </span>
              <span
                v-if="item.rejected_stale_count > 0"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-red-50 text-red-700 border border-red-100"
              >
                差し戻し放置: <strong>{{ item.rejected_stale_count }}</strong>
              </span>
              <span
                v-if="item.approval_delay_count > 0"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs bg-red-50 text-red-700 border border-red-100"
              >
                承認遅延: <strong>{{ item.approval_delay_count }}</strong>
              </span>
            </div>
          </div>

          <!-- 右：アクションボタン -->
          <div class="flex flex-col gap-2 shrink-0">
            <button
              @click="goToSettings(item.corporate_id)"
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition-colors"
            >
              <Settings :size="13" />
              閾値設定
            </button>
            <RouterLink
              :to="`/dashboard/corporate`"
              class="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-50 text-slate-600 rounded-lg hover:bg-slate-100 transition-colors"
            >
              <ExternalLink :size="13" />
              消込画面
            </RouterLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
