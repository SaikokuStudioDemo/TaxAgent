<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { RouterLink } from 'vue-router';
import { useAuth } from '@/composables/useAuth';
import { api } from '@/lib/api';
import {
  LayoutDashboard,
  Receipt,
  FileText,
  Settings,
  UserCircle,
  CheckCircle,
  LogOut,
  Users,
  CreditCard,
  Building2,
  ChevronLeft,
  ChevronRight,
  ArrowRightLeft,
  BookText,
  Wallet,
  History,
  Zap,
  Link2,
  List,
  Upload,
  ShieldCheck,
  Database,
  KeyRound,
  Download,
  BarChart3,
  LayoutTemplate,
  Calculator,
} from 'lucide-vue-next';
import AIChatPanel from '@/components/chat/AIChatPanel.vue';

const isLeftSidebarOpen = ref(true);
const isChatOverlay = ref(true);   // ログイン直後はオーバーレイ表示

const { signOut, displayName, displayRole, isAdmin, isAccountingOrAbove } = useAuth();

// ── 承認待ちバッジ ────────────────────────────────────────────
const hasPendingReceipts = ref(false);
const hasPendingInvoices = ref(false);

const fetchPendingCounts = async () => {
    try {
        const [receipts, invoices] = await Promise.all([
            api.get<any[]>('/receipts?approval_status=pending_approval&limit=1'),
            api.get<any[]>('/invoices?approval_status=pending_approval&document_type=received&limit=1'),
        ]);
        hasPendingReceipts.value = Array.isArray(receipts) && receipts.length > 0;
        hasPendingInvoices.value = Array.isArray(invoices) && invoices.length > 0;
    } catch { /* サイレントに失敗 */ }
};

onMounted(() => {
    fetchPendingCounts();
});
</script>

<template>
  <div class="flex h-screen bg-gray-50 overflow-hidden font-sans">
    <!-- Left Navigation Sidebar -->
    <aside :class="['bg-white text-slate-800 border-r border-slate-200 flex flex-col justify-between flex-shrink-0 relative z-30 shadow-sm transition-all duration-300', isLeftSidebarOpen ? 'w-64' : 'w-20']">
      <!-- Floating Toggle Left -->
      <button 
        @click="isLeftSidebarOpen = !isLeftSidebarOpen"
        class="absolute -right-3 top-8 bg-white border border-gray-200 text-gray-500 hover:text-blue-600 rounded-full p-1 shadow-md z-50 flex items-center justify-center transition-colors"
      >
        <ChevronLeft v-if="isLeftSidebarOpen" :size="16" />
        <ChevronRight v-else :size="16" />
      </button>
      <div class="flex flex-col h-full overflow-hidden">
        <!-- Brand & Toggle -->
        <div class="px-4 py-3 border-b border-slate-200 flex items-center" :class="isLeftSidebarOpen ? 'justify-start' : 'justify-center'">
          <div class="flex items-center gap-3 overflow-hidden" :class="isLeftSidebarOpen ? 'ml-2' : ''">
            <img
              src="/logo.png"
              alt="Tax Agent"
              :class="isLeftSidebarOpen ? 'h-16 w-auto object-contain' : 'h-10 w-10 object-contain'"
            />
          </div>
        </div>

        <!-- Nav Links -->
        <nav class="flex-1 overflow-y-auto px-3 py-6 space-y-8 no-scrollbar">
          <!-- サマリー -->
          <div>
            <RouterLink to="/dashboard/corporate" exact-active-class="bg-indigo-600 text-white" class="flex items-center gap-3 px-3 py-2.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg font-medium transition-colors" :class="{'justify-center': !isLeftSidebarOpen}">
              <LayoutDashboard :size="20" class="shrink-0" />
              <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">サマリー</span>
            </RouterLink>
          </div>

          <!-- 書類登録 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <Upload :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">書類登録</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/receipts/upload" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="領収書提出">
                <Receipt :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">領収書提出</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/receive" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="受領請求書アップロード">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">受領請求書アップロード</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/create" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="請求書発行">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">請求書発行</span>
              </RouterLink>
            </div>
          </div>

          <!-- 書類管理 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <List :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">書類管理</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/receipts/list" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="領収書一覧">
                <List :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">領収書一覧</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/received-list" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="受取請求書一覧">
                <List :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">受取請求書一覧</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/list" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="請求書リスト">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">請求書リスト</span>
              </RouterLink>
            </div>
          </div>

          <!-- 承認 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <ShieldCheck :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">承認</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/receipts/approvals" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="領収書承認">
                <Receipt :size="18" class="shrink-0" />
                <span v-if="isLeftSidebarOpen" class="whitespace-nowrap flex-1">領収書承認</span>
                <span v-if="hasPendingReceipts" class="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/approvals" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="請求書承認">
                <CheckCircle :size="18" class="shrink-0" />
                <span v-if="isLeftSidebarOpen" class="whitespace-nowrap flex-1">請求書承認</span>
                <span v-if="hasPendingInvoices" class="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
              </RouterLink>
            </div>
          </div>

          <!-- 照合・消込 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <Link2 :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">照合・消込</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/receipts/matching" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="経費消込">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">経費消込</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/payment-matching" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="支払消込">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">支払消込</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/matching" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="入金消込">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">入金消込</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/cash/matching" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="現金消込">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">現金消込</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/banking/outflow" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="出金明細照合">
                <Link2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">出金明細照合</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/banking/inflow" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="入金明細照合">
                <Link2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">入金明細照合</span>
              </RouterLink>
            </div>
          </div>

          <!-- データ管理 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <Database :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">データ管理</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink v-if="isAccountingOrAbove" to="/dashboard/corporate/banking/import" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="銀行明細アップロード">
                <CreditCard :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">銀行明細アップロード</span>
              </RouterLink>
              <RouterLink v-if="isAccountingOrAbove" to="/dashboard/corporate/cash/ledger" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="現金出納帳">
                <Wallet :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">現金出納帳</span>
              </RouterLink>
              <RouterLink v-if="isAccountingOrAbove" to="/dashboard/corporate/banking/history" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="インポート履歴">
                <History :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">インポート履歴</span>
              </RouterLink>
              <RouterLink v-if="isAccountingOrAbove" to="/dashboard/corporate/banking/auto-matches" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="自動消込履歴">
                <Zap :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">自動消込履歴</span>
              </RouterLink>
            </div>
          </div>

          <!-- アウトプット（isAccountingOrAbove のみ表示） -->
          <div v-if="isAccountingOrAbove">
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <Download :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">アウトプット</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/outputs/csv" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="CSV出力">
                <Download :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">CSV出力</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/outputs/zengin" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="全銀データ">
                <Building2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">全銀データ</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/outputs/reports" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="レポート・予算対比">
                <BarChart3 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">レポート・予算対比</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/outputs/tax-report" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="税務申告サポート">
                <Calculator :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">税務申告サポート</span>
              </RouterLink>
            </div>
          </div>

          <!-- テンプレート（isAccountingOrAbove のみ表示） -->
          <div v-if="isAccountingOrAbove">
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <LayoutTemplate :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">テンプレート</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/templates/invoices" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="請求書テンプレート">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">請求書テンプレート</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/templates/receipts" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="領収書テンプレート">
                <Receipt :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">領収書テンプレート</span>
              </RouterLink>
            </div>
          </div>

          <!-- ルール設定 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <Settings :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">ルール設定</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink v-if="isAdmin" to="/dashboard/corporate/rules/approvals" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="承認ルール">
                <ShieldCheck :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">承認ルール</span>
              </RouterLink>
              <RouterLink v-if="isAccountingOrAbove" to="/dashboard/corporate/settings/matching-rules" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="消込条件ルール">
                <ArrowRightLeft :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">消込条件ルール</span>
              </RouterLink>
              <RouterLink v-if="isAccountingOrAbove" to="/dashboard/corporate/settings/journal-rules" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="自動仕訳ルール">
                <BookText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">自動仕訳ルール</span>
              </RouterLink>
            </div>
          </div>

          <!-- マスター管理 -->
          <div>
            <div v-if="isLeftSidebarOpen" class="flex items-center gap-1.5 px-3 mb-3">
              <Building2 :size="12" class="text-slate-400" />
              <p class="text-xs font-semibold text-slate-500 uppercase tracking-wider">マスター管理</p>
            </div>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink v-if="isAdmin" to="/dashboard/corporate/settings/organization" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="部門・プロジェクト">
                <Users :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">部門・プロジェクト</span>
              </RouterLink>
              <RouterLink v-if="isAdmin" to="/dashboard/corporate/settings/company" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="自社情報管理">
                <Building2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">自社情報管理</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/settings/clients" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="取引先管理">
                <Building2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">取引先管理</span>
              </RouterLink>
              <RouterLink v-if="isAdmin" to="/dashboard/corporate/users" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="ユーザー一覧">
                <Users :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">ユーザー一覧</span>
              </RouterLink>
              <RouterLink v-if="isAdmin" to="/dashboard/corporate/settings/permissions" class="flex items-center gap-3 px-3 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors" active-class="bg-indigo-50 text-indigo-700" :class="{'justify-center': !isLeftSidebarOpen}" title="権限設定">
                <KeyRound :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">権限設定</span>
              </RouterLink>
            </div>
          </div>
        </nav>

        <!-- User Profile -->
        <div class="p-4 border-t border-slate-200 flex flex-col items-center">
          <div class="flex items-center gap-3 px-2 py-2 cursor-pointer hover:bg-slate-100 rounded-lg transition-colors w-full" :class="{'justify-center': !isLeftSidebarOpen}" title="プロフィール設定">
            <UserCircle :size="32" class="text-slate-400 shrink-0" />
            <div class="flex-1 min-w-0" v-if="isLeftSidebarOpen">
              <p class="text-sm font-medium text-slate-800 truncate" :title="displayName">{{ displayName !== '読込中...' ? displayName : '...' }}</p>
              <p class="text-xs text-slate-500 truncate">{{ displayRole }}</p>
            </div>
            <Settings :size="16" class="text-slate-400 shrink-0" v-if="isLeftSidebarOpen" />
          </div>
          <button @click="signOut" class="w-full mt-2 flex items-center gap-3 py-2 text-slate-500 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium" :class="isLeftSidebarOpen ? 'px-3' : 'justify-center'" title="ログアウト">
            <LogOut :size="18" class="shrink-0" />
            <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">ログアウト</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- Center Content (Main Dashboard) -->
    <main class="flex-1 flex flex-col min-w-0 bg-[#F5F7FA] relative z-10">

      <div class="flex-1 overflow-y-auto no-scrollbar relative min-h-0 container mx-auto p-4 lg:p-8">
        <router-view :key="$route.name" />
      </div>
    </main>

  </div>

  <!-- AI チャットパネル（オーバーレイ / フローティング切替） -->
  <AIChatPanel
    :is-overlay="isChatOverlay"
    :sidebar-collapsed="!isLeftSidebarOpen"
    @close="isChatOverlay = false"
    @open-overlay="isChatOverlay = true"
  />
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;  /* IE and Edge */
  scrollbar-width: none;  /* Firefox */
}
</style>
