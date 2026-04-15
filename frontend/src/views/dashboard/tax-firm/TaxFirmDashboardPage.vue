<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useAuth } from '@/composables/useAuth';
import { formatCurrency, calculateTaxInclusive } from '@/lib/utils/formatters';
import { Users, Banknote, ShieldCheck, Loader2 } from 'lucide-vue-next';
import { PLANS } from '@/lib/constants/mockData';

const { currentUser, getToken, userProfile, displayName } = useAuth();
const clients = ref<any[]>([]);
const isLoading = ref(true);

onMounted(async () => {
    if (!currentUser.value) return;
    try {
        const token = await getToken();
        if (!token) return;
        const headers = { 'Authorization': `Bearer ${token}` };
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

        const clientsRes = await fetch(`${apiUrl}/users/clients`, { headers });
        if (clientsRes.ok) {
            clients.value = (await clientsRes.json()).data || [];
        }
    } catch (err) {
        console.error("Failed to load dashboard data:", err);
    } finally {
        isLoading.value = false;
    }
});

const totalUsageFee = () => clients.value.reduce((sum, client) => sum + (client.totalUsageFee || 0), 0);
const planName = () => {
    const plan = PLANS.find((p: any) => p.id === userProfile.value?.data?.planId);
    return plan?.name || 'プラン情報なし';
};
</script>

<template>
    <div v-if="isLoading" class="flex h-[calc(100vh-64px)] items-center justify-center">
        <Loader2 :size="32" class="animate-spin relative text-indigo-500" />
    </div>

    <div v-else class="p-8">
        <h1 class="text-2xl font-bold text-gray-900 mb-8">顧客ダッシュボード（サマリー）</h1>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <!-- Total Customers Card -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col items-center text-center">
                <div class="w-12 h-12 bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600 mb-4">
                    <Users :size="24" />
                </div>
                <h2 class="text-sm font-bold text-gray-500 mb-1">総顧客数</h2>
                <div class="text-3xl font-bold text-gray-900">
                    {{ clients.length }} <span class="text-base font-medium text-gray-500">社</span>
                </div>
            </div>

            <!-- Total Revenue Card -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col items-center text-center">
                <div class="w-12 h-12 bg-emerald-50 rounded-full flex items-center justify-center text-emerald-600 mb-4">
                    <Banknote :size="24" />
                </div>
                <h2 class="text-sm font-bold text-gray-500 mb-1">ユーザー利用料 合計 (月額)</h2>
                <div class="text-3xl font-bold text-gray-900">
                    {{ formatCurrency(calculateTaxInclusive(totalUsageFee())) }} <span class="text-base font-medium text-gray-500">/ 月</span>
                </div>
                <div class="text-xs text-gray-400 mt-1">(税抜 {{ formatCurrency(totalUsageFee()) }})</div>
            </div>

            <!-- Contract Plan Card -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 flex flex-col items-center text-center">
                <div class="w-12 h-12 bg-amber-50 rounded-full flex items-center justify-center text-amber-600 mb-4">
                    <ShieldCheck :size="24" />
                </div>
                <h2 class="text-sm font-bold text-gray-500 mb-1">現在の契約プラン</h2>
                <div class="text-2xl font-bold text-gray-900 mb-1">
                    {{ planName() }}
                </div>
                <p v-if="userProfile?.data?.monthlyFee !== undefined" class="text-lg font-bold text-indigo-600 mb-2">
                    {{ formatCurrency(calculateTaxInclusive(userProfile?.data?.monthlyFee)) }} <span class="text-sm font-medium text-gray-500">/ 月</span>
                    <span class="block text-xs text-gray-400 font-normal mt-0.5">(税抜 {{ formatCurrency(userProfile?.data?.monthlyFee) }})</span>
                </p>
                <p class="text-xs text-gray-400">{{ displayName }}</p>
            </div>
        </div>

        <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-8 flex items-center justify-center h-[300px]">
            <p class="text-gray-500">※ チャートやその他の統計データがここに表示されます</p>
        </div>
    </div>
</template>
