<script setup lang="ts">
import { ref } from 'vue';
import { Download, Building2 } from 'lucide-vue-next';
import { useAuth } from '@/composables/useAuth';

const { getToken } = useAuth();

const fiscalPeriod = ref('');
const isDownloading = ref(false);
const error = ref<string | null>(null);

const handleDownload = async () => {
  isDownloading.value = true;
  error.value = null;
  try {
    const token = await getToken();
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    const params = new URLSearchParams(
      fiscalPeriod.value ? { fiscal_period: fiscalPeriod.value } : {}
    );
    const url = `${apiUrl}/exports/zengin${params.toString() ? '?' + params : ''}`;
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail ?? 'ダウンロード失敗');
    }
    const blob = await res.blob();
    const filename = `zengin_${fiscalPeriod.value || 'all'}.txt`;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (e: any) {
    error.value = e.message ?? '全銀データのダウンロードに失敗しました';
  } finally {
    isDownloading.value = false;
  }
};
</script>

<template>
  <div class="p-6 max-w-2xl mx-auto">
    <div class="flex items-center gap-3 mb-6">
      <Building2 class="text-indigo-600" :size="24" />
      <div>
        <h1 class="text-xl font-bold text-slate-800">全銀データ出力</h1>
        <p class="text-sm text-slate-500">承認済み・未消込の受領請求書を全銀フォーマットで出力します</p>
      </div>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="px-6 py-5 bg-amber-50 border-b border-amber-100">
        <p class="text-xs text-amber-700">
          出力対象：承認済みかつ未消込の受領請求書。文字コード：Shift-JIS（1行120バイト固定長）。
        </p>
      </div>

      <div class="px-6 py-5">
        <label class="text-sm font-semibold text-slate-700 block mb-2">
          会計期間（省略時：全期間）
        </label>
        <input
          v-model="fiscalPeriod"
          type="month"
          class="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none w-44"
        />
      </div>

      <!-- エラー -->
      <div v-if="error" class="mx-6 mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
        {{ error }}
      </div>

      <!-- ダウンロードボタン -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end">
        <button
          @click="handleDownload"
          :disabled="isDownloading"
          class="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          <Download :size="15" />
          {{ isDownloading ? 'ダウンロード中...' : '全銀データをダウンロード' }}
        </button>
      </div>
    </div>
  </div>
</template>
