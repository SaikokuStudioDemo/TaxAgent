<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Calculator, AlertCircle } from 'lucide-vue-next';
import { api } from '@/lib/api';

const fiscalYear = ref(new Date().getFullYear());
const reportMonth = ref<number | null>(null);
const report = ref<any>(null);
const isLoading = ref(false);
const error = ref<string | null>(null);

const MONTHS = Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` }));

const fetchReport = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const params: Record<string, string> = { fiscal_year: String(fiscalYear.value) };
    if (reportMonth.value) params.month = String(reportMonth.value);
    const qs = new URLSearchParams(params);
    report.value = await api.get<any>(`/exports/tax-report?${qs}`);
  } catch (e: any) {
    error.value = e.message ?? 'データの取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

const fmt = (n: number) => n.toLocaleString();

onMounted(fetchReport);
</script>

<template>
  <div class="p-6 max-w-3xl mx-auto space-y-6">
    <!-- ヘッダー -->
    <div class="flex items-center gap-3">
      <Calculator class="text-indigo-600" :size="24" />
      <div>
        <h1 class="text-xl font-bold text-slate-800">税務申告サポート</h1>
        <p class="text-sm text-slate-500">消費税集計データ（参考値）</p>
      </div>
    </div>

    <!-- 絞り込み -->
    <div class="flex flex-wrap items-end gap-4">
      <div>
        <label class="text-xs font-semibold text-slate-600 block mb-1">年度</label>
        <input v-model.number="fiscalYear" type="number" min="2020" max="2099"
          class="border border-slate-300 rounded-lg px-3 py-2 text-sm w-24 focus:ring-2 focus:ring-indigo-500 outline-none" />
      </div>
      <div>
        <label class="text-xs font-semibold text-slate-600 block mb-1">月（省略時：年間）</label>
        <select v-model="reportMonth"
          class="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none">
          <option :value="null">年間</option>
          <option v-for="m in MONTHS" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
      <button @click="fetchReport" :disabled="isLoading"
        class="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
        集計する
      </button>
    </div>

    <!-- エラー -->
    <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{{ error }}</div>

    <!-- レポート -->
    <div v-if="report && !isLoading" class="space-y-6">

      <!-- 売上側テーブル -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="px-5 py-3 bg-indigo-50 border-b border-indigo-100">
          <h2 class="text-sm font-bold text-indigo-800">売上側（課税売上）</h2>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-xs text-slate-500 border-b">
            <tr>
              <th class="px-4 py-2 text-left">区分</th>
              <th class="px-4 py-2 text-right">金額</th>
              <th class="px-4 py-2 text-right">消費税額</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr>
              <td class="px-4 py-3">課税売上（10%）</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.sales.taxable_10) }}</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.sales.consumption_tax_10) }}</td>
            </tr>
            <tr>
              <td class="px-4 py-3">課税売上（8%・軽減）</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.sales.taxable_8) }}</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.sales.consumption_tax_8) }}</td>
            </tr>
            <tr>
              <td class="px-4 py-3 text-slate-500">非課税・対象外</td>
              <td class="px-4 py-3 text-right text-slate-500">¥{{ fmt(report.sales.tax_exempt) }}</td>
              <td class="px-4 py-3 text-right text-slate-400">—</td>
            </tr>
            <tr class="font-semibold bg-slate-50">
              <td class="px-4 py-3">合計</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.sales.total) }}</td>
              <td class="px-4 py-3 text-right text-indigo-700">¥{{ fmt(report.sales.total_consumption_tax) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 仕入側テーブル -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="px-5 py-3 bg-green-50 border-b border-green-100">
          <h2 class="text-sm font-bold text-green-800">仕入側（課税仕入・仕入税額控除）</h2>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-xs text-slate-500 border-b">
            <tr>
              <th class="px-4 py-2 text-left">区分</th>
              <th class="px-4 py-2 text-right">金額</th>
              <th class="px-4 py-2 text-right">消費税額</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr>
              <td class="px-4 py-3">課税仕入（10%）</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.purchases.taxable_10) }}</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.purchases.consumption_tax_10) }}</td>
            </tr>
            <tr>
              <td class="px-4 py-3">課税仕入（8%・軽減）</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.purchases.taxable_8) }}</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.purchases.consumption_tax_8) }}</td>
            </tr>
            <tr>
              <td class="px-4 py-3 text-slate-500">対象外</td>
              <td class="px-4 py-3 text-right text-slate-500">¥{{ fmt(report.purchases.tax_exempt) }}</td>
              <td class="px-4 py-3 text-right text-slate-400">—</td>
            </tr>
            <tr class="font-semibold bg-slate-50">
              <td class="px-4 py-3">合計</td>
              <td class="px-4 py-3 text-right">¥{{ fmt(report.purchases.total) }}</td>
              <td class="px-4 py-3 text-right text-green-700">¥{{ fmt(report.purchases.total_consumption_tax) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 納付税額サマリー -->
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-3">
        <h2 class="text-sm font-bold text-slate-700 mb-4">納付税額サマリー</h2>
        <div class="flex justify-between text-sm">
          <span class="text-slate-600">売上消費税額</span>
          <span class="font-medium">¥{{ fmt(report.sales.total_consumption_tax) }}</span>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-slate-600">仕入税額控除</span>
          <span class="font-medium text-green-600">− ¥{{ fmt(report.purchases.deductible_tax) }}</span>
        </div>
        <div class="border-t border-slate-200 pt-3 flex justify-between">
          <span class="font-bold text-slate-800">
            {{ report.summary.has_refund ? '還付税額' : '納付税額' }}
          </span>
          <span :class="['text-xl font-bold', report.summary.has_refund ? 'text-blue-600' : 'text-red-600']">
            ¥{{ fmt(report.summary.has_refund ? report.summary.tax_refund : report.summary.tax_payable) }}
          </span>
        </div>
        <div v-if="report.summary.has_refund"
          class="flex items-center gap-2 p-3 bg-blue-50 rounded-lg text-sm text-blue-700">
          <AlertCircle :size="14" />
          仕入税額が売上税額を超えています。消費税の還付申告が可能です。
        </div>
      </div>

      <!-- 注意書き -->
      <div class="flex items-start gap-2 p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-700">
        <AlertCircle :size="14" class="shrink-0 mt-0.5" />
        <p>この集計はシステムに登録されたデータを元にした参考値です。実際の申告には税理士にご確認ください。</p>
      </div>
    </div>

    <!-- ローディング -->
    <div v-if="isLoading" class="space-y-4">
      <div v-for="i in 3" :key="i" class="h-48 bg-slate-100 rounded-2xl animate-pulse" />
    </div>
  </div>
</template>
