<script setup lang="ts">
import { ref } from 'vue';
import { formatCurrency, calculateTaxInclusive } from '@/lib/utils/formatters';
import { 
  Building2, 
  Users, 
  Banknote,
  TrendingUp,
  CreditCard,
  Building
} from 'lucide-vue-next';

// -------------------------------------------------------------
// Mock Data generation for the Admin Dashboard to fulfill Phase 5
// -------------------------------------------------------------
const mrr = ref(3850000); // 3.85M JPY
const totalTaxFirms = ref(48);
const totalCorporates = ref(1240);

const salesAgentDistribution = ref([
  { id: 1, name: '山田 太郎', amount: 450000, clients: 15 },
  { id: 2, name: '佐藤 花子', amount: 320000, clients: 12 },
  { id: 3, name: '鈴木 一郎', amount: 280000, clients: 9 },
  { id: 4, name: '高橋 メアリー', amount: 150000, clients: 4 },
]);

const franchiseDistribution = ref([
  { id: 1, name: 'テスト会計事務所 (FC本舗)', amount: 850000, clients: 45 },
  { id: 2, name: 'みなとみらい税理士法人', amount: 620000, clients: 32 },
  { id: 3, name: '渋谷タックスパートナーズ', amount: 480000, clients: 25 },
]);
</script>

<template>
  <div class="p-8">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-slate-900 mb-2">プラットフォーム管理サマリー</h1>
      <p class="text-slate-500">
        Tax-Agent 全体の稼働状況、MRR、および各代理店への分配金を管理します。
      </p>
    </div>

    <!-- Top KPIs -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center gap-5">
        <div class="w-14 h-14 bg-sky-50 rounded-full flex items-center justify-center text-sky-600 flex-shrink-0">
          <Banknote :size="28" />
        </div>
        <div>
          <h2 class="text-sm font-bold text-slate-500 mb-1">今月のMRR (概算)</h2>
          <div class="text-3xl font-bold text-slate-900 flex items-end gap-2">
            {{ formatCurrency(calculateTaxInclusive(mrr)) }}
            <span class="text-sm font-medium text-emerald-600 flex items-center mb-1"><TrendingUp :size="14" class="mr-0.5"/> +12%</span>
          </div>
          <div class="text-xs text-slate-400 mt-1">(税抜 {{ formatCurrency(mrr) }})</div>
        </div>
      </div>

      <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center gap-5">
        <div class="w-14 h-14 bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600 flex-shrink-0">
          <Building2 :size="28" />
        </div>
        <div>
          <h2 class="text-sm font-bold text-slate-500 mb-1">アクティブな税理士法人</h2>
          <div class="text-3xl font-bold text-slate-900 flex items-end gap-2">
            {{ totalTaxFirms }} <span class="text-base font-normal text-slate-500 mb-0.5">社</span>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex items-center gap-5">
        <div class="w-14 h-14 bg-emerald-50 rounded-full flex items-center justify-center text-emerald-600 flex-shrink-0">
          <Building :size="28" />
        </div>
        <div>
          <h2 class="text-sm font-bold text-slate-500 mb-1">登録されている一般法人</h2>
          <div class="text-3xl font-bold text-slate-900 flex items-end gap-2">
            {{ totalCorporates }} <span class="text-base font-normal text-slate-500 mb-0.5">社</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      
      <!-- Sales Agents Revenue Distribution -->
      <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
        <div class="px-6 py-5 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
          <h2 class="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Users :size="20" class="text-indigo-500" /> 第一/二営業部 (内部セールス)
          </h2>
        </div>
        <div class="p-6 flex-1">
          <p class="text-sm text-slate-500 mb-4">今月の獲得顧客に対するインセンティブ/分配金の試算</p>
          <div class="space-y-4">
            <div v-for="agent in salesAgentDistribution" :key="agent.id" class="flex items-center justify-between p-4 border border-slate-100 rounded-lg hover:border-indigo-100 hover:bg-indigo-50/30 transition-colors">
              <div>
                <div class="font-bold text-slate-900">{{ agent.name }}</div>
                <div class="text-xs text-slate-500 mt-1">獲得: {{ agent.clients }}社</div>
              </div>
              <div class="text-right">
                <div class="font-bold text-indigo-700 text-lg">{{ formatCurrency(calculateTaxInclusive(agent.amount)) }}</div>
                <div class="text-[10px] text-slate-400">想定支払額 (税抜 {{ formatCurrency(agent.amount) }})</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Franchise Tax Firms Revenue Distribution -->
      <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
        <div class="px-6 py-5 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
          <h2 class="text-lg font-bold text-slate-800 flex items-center gap-2">
            <CreditCard :size="20" class="text-emerald-500" /> 紹介/FC税理士法人 キックバック
          </h2>
        </div>
        <div class="p-6 flex-1">
          <p class="text-sm text-slate-500 mb-4">自社顧客を本プラットフォームに onboarding した税理士法人への分配金</p>
          <div class="space-y-4">
            <div v-for="fc in franchiseDistribution" :key="fc.id" class="flex items-center justify-between p-4 border border-slate-100 rounded-lg hover:border-emerald-100 hover:bg-emerald-50/30 transition-colors">
              <div>
                <div class="font-bold text-slate-900">{{ fc.name }}</div>
                <div class="text-xs text-slate-500 mt-1">管理顧客: {{ fc.clients }}社</div>
              </div>
              <div class="text-right">
                <div class="font-bold text-emerald-700 text-lg">{{ formatCurrency(calculateTaxInclusive(fc.amount)) }}</div>
                <div class="text-[10px] text-slate-400">想定キックバック額 (税抜 {{ formatCurrency(fc.amount) }})</div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
