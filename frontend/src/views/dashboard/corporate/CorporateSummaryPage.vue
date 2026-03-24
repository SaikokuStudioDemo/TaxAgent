<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  AlertCircle,
  CreditCard,
  FileText,
  CheckCircle,
  Percent,
  ArrowUpRight
} from 'lucide-vue-next';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Doughnut } from 'vue-chartjs';
import { useInvoices } from '@/composables/useInvoices';
import { useReceipts } from '@/composables/useReceipts';
import { useBankTransactions } from '@/composables/useBankTransactions';

ChartJS.register(ArcElement, Tooltip, Legend);

// --- KPI DATA ---
const { invoices, fetchInvoices } = useInvoices();
const { receipts, fetchReceipts } = useReceipts();
const { transactions, matches, fetchTransactions, fetchMatches } = useBankTransactions();

onMounted(() => {
    Promise.all([
        fetchInvoices(),
        fetchReceipts(),
        fetchTransactions(),
        fetchMatches(),
    ]);
});

const kpi = computed(() => {
    const totalDocs = invoices.value.length + receipts.value.length;
    const matchCount = matches.value.length;
    const rate = totalDocs > 0 ? Math.round((matchCount / totalDocs) * 1000) / 10 : 0;
    return {
        bankCount: transactions.value.length,
        docCount: totalDocs,
        matchCount,
        matchRate: rate,
    };
});

const chartData = {
  labels: ['請求書', '領収書'],
  datasets: [
    {
      backgroundColor: ['#3b82f6', '#10b981'], // blue-500, emerald-500
      data: [750000, 450000],
      borderWidth: 0,
      hoverOffset: 4
    }
  ]
};

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '75%',
  plugins: {
    legend: {
      display: false
    },
    tooltip: {
      callbacks: {
        label: function(context: any) {
          let label = context.label || '';
          if (label) {
            label += ': ';
          }
          if (context.parsed !== null) {
            label += new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY' }).format(context.parsed);
          }
          return label;
        }
      }
    }
  }
};
</script>

<template>
  <div class="space-y-6">
    <!-- Header & Alert -->
    <div class="flex justify-between items-end mb-2">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 tracking-tight">顧客サマリー</h1>
        <p class="text-gray-500 mt-1">最新の経費および請求状況をご確認いただけます</p>
      </div>
    </div>

    <div class="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-r-lg flex items-start gap-3 shadow-sm">
      <AlertCircle class="text-yellow-600 mt-0.5" :size="20" />
      <div>
        <h3 class="text-sm font-bold text-yellow-800">あと2日で承認状況を100%にしてください</h3>
        <p class="text-sm text-yellow-700 mt-0.5">現在未承認の領収書が12件残っています。期日までの処理をお願いします。</p>
      </div>
    </div>

    <!-- KPI Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
      <!-- Card 1 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
        <div class="flex justify-between items-start mb-4">
          <div class="p-3 bg-gray-50 rounded-xl"><CreditCard :size="24" class="text-blue-600" /></div>
          <div class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-50 text-emerald-700">+12%</div>
        </div>
        <h3 class="text-gray-500 text-sm font-medium mb-1">登録された銀行/カード</h3>
        <p class="text-3xl font-extrabold text-gray-900">{{ kpi.bankCount }}</p>
      </div>
      <!-- Card 2 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
        <div class="flex justify-between items-start mb-4">
          <div class="p-3 bg-gray-50 rounded-xl"><FileText :size="24" class="text-emerald-600" /></div>
          <div class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-50 text-emerald-700">+5%</div>
        </div>
        <h3 class="text-gray-500 text-sm font-medium mb-1">登録された請求書/領収書</h3>
        <p class="text-3xl font-extrabold text-gray-900">{{ kpi.docCount }}</p>
      </div>
      <!-- Card 3 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
        <div class="flex justify-between items-start mb-4">
          <div class="p-3 bg-gray-50 rounded-xl"><CheckCircle :size="24" class="text-indigo-600" /></div>
          <div class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-50 text-emerald-700">+18%</div>
        </div>
        <h3 class="text-gray-500 text-sm font-medium mb-1">完了したマッチング</h3>
        <p class="text-3xl font-extrabold text-gray-900">{{ kpi.matchCount }}</p>
      </div>
      <!-- Card 4 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm border border-gray-200 hover:shadow-md transition-shadow">
        <div class="flex justify-between items-start mb-4">
          <div class="p-3 bg-gray-50 rounded-xl"><Percent :size="24" class="text-purple-600" /></div>
          <div class="px-2.5 py-1 text-xs font-bold rounded-full bg-red-50 text-red-600">-2.1%</div>
        </div>
        <h3 class="text-gray-500 text-sm font-medium mb-1">マッチング完了率</h3>
        <p class="text-3xl font-extrabold text-gray-900">{{ kpi.matchRate }}%</p>
      </div>
    </div>

    <!-- Main Content Area -->
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6 pt-4">

      <!-- Table: Department Progress -->
      <div class="xl:col-span-3 bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
        <div class="px-6 py-5 border-b border-gray-100 flex justify-between items-center">
          <h2 class="text-lg font-bold text-gray-800">概要データ (部署別)</h2>
          <button class="text-sm text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1">
            詳細を見る <ArrowUpRight :size="16" />
          </button>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-gray-50/50 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                <th class="py-4 px-6 border-b border-gray-100">部署名</th>
                <th class="py-4 px-6 border-b border-gray-100 text-right">提出済</th>
                <th class="py-4 px-6 border-b border-gray-100 text-right">承認済</th>
                <th class="py-4 px-6 border-b border-gray-100 text-right">完了率</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 text-sm">
              <tr class="hover:bg-gray-50/50 transition-colors">
                <td class="py-4 px-6 font-medium text-gray-900">営業部</td>
                <td class="py-4 px-6 text-right text-gray-600">45件</td>
                <td class="py-4 px-6 text-right text-gray-600">42件</td>
                <td class="py-4 px-6 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <span class="font-bold text-emerald-600">93.3%</span>
                    <div class="w-16 h-2 bg-gray-100 rounded-full overflow-hidden inline-block"><div class="w-[93%] h-full bg-emerald-500 rounded-full"></div></div>
                  </div>
                </td>
              </tr>
              <tr class="hover:bg-gray-50/50 transition-colors">
                <td class="py-4 px-6 font-medium text-gray-900">開発部</td>
                <td class="py-4 px-6 text-right text-gray-600">28件</td>
                <td class="py-4 px-6 text-right text-gray-600">19件</td>
                <td class="py-4 px-6 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <span class="font-bold text-amber-500">67.8%</span>
                    <div class="w-16 h-2 bg-gray-100 rounded-full overflow-hidden inline-block"><div class="w-[67%] h-full bg-amber-400 rounded-full"></div></div>
                  </div>
                </td>
              </tr>
              <tr class="hover:bg-gray-50/50 transition-colors">
                <td class="py-4 px-6 font-medium text-gray-900">広報部</td>
                <td class="py-4 px-6 text-right text-gray-600">12件</td>
                <td class="py-4 px-6 text-right text-gray-600">12件</td>
                <td class="py-4 px-6 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <span class="font-bold text-emerald-600">100%</span>
                    <div class="w-16 h-2 bg-gray-100 rounded-full overflow-hidden inline-block"><div class="w-full h-full bg-emerald-500 rounded-full"></div></div>
                  </div>
                </td>
              </tr>
              <tr class="hover:bg-gray-50/50 transition-colors">
                <td class="py-4 px-6 font-medium text-gray-900">人事部</td>
                <td class="py-4 px-6 text-right text-gray-600">4件</td>
                <td class="py-4 px-6 text-right text-gray-600">1件</td>
                <td class="py-4 px-6 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <span class="font-bold text-red-500">25.0%</span>
                    <div class="w-16 h-2 bg-gray-100 rounded-full overflow-hidden inline-block"><div class="w-[25%] h-full bg-red-500 rounded-full"></div></div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Bottom Visualizations Area -->
      <div class="xl:col-span-1 bg-white rounded-2xl shadow-sm border border-gray-200 p-6 flex flex-col h-full">
        <h3 class="text-gray-800 font-bold self-start mb-6">合計金額内訳</h3>
        
        <div class="flex-1 flex flex-col items-center justify-center relative">
          <!-- Donut Chart -->
          <div class="w-48 h-48 relative">
            <Doughnut :data="chartData" :options="chartOptions" />
            
            <!-- Center Text Overlay -->
            <div class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-1">
              <span class="block text-2xl font-bold text-gray-800">¥1.2M</span>
              <span class="block text-[10px] text-gray-500 font-medium">今月累計</span>
            </div>
          </div>
          
          <!-- Custom Legend -->
          <div class="flex gap-6 mt-8 text-sm font-medium text-gray-600">
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 bg-blue-500 rounded-full"></div>請求書
            </div>
            <div class="flex items-center gap-2">
              <div class="w-3 h-3 bg-emerald-500 rounded-full"></div>領収書
            </div>
          </div>
        </div>
      </div>

      <div class="xl:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-200 p-6 flex flex-col h-full">
        <h3 class="text-gray-800 font-bold mb-6">承認進捗</h3>
        
        <div class="space-y-6 flex-1">
          <!-- Row 1: 係長承認待ち -->
          <div class="flex items-center justify-between group">
            <span class="text-sm font-medium text-gray-700 w-32">係長承認待ち</span>
            <div class="flex items-center gap-6 flex-1 justify-end">
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">提出数</span>
                <span class="block font-bold text-gray-800">120</span>
              </div>
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">承認数</span>
                <span class="block font-bold text-gray-800">80</span>
              </div>
              <div class="text-right ml-4 w-16">
                <span class="block text-[10px] text-gray-400">完了率</span>
                <span class="block font-bold text-blue-600">66.7%</span>
              </div>
            </div>
          </div>
          <div class="h-px bg-gray-100 w-full group-last:hidden"></div>

          <!-- Row 2: 課長承認待ち -->
          <div class="flex items-center justify-between group">
            <span class="text-sm font-medium text-gray-700 w-32">課長承認待ち</span>
            <div class="flex items-center gap-6 flex-1 justify-end">
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">提出数</span>
                <span class="block font-bold text-gray-800">80</span>
              </div>
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">承認数</span>
                <span class="block font-bold text-gray-800">50</span>
              </div>
              <div class="text-right ml-4 w-16">
                <span class="block text-[10px] text-gray-400">完了率</span>
                <span class="block font-bold text-blue-600">62.5%</span>
              </div>
            </div>
          </div>
          <div class="h-px bg-gray-100 w-full group-last:hidden"></div>

          <!-- Row 3: 部長承認待ち -->
          <div class="flex items-center justify-between group">
            <span class="text-sm font-medium text-gray-700 w-32">部長承認待ち</span>
            <div class="flex items-center gap-6 flex-1 justify-end">
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">提出数</span>
                <span class="block font-bold text-gray-800">30</span>
              </div>
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">承認数</span>
                <span class="block font-bold text-gray-800">15</span>
              </div>
              <div class="text-right ml-4 w-16">
                <span class="block text-[10px] text-gray-400">完了率</span>
                <span class="block font-bold text-blue-600">50.0%</span>
              </div>
            </div>
          </div>
          <div class="h-px bg-gray-100 w-full group-last:hidden"></div>

          <!-- Row 4: 社長承認待ち -->
          <div class="flex items-center justify-between group">
            <span class="text-sm font-medium text-gray-700 w-32">社長承認待ち</span>
            <div class="flex items-center gap-6 flex-1 justify-end">
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">提出数</span>
                <span class="block font-bold text-gray-800">10</span>
              </div>
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">承認数</span>
                <span class="block font-bold text-gray-800">2</span>
              </div>
              <div class="text-right ml-4 w-16">
                <span class="block text-[10px] text-gray-400">完了率</span>
                <span class="block font-bold text-blue-600">20.0%</span>
              </div>
            </div>
          </div>
          <div class="h-px bg-gray-100 w-full group-last:hidden"></div>

          <!-- Row 5: 承認完了 -->
          <div class="flex items-center justify-between group">
            <span class="text-sm font-medium text-gray-700 w-32">承認完了</span>
            <div class="flex items-center gap-6 flex-1 justify-end">
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">提出数</span>
                <span class="block font-bold text-gray-800">1,500</span>
              </div>
              <div class="text-center">
                <span class="block text-[10px] text-gray-400">承認数</span>
                <span class="block font-bold text-gray-800">1,500</span>
              </div>
              <div class="text-right ml-4 w-16">
                <span class="block text-[10px] text-gray-400">完了率</span>
                <span class="block font-bold text-blue-600">100.0%</span>
              </div>
            </div>
          </div>
          <div class="h-px bg-gray-100 w-full group-last:hidden"></div>

        </div>
      </div>

    </div>
  </div>
</template>
