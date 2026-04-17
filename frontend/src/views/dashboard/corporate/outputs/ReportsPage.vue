<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { BarChart3, Plus, Edit2, Trash2, AlertCircle } from 'lucide-vue-next';
import { api } from '@/lib/api';
import { useAuth } from '@/composables/useAuth';

const { isAdmin } = useAuth();

// ── レポート用 ──────────────────────────────────────────────────────────────
const fiscalYear = ref(new Date().getFullYear());
const reportMonth = ref<number | null>(null);
const report = ref<any>(null);
const isReportLoading = ref(false);
const reportError = ref<string | null>(null);

const fetchReport = async () => {
  isReportLoading.value = true;
  reportError.value = null;
  try {
    const params: any = { fiscal_year: fiscalYear.value };
    if (reportMonth.value) params.month = reportMonth.value;
    const qs = new URLSearchParams(Object.fromEntries(
      Object.entries(params).map(([k, v]) => [k, String(v)])
    ));
    report.value = await api.get<any>(`/budgets/report?${qs}`);
  } catch (e: any) {
    reportError.value = e.message ?? 'レポートの取得に失敗しました';
  } finally {
    isReportLoading.value = false;
  }
};

const achievementClass = (rate: number | null) => {
  if (rate === null) return 'text-slate-400';
  if (rate >= 100) return 'text-red-600 font-semibold';
  if (rate >= 80) return 'text-amber-600';
  return 'text-green-600';
};

// ── 予算登録用（管理者のみ） ──────────────────────────────────────────────
const budgets = ref<any[]>([]);
const isBudgetsLoading = ref(false);
const budgetForm = ref({ fiscal_year: new Date().getFullYear(), month: 1, account_subject: '', amount: 0 });
const editingId = ref<string | null>(null);
const isSaving = ref(false);
const budgetError = ref<string | null>(null);

const fetchBudgets = async () => {
  if (!isAdmin.value) return;
  isBudgetsLoading.value = true;
  try {
    const data = await api.get<any[]>(`/budgets?fiscal_year=${fiscalYear.value}`);
    budgets.value = data;
  } catch { } finally {
    isBudgetsLoading.value = false;
  }
};

const handleSave = async () => {
  isSaving.value = true;
  budgetError.value = null;
  try {
    if (editingId.value) {
      await api.put(`/budgets/${editingId.value}`, {
        amount: budgetForm.value.amount,
        account_subject: budgetForm.value.account_subject,
      });
    } else {
      await api.post('/budgets', budgetForm.value);
    }
    editingId.value = null;
    budgetForm.value = { fiscal_year: fiscalYear.value, month: 1, account_subject: '', amount: 0 };
    await fetchBudgets();
    await fetchReport();
  } catch (e: any) {
    budgetError.value = e.message;
  } finally {
    isSaving.value = false;
  }
};

const handleEdit = (b: any) => {
  editingId.value = b.id;
  budgetForm.value = { fiscal_year: b.fiscal_year, month: b.month, account_subject: b.account_subject, amount: b.amount };
};

const handleDelete = async (id: string) => {
  if (!confirm('この予算を削除しますか？')) return;
  try {
    await api.delete(`/budgets/${id}`);
    await fetchBudgets();
    await fetchReport();
  } catch (e: any) {
    budgetError.value = e.message;
  }
};

onMounted(async () => {
  await Promise.all([fetchReport(), fetchBudgets()]);
});

const MONTHS = Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` }));
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-8">
    <!-- ヘッダー -->
    <div class="flex items-center gap-3">
      <BarChart3 class="text-indigo-600" :size="24" />
      <div>
        <h1 class="text-xl font-bold text-slate-800">予算対比レポート</h1>
        <p class="text-sm text-slate-500">予算と実績の差異を確認します</p>
      </div>
    </div>

    <!-- 絞り込みコントロール -->
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
      <button @click="fetchReport" :disabled="isReportLoading"
        class="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
        表示
      </button>
    </div>

    <!-- エラー -->
    <div v-if="reportError" class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{{ reportError }}</div>

    <!-- 予算未登録バナー -->
    <div v-if="report && !report.has_budget"
      class="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
      <AlertCircle :size="16" />
      予算が未登録のため実績のみ表示しています
    </div>

    <!-- レポートテーブル -->
    <div v-if="report" class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 text-xs font-semibold text-slate-600 border-b border-slate-200">
          <tr>
            <th class="px-4 py-3 text-left">勘定科目</th>
            <th class="px-4 py-3 text-right">予算</th>
            <th class="px-4 py-3 text-right">実績</th>
            <th class="px-4 py-3 text-right">差額</th>
            <th class="px-4 py-3 text-right">達成率</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-if="isReportLoading">
            <td colspan="5" class="px-4 py-8 text-center text-slate-400">読み込み中...</td>
          </tr>
          <tr v-else-if="report.rows.length === 0">
            <td colspan="5" class="px-4 py-8 text-center text-slate-400">データがありません</td>
          </tr>
          <tr v-for="row in report.rows" :key="row.account_subject" class="hover:bg-slate-50/50">
            <td class="px-4 py-3 font-medium text-slate-800">
              {{ row.account_subject }}
              <span v-if="!row.has_budget" class="ml-2 text-xs text-slate-400">（予算未設定）</span>
            </td>
            <td class="px-4 py-3 text-right text-slate-600">
              {{ row.has_budget ? row.budget_amount.toLocaleString() : '—' }}
            </td>
            <td class="px-4 py-3 text-right text-slate-800 font-medium">{{ row.actual_amount.toLocaleString() }}</td>
            <td class="px-4 py-3 text-right" :class="row.difference >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ row.difference >= 0 ? '+' : '' }}{{ row.difference.toLocaleString() }}
            </td>
            <td class="px-4 py-3 text-right" :class="achievementClass(row.achievement_rate)">
              {{ row.achievement_rate !== null ? row.achievement_rate + '%' : '—' }}
            </td>
          </tr>
        </tbody>
        <tfoot class="bg-slate-50 border-t-2 border-slate-200">
          <tr class="font-bold">
            <td class="px-4 py-3 text-slate-800">合計</td>
            <td class="px-4 py-3 text-right">{{ report.total.budget_amount.toLocaleString() }}</td>
            <td class="px-4 py-3 text-right">{{ report.total.actual_amount.toLocaleString() }}</td>
            <td class="px-4 py-3 text-right" :class="report.total.difference >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ report.total.difference >= 0 ? '+' : '' }}{{ report.total.difference.toLocaleString() }}
            </td>
            <td class="px-4 py-3 text-right" :class="achievementClass(report.total.achievement_rate)">
              {{ report.total.achievement_rate !== null ? report.total.achievement_rate + '%' : '—' }}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>

    <!-- ── 予算登録フォーム（管理者のみ）─────────────────────────────────── -->
    <div v-if="isAdmin" class="space-y-4">
      <h2 class="text-base font-bold text-slate-700 border-t border-slate-200 pt-6">予算登録・編集</h2>

      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
        <div v-if="budgetError" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">{{ budgetError }}</div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <div>
            <label class="text-xs text-slate-600 block mb-1">年度</label>
            <input v-model.number="budgetForm.fiscal_year" type="number" class="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
          </div>
          <div>
            <label class="text-xs text-slate-600 block mb-1">月</label>
            <select v-model.number="budgetForm.month" class="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none">
              <option v-for="m in MONTHS" :key="m.value" :value="m.value">{{ m.label }}</option>
            </select>
          </div>
          <div>
            <label class="text-xs text-slate-600 block mb-1">勘定科目</label>
            <input v-model="budgetForm.account_subject" type="text" placeholder="交通費" class="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
          </div>
          <div>
            <label class="text-xs text-slate-600 block mb-1">予算金額（円）</label>
            <input v-model.number="budgetForm.amount" type="number" min="0" class="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
          </div>
        </div>
        <div class="flex gap-2">
          <button @click="handleSave" :disabled="isSaving"
            class="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
            <Plus :size="14" />
            {{ editingId ? '更新する' : '登録する' }}
          </button>
          <button v-if="editingId" @click="editingId = null"
            class="px-4 py-2 border border-slate-200 text-slate-600 text-sm rounded-lg hover:bg-slate-50">
            キャンセル
          </button>
        </div>
      </div>

      <!-- 予算一覧 -->
      <div v-if="budgets.length > 0" class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-xs text-slate-600 border-b">
            <tr>
              <th class="px-4 py-2 text-left">年度</th>
              <th class="px-4 py-2 text-left">月</th>
              <th class="px-4 py-2 text-left">勘定科目</th>
              <th class="px-4 py-2 text-right">金額</th>
              <th class="px-4 py-2 text-center">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="b in budgets" :key="b.id">
              <td class="px-4 py-2">{{ b.fiscal_year }}</td>
              <td class="px-4 py-2">{{ b.month }}月</td>
              <td class="px-4 py-2">{{ b.account_subject }}</td>
              <td class="px-4 py-2 text-right">¥{{ b.amount.toLocaleString() }}</td>
              <td class="px-4 py-2 text-center">
                <div class="flex justify-center gap-1">
                  <button @click="handleEdit(b)" class="p-1 hover:bg-slate-100 rounded text-slate-500">
                    <Edit2 :size="14" />
                  </button>
                  <button @click="handleDelete(b.id)" class="p-1 hover:bg-red-50 rounded text-red-400">
                    <Trash2 :size="14" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
