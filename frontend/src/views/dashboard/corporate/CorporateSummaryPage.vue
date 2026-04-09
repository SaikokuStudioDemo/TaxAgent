<script setup lang="ts">
import { computed, onMounted } from 'vue';
import {
  AlertCircle,
  ArrowUpRight,
  Wallet,
  Receipt,
  FileText,
  Building2,
  CheckCircle2,
  Clock,
  CircleDot,
} from 'lucide-vue-next';
import { RouterLink } from 'vue-router';
import { useInvoices } from '@/composables/useInvoices';
import { useReceipts } from '@/composables/useReceipts';
import { useTransactions } from '@/composables/useTransactions';
import { useCash } from '@/composables/useCash';
import { formatNumber as formatAmount } from '@/lib/utils/formatters';

const { invoices, fetchInvoices } = useInvoices();
const { receipts, fetchReceipts } = useReceipts();
const { transactions, matches, fetchTransactions, fetchMatches } = useTransactions();
const { cashSummary, fetchCashSummary } = useCash();

onMounted(() => {
  Promise.all([
    fetchInvoices(),
    fetchReceipts(),
    fetchTransactions(),
    fetchMatches(),
    fetchCashSummary(),
  ]);
});

// ── 経費精算（領収書） ────────────────────────────────
const expenseStats = computed(() => {
  const all = receipts.value;
  const pendingApproval = all.filter(r => r.approval_status === 'pending_approval').length;
  const approvedUnmatched = all.filter(
    r => r.approval_status === 'approved' && r.reconciliation_status !== 'reconciled'
  ).length;
  const matched = all.filter(r => r.reconciliation_status === 'reconciled').length;
  return { pendingApproval, approvedUnmatched, matched, total: all.length };
});

// ── 受領請求書 ────────────────────────────────────────
const receivedInvoiceStats = computed(() => {
  const all = invoices.value.filter(i => i.document_type === 'received');
  const pendingApproval = all.filter(i => i.approval_status === 'pending_approval').length;
  const approvedUnmatched = all.filter(
    i => ['approved', 'auto_approved'].includes(i.approval_status) && i.reconciliation_status !== 'reconciled'
  ).length;
  const matched = all.filter(i => i.reconciliation_status === 'reconciled').length;
  return { pendingApproval, approvedUnmatched, matched, total: all.length };
});

// ── 発行請求書 ────────────────────────────────────────
const issuedInvoiceStats = computed(() => {
  const all = invoices.value.filter(i => i.document_type === 'issued');
  const unsent = all.filter(i => !i.delivery_status || i.delivery_status === 'unsent').length;
  const sentUnmatched = all.filter(
    i => i.delivery_status === 'sent' && i.reconciliation_status !== 'reconciled'
  ).length;
  const matched = all.filter(i => i.reconciliation_status === 'reconciled').length;
  return { unsent, sentUnmatched, matched, total: all.length };
});

// ── 銀行口座明細 ──────────────────────────────────────
const bankStats = computed(() => {
  const all = transactions.value;
  const unmatched = all.filter(t => t.status === 'unmatched').length;
  const autoMatched = matches.value.filter((m: any) => m.match_type === 'auto_expense').length;
  const manualMatched = all.filter(t => t.status === 'matched').length - autoMatched;
  const transferred = all.filter(t => t.status === 'transferred').length;
  return { unmatched, autoMatched, manualMatched: Math.max(0, manualMatched), transferred, total: all.length };
});

// ── 要対応アラート ────────────────────────────────────
const alerts = computed(() => {
  const list: { message: string; to: string; label: string }[] = [];
  if (expenseStats.value.pendingApproval > 0) {
    list.push({
      message: `領収書の承認が ${expenseStats.value.pendingApproval}件 待機中です`,
      to: '/dashboard/corporate/receipts/approvals',
      label: '承認画面へ',
    });
  }
  if (expenseStats.value.approvedUnmatched > 0) {
    list.push({
      message: `承認済み領収書 ${expenseStats.value.approvedUnmatched}件 が未消込です`,
      to: '/dashboard/corporate/receipts/matching',
      label: '消込画面へ',
    });
  }
  if (receivedInvoiceStats.value.pendingApproval > 0) {
    list.push({
      message: `受領請求書の承認が ${receivedInvoiceStats.value.pendingApproval}件 待機中です`,
      to: '/dashboard/corporate/invoices/approvals',
      label: '承認画面へ',
    });
  }
  if (bankStats.value.unmatched > 0) {
    list.push({
      message: `銀行口座の未消込明細が ${bankStats.value.unmatched}件 あります`,
      to: '/dashboard/corporate/receipts/matching',
      label: '消込画面へ',
    });
  }
  return list;
});
</script>

<template>
  <div class="space-y-6">

    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900 tracking-tight">処理状況サマリー</h1>
      <p class="text-gray-500 mt-1 text-sm">承認・消込の処理状況をリアルタイムで確認できます</p>
    </div>

    <!-- Alerts -->
    <div v-if="alerts.length > 0" class="space-y-2">
      <div
        v-for="(alert, i) in alerts" :key="i"
        class="bg-amber-50 border-l-4 border-amber-400 px-4 py-3 rounded-r-lg flex items-center justify-between gap-3 shadow-sm"
      >
        <div class="flex items-center gap-2">
          <AlertCircle class="h-4 w-4 text-amber-600 shrink-0" />
          <p class="text-sm font-medium text-amber-800">{{ alert.message }}</p>
        </div>
        <RouterLink
          :to="alert.to"
          class="shrink-0 text-xs font-bold text-amber-700 hover:text-amber-900 flex items-center gap-1 bg-amber-100 hover:bg-amber-200 px-3 py-1.5 rounded-lg transition-colors"
        >
          {{ alert.label }} <ArrowUpRight class="h-3.5 w-3.5" />
        </RouterLink>
      </div>
    </div>
    <div v-else
      class="bg-emerald-50 border-l-4 border-emerald-400 px-4 py-3 rounded-r-lg flex items-center gap-2 shadow-sm">
      <CheckCircle2 class="h-4 w-4 text-emerald-600 shrink-0" />
      <p class="text-sm font-medium text-emerald-800">現在、対応が必要な項目はありません</p>
    </div>

    <!-- Status Cards: 2x2 grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-5">

      <!-- 経費精算 -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="p-2 bg-indigo-50 rounded-lg">
              <Receipt class="h-5 w-5 text-indigo-600" />
            </div>
            <div>
              <h2 class="text-sm font-bold text-gray-800">経費精算</h2>
              <p class="text-xs text-gray-400">領収書 計{{ expenseStats.total }}件</p>
            </div>
          </div>
          <RouterLink to="/dashboard/corporate/receipts/matching"
            class="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1">
            消込画面 <ArrowUpRight class="h-3.5 w-3.5" />
          </RouterLink>
        </div>
        <div class="p-5">
          <!-- Funnel steps -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Clock class="h-4 w-4 text-amber-500" />
                <span class="text-sm text-gray-600">承認待ち</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-extrabold"
                  :class="expenseStats.pendingApproval > 0 ? 'text-amber-500' : 'text-gray-300'">
                  {{ expenseStats.pendingApproval }}件
                </span>
                <RouterLink v-if="expenseStats.pendingApproval > 0"
                  to="/dashboard/corporate/receipts/approvals"
                  class="text-[10px] font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full hover:bg-amber-200 transition-colors">
                  対応する
                </RouterLink>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CircleDot class="h-4 w-4 text-blue-500" />
                <span class="text-sm text-gray-600">承認済・未消込</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-extrabold"
                  :class="expenseStats.approvedUnmatched > 0 ? 'text-blue-500' : 'text-gray-300'">
                  {{ expenseStats.approvedUnmatched }}件
                </span>
                <RouterLink v-if="expenseStats.approvedUnmatched > 0"
                  to="/dashboard/corporate/receipts/matching"
                  class="text-[10px] font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full hover:bg-blue-200 transition-colors">
                  消込する
                </RouterLink>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-emerald-500" />
                <span class="text-sm text-gray-600">消込済</span>
              </div>
              <span class="text-lg font-extrabold"
                :class="expenseStats.matched > 0 ? 'text-emerald-500' : 'text-gray-300'">
                {{ expenseStats.matched }}件
              </span>
            </div>
          </div>
          <!-- Progress bar -->
          <div class="mt-4 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div class="h-full bg-emerald-500 rounded-full transition-all"
              :style="{ width: expenseStats.total > 0 ? `${Math.round(expenseStats.matched / expenseStats.total * 100)}%` : '0%' }">
            </div>
          </div>
          <p class="text-right text-xs text-gray-400 mt-1">
            消込完了率 {{ expenseStats.total > 0 ? Math.round(expenseStats.matched / expenseStats.total * 100) : 0 }}%
          </p>
        </div>
      </div>

      <!-- 受領請求書 -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="p-2 bg-violet-50 rounded-lg">
              <FileText class="h-5 w-5 text-violet-600" />
            </div>
            <div>
              <h2 class="text-sm font-bold text-gray-800">受領請求書</h2>
              <p class="text-xs text-gray-400">計{{ receivedInvoiceStats.total }}件</p>
            </div>
          </div>
          <RouterLink to="/dashboard/corporate/invoices/payment-matching"
            class="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1">
            消込画面 <ArrowUpRight class="h-3.5 w-3.5" />
          </RouterLink>
        </div>
        <div class="p-5">
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Clock class="h-4 w-4 text-amber-500" />
                <span class="text-sm text-gray-600">承認待ち</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-extrabold"
                  :class="receivedInvoiceStats.pendingApproval > 0 ? 'text-amber-500' : 'text-gray-300'">
                  {{ receivedInvoiceStats.pendingApproval }}件
                </span>
                <RouterLink v-if="receivedInvoiceStats.pendingApproval > 0"
                  to="/dashboard/corporate/invoices/approvals"
                  class="text-[10px] font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full hover:bg-amber-200 transition-colors">
                  対応する
                </RouterLink>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CircleDot class="h-4 w-4 text-blue-500" />
                <span class="text-sm text-gray-600">承認済・未消込</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-extrabold"
                  :class="receivedInvoiceStats.approvedUnmatched > 0 ? 'text-blue-500' : 'text-gray-300'">
                  {{ receivedInvoiceStats.approvedUnmatched }}件
                </span>
                <RouterLink v-if="receivedInvoiceStats.approvedUnmatched > 0"
                  to="/dashboard/corporate/invoices/payment-matching"
                  class="text-[10px] font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full hover:bg-blue-200 transition-colors">
                  消込する
                </RouterLink>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-emerald-500" />
                <span class="text-sm text-gray-600">消込済</span>
              </div>
              <span class="text-lg font-extrabold"
                :class="receivedInvoiceStats.matched > 0 ? 'text-emerald-500' : 'text-gray-300'">
                {{ receivedInvoiceStats.matched }}件
              </span>
            </div>
          </div>
          <div class="mt-4 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div class="h-full bg-emerald-500 rounded-full transition-all"
              :style="{ width: receivedInvoiceStats.total > 0 ? `${Math.round(receivedInvoiceStats.matched / receivedInvoiceStats.total * 100)}%` : '0%' }">
            </div>
          </div>
          <p class="text-right text-xs text-gray-400 mt-1">
            消込完了率 {{ receivedInvoiceStats.total > 0 ? Math.round(receivedInvoiceStats.matched / receivedInvoiceStats.total * 100) : 0 }}%
          </p>
        </div>
      </div>

      <!-- 発行請求書 -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="p-2 bg-blue-50 rounded-lg">
              <FileText class="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <h2 class="text-sm font-bold text-gray-800">発行請求書</h2>
              <p class="text-xs text-gray-400">計{{ issuedInvoiceStats.total }}件</p>
            </div>
          </div>
          <RouterLink to="/dashboard/corporate/invoices/matching"
            class="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1">
            消込画面 <ArrowUpRight class="h-3.5 w-3.5" />
          </RouterLink>
        </div>
        <div class="p-5">
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Clock class="h-4 w-4 text-amber-500" />
                <span class="text-sm text-gray-600">未送付</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-extrabold"
                  :class="issuedInvoiceStats.unsent > 0 ? 'text-amber-500' : 'text-gray-300'">
                  {{ issuedInvoiceStats.unsent }}件
                </span>
                <RouterLink v-if="issuedInvoiceStats.unsent > 0"
                  to="/dashboard/corporate/invoices/list"
                  class="text-[10px] font-bold bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full hover:bg-amber-200 transition-colors">
                  対応する
                </RouterLink>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CircleDot class="h-4 w-4 text-blue-500" />
                <span class="text-sm text-gray-600">送付済・入金待ち</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-lg font-extrabold"
                  :class="issuedInvoiceStats.sentUnmatched > 0 ? 'text-blue-500' : 'text-gray-300'">
                  {{ issuedInvoiceStats.sentUnmatched }}件
                </span>
                <RouterLink v-if="issuedInvoiceStats.sentUnmatched > 0"
                  to="/dashboard/corporate/invoices/matching"
                  class="text-[10px] font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full hover:bg-blue-200 transition-colors">
                  消込する
                </RouterLink>
              </div>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-emerald-500" />
                <span class="text-sm text-gray-600">入金確認済</span>
              </div>
              <span class="text-lg font-extrabold"
                :class="issuedInvoiceStats.matched > 0 ? 'text-emerald-500' : 'text-gray-300'">
                {{ issuedInvoiceStats.matched }}件
              </span>
            </div>
          </div>
          <div class="mt-4 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div class="h-full bg-emerald-500 rounded-full transition-all"
              :style="{ width: issuedInvoiceStats.total > 0 ? `${Math.round(issuedInvoiceStats.matched / issuedInvoiceStats.total * 100)}%` : '0%' }">
            </div>
          </div>
          <p class="text-right text-xs text-gray-400 mt-1">
            入金完了率 {{ issuedInvoiceStats.total > 0 ? Math.round(issuedInvoiceStats.matched / issuedInvoiceStats.total * 100) : 0 }}%
          </p>
        </div>
      </div>

      <!-- 銀行口座明細 -->
      <div class="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="p-2 bg-slate-50 rounded-lg">
              <Building2 class="h-5 w-5 text-slate-600" />
            </div>
            <div>
              <h2 class="text-sm font-bold text-gray-800">銀行口座明細</h2>
              <p class="text-xs text-gray-400">計{{ bankStats.total }}件</p>
            </div>
          </div>
          <RouterLink to="/dashboard/corporate/banking/import"
            class="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1">
            取込画面 <ArrowUpRight class="h-3.5 w-3.5" />
          </RouterLink>
        </div>
        <div class="p-5">
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <Clock class="h-4 w-4 text-amber-500" />
                <span class="text-sm text-gray-600">未消込</span>
              </div>
              <span class="text-lg font-extrabold"
                :class="bankStats.unmatched > 0 ? 'text-amber-500' : 'text-gray-300'">
                {{ bankStats.unmatched }}件
              </span>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-emerald-400" />
                <span class="text-sm text-gray-600">自動消込済</span>
              </div>
              <span class="text-lg font-extrabold text-emerald-400">{{ bankStats.autoMatched }}件</span>
            </div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <CheckCircle2 class="h-4 w-4 text-emerald-600" />
                <span class="text-sm text-gray-600">現金移管 / 手動消込済</span>
              </div>
              <span class="text-lg font-extrabold text-emerald-600">
                {{ bankStats.transferred + bankStats.manualMatched }}件
              </span>
            </div>
          </div>
          <div class="mt-4 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div class="h-full bg-emerald-500 rounded-full transition-all"
              :style="{ width: bankStats.total > 0 ? `${Math.round((bankStats.total - bankStats.unmatched) / bankStats.total * 100)}%` : '0%' }">
            </div>
          </div>
          <p class="text-right text-xs text-gray-400 mt-1">
            処理完了率 {{ bankStats.total > 0 ? Math.round((bankStats.total - bankStats.unmatched) / bankStats.total * 100) : 0 }}%
          </p>
        </div>
      </div>

    </div>

    <!-- 現金出納帳サマリー -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
      <div class="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="p-2 bg-emerald-50 rounded-lg">
            <Wallet class="h-5 w-5 text-emerald-600" />
          </div>
          <h2 class="text-sm font-bold text-gray-800">現金出納帳</h2>
        </div>
        <RouterLink to="/dashboard/corporate/cash/matching"
          class="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1">
          <span v-if="(cashSummary?.unmatched_count ?? 0) > 0"
            class="bg-amber-100 text-amber-700 text-xs font-bold px-2 py-0.5 rounded-full mr-1">
            未消込 {{ cashSummary?.unmatched_count }}件
          </span>
          消込画面 <ArrowUpRight class="h-3.5 w-3.5" />
        </RouterLink>
      </div>
      <div class="p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="text-center">
          <p class="text-xs font-semibold text-gray-500 mb-1">現在残高</p>
          <p class="text-xl font-extrabold text-gray-900">¥{{ formatAmount(cashSummary?.current_balance ?? 0) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs font-semibold text-gray-500 mb-1">収入合計</p>
          <p class="text-xl font-extrabold text-emerald-600">¥{{ formatAmount(cashSummary?.total_income ?? 0) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs font-semibold text-gray-500 mb-1">支出合計</p>
          <p class="text-xl font-extrabold text-red-500">¥{{ formatAmount(cashSummary?.total_expense ?? 0) }}</p>
        </div>
        <div class="text-center">
          <p class="text-xs font-semibold text-gray-500 mb-1">未消込</p>
          <p class="text-xl font-extrabold"
            :class="(cashSummary?.unmatched_count ?? 0) > 0 ? 'text-amber-500' : 'text-gray-300'">
            {{ cashSummary?.unmatched_count ?? 0 }}件
          </p>
          <p class="text-xs text-gray-400 mt-0.5">¥{{ formatAmount(cashSummary?.unmatched_amount ?? 0) }}</p>
        </div>
      </div>
    </div>

  </div>
</template>
