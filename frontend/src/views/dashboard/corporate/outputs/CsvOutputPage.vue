<script setup lang="ts">
import { ref } from 'vue';
import { Download, FileText } from 'lucide-vue-next';
import { useAuth } from '@/composables/useAuth';

const { getToken } = useAuth();

const formatType = ref<'freee' | 'mf' | 'yayoi'>('freee');
const docType = ref<'receipt' | 'invoice' | 'all'>('all');
const fiscalPeriod = ref('');
const isDownloading = ref(false);
const error = ref<string | null>(null);

const FORMAT_LABELS = {
  freee: 'freee（フリー）',
  mf: 'マネーフォワード',
  yayoi: '弥生会計',
};
const DOC_TYPE_LABELS = {
  receipt: '領収書のみ',
  invoice: '請求書のみ',
  all: '全て（領収書＋請求書）',
};

const handleDownload = async () => {
  isDownloading.value = true;
  error.value = null;
  try {
    const token = await getToken();
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    const params = new URLSearchParams({
      format_type: formatType.value,
      doc_type: docType.value,
      ...(fiscalPeriod.value && { fiscal_period: fiscalPeriod.value }),
    });
    const res = await fetch(`${apiUrl}/exports/csv?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail ?? 'ダウンロード失敗');
    }
    const blob = await res.blob();
    const filename = `export_${formatType.value}_${fiscalPeriod.value || 'all'}.csv`;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (e: any) {
    error.value = e.message ?? 'ダウンロードに失敗しました';
  } finally {
    isDownloading.value = false;
  }
};
</script>

<template>
  <div class="p-6 max-w-2xl mx-auto">
    <div class="flex items-center gap-3 mb-6">
      <FileText class="text-indigo-600" :size="24" />
      <div>
        <h1 class="text-xl font-bold text-slate-800">CSV出力</h1>
        <p class="text-sm text-slate-500">会計ソフト用CSVをダウンロードします</p>
      </div>
    </div>

    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div class="divide-y divide-slate-100">

        <!-- フォーマット選択 -->
        <div class="px-6 py-5">
          <label class="text-sm font-semibold text-slate-700 block mb-3">出力フォーマット</label>
          <div class="flex flex-wrap gap-3">
            <label
              v-for="(label, key) in FORMAT_LABELS" :key="key"
              class="flex items-center gap-2 cursor-pointer"
            >
              <input type="radio" v-model="formatType" :value="key" class="accent-indigo-600" />
              <span class="text-sm text-slate-700">{{ label }}</span>
            </label>
          </div>
        </div>

        <!-- 対象種別 -->
        <div class="px-6 py-5">
          <label class="text-sm font-semibold text-slate-700 block mb-3">出力対象</label>
          <div class="flex flex-wrap gap-3">
            <label
              v-for="(label, key) in DOC_TYPE_LABELS" :key="key"
              class="flex items-center gap-2 cursor-pointer"
            >
              <input type="radio" v-model="docType" :value="key" class="accent-indigo-600" />
              <span class="text-sm text-slate-700">{{ label }}</span>
            </label>
          </div>
        </div>

        <!-- 会計期間 -->
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
          {{ isDownloading ? 'ダウンロード中...' : 'CSVをダウンロード' }}
        </button>
      </div>
    </div>
  </div>
</template>
