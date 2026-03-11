<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useAuth } from '@/composables/useAuth';
import { formatCurrency, calculateTaxInclusive } from '@/lib/utils/formatters';
import { Plus, Edit2, Loader2 } from 'lucide-vue-next';

const { currentUser, getToken } = useAuth();
const customers = ref<any[]>([]);
const isLoading = ref(true);

onMounted(async () => {
    if (!currentUser.value) return;
    try {
        const token = await getToken();
        if(!token) return;
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
        const response = await fetch(`${apiUrl}/users/clients`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            const resData = await response.json();
            customers.value = resData.data || [];
        }
    } catch (err) {
        console.error("Failed to fetch customers:", err);
    } finally {
        isLoading.value = false;
    }
});
</script>

<template>
  <div class="p-8">
    <div class="flex justify-between items-center mb-8">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 mb-2">顧客一覧</h1>
        <p class="text-gray-500">
          登録されている一般法人の一覧とステータスを確認・管理します。
        </p>
      </div>

      <!-- Add Customer Button -->
      <RouterLink
        to="/dashboard/tax-firm/contract-edit"
        class="flex items-center gap-2 bg-indigo-600 text-white font-bold py-2.5 px-5 rounded-lg hover:bg-indigo-700 shadow-sm transition-colors"
      >
        <Plus :size="20" />
        顧客を追加
      </RouterLink>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-gray-50 text-sm font-semibold text-gray-600 border-b border-gray-200">
              <th class="p-4 whitespace-nowrap">顧客名</th>
              <th class="p-4 whitespace-nowrap">ユーザー利用料</th>
              <th class="p-4 whitespace-nowrap">ステータス</th>
              <th class="p-4 whitespace-nowrap">MA</th>
              <th class="p-4 whitespace-nowrap">担当者</th>
              <th class="p-4 whitespace-nowrap text-center">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <template v-if="isLoading">
              <tr>
                <td colspan="6" class="p-12 text-center text-gray-400">
                  <div class="flex flex-col items-center justify-center gap-3">
                    <Loader2 :size="32" class="animate-spin text-indigo-400" />
                    <p>顧客データを読込中...</p>
                  </div>
                </td>
              </tr>
            </template>
            <template v-else-if="customers.length === 0">
              <tr>
                <td colspan="6" class="p-8 text-center text-gray-500">
                  まだ登録されている顧客がいません。「顧客を追加」ボタンから法人を登録してください。
                </td>
              </tr>
            </template>
            <template v-else>
              <tr v-for="customer in customers" :key="customer._id" class="hover:bg-gray-50/50 transition-colors">
                <td class="p-4 font-bold text-gray-900">
                  {{ customer.companyName }}
                  <div class="text-xs text-gray-400 font-normal mt-0.5 font-mono">{{ customer.firebase_uid }}</div>
                </td>
                <td class="p-4 text-gray-600 font-medium">
                  {{ formatCurrency(calculateTaxInclusive(customer.totalUsageFee || 0)) }}
                  <span class="text-[10px] text-gray-400 block mt-0.5">(税抜 {{ formatCurrency(customer.totalUsageFee || 0) }})</span>
                </td>
                <td class="p-4">
                  <span
                    class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border"
                    :class="customer.status === '税理士対応完了' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'"
                  >
                    {{ customer.status || '未設定' }}
                  </span>
                </td>
                <td class="p-4">
                  <span
                    class="text-xs font-semibold"
                    :class="customer.maStatus === 'アクティブ' ? 'text-indigo-600' : 'text-gray-500'"
                  >
                    {{ customer.maStatus || '未設定' }}
                  </span>
                </td>
                <td class="p-4">
                  <div class="flex items-center gap-2">
                    <div class="w-6 h-6 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center text-xs font-bold">
                      {{ customer.assignee?.charAt(0) || '-' }}
                    </div>
                    <span class="text-sm font-medium text-gray-700">{{ customer.assignee || '未設定' }}</span>
                  </div>
                </td>
                <td class="p-4 text-center">
                  <RouterLink
                    :to="`/dashboard/tax-firm/contract-edit/${customer._id}`"
                    class="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-gray-100 text-gray-600 hover:bg-indigo-50 hover:text-indigo-600 transition-colors"
                    title="編集"
                  >
                    <Edit2 :size="16" />
                  </RouterLink>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
