<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { Home, Users, Settings, LogOut, ArrowRightLeft, BookText } from 'lucide-vue-next';
import { useAuth } from '@/composables/useAuth';

const route = useRoute();
const { currentUser, getToken, signOut } = useAuth();
const companyName = ref('読込中...');
const role = ref('管理者');

onMounted(async () => {
    if (!currentUser.value) return;
    try {
        const token = await getToken();
        if (token) {
             const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
             const response = await fetch(`${apiUrl}/users/me`, {
                 headers: { 'Authorization': `Bearer ${token}` }
             });
             if (response.ok) {
                 const resData = await response.json();
                 if (resData.data?.companyName) {
                     companyName.value = resData.data.companyName;
                 }
                 if (resData.type === 'employee') {
                     companyName.value = resData.data?.name || 'ユーザー';
                     role.value = resData.data?.role === 'admin' ? '管理者' : 'スタッフ';
                 }
             }
        }
    } catch (err) {
        console.error("Failed to fetch profile", err);
        companyName.value = 'エラー';
    }
});

const isActive = (path: string) => {
    if (path === '/dashboard/tax-firm' && route.path === '/dashboard/tax-firm') return true;
    if (path !== '/dashboard/tax-firm' && route.path.startsWith(path)) return true;
    return false;
};
</script>

<template>
  <aside class="w-64 bg-white border-r border-gray-200 flex flex-col fixed h-full z-10">
    <div class="p-6 border-b border-gray-100">
      <h1 class="text-xl font-extrabold text-[#1D4ED8]">Tax-Agent</h1>
      <p class="text-xs text-gray-500 mt-1">税理士法人用ダッシュボード</p>
    </div>

    <nav class="flex-1 p-4 space-y-1">
      <RouterLink 
        to="/dashboard/tax-firm" 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors"
        :class="isActive('/dashboard/tax-firm') ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-700 hover:bg-gray-50 hover:text-indigo-600'"
      >
        <Home :size="20" :class="isActive('/dashboard/tax-firm') ? 'text-indigo-600' : 'text-gray-400'" />
        サマリー
      </RouterLink>
      
      <RouterLink 
        to="/dashboard/tax-firm/customers" 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors"
        :class="isActive('/dashboard/tax-firm/customers') || route.path.includes('/contract-edit') ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-700 hover:bg-gray-50 hover:text-indigo-600'"
      >
        <Users :size="20" :class="isActive('/dashboard/tax-firm/customers') || route.path.includes('/contract-edit') ? 'text-indigo-600' : 'text-gray-400'" />
        顧客一覧
      </RouterLink>

      <div class="mt-8 pt-6 border-t border-gray-100">
        <h3 class="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">管理メニュー</h3>
        <RouterLink 
          to="/dashboard/tax-firm/users" 
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors"
          :class="isActive('/dashboard/tax-firm/users') ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-700 hover:bg-gray-50 hover:text-indigo-600'"
        >
          <Settings :size="20" :class="isActive('/dashboard/tax-firm/users') ? 'text-indigo-600' : 'text-gray-400'" />
          ユーザー一覧・招待
        </RouterLink>
        <RouterLink 
          to="/dashboard/tax-firm/settings/matching-rules" 
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors mt-1"
          :class="isActive('/dashboard/tax-firm/settings/matching-rules') ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-700 hover:bg-gray-50 hover:text-indigo-600'"
        >
          <ArrowRightLeft :size="20" :class="isActive('/dashboard/tax-firm/settings/matching-rules') ? 'text-indigo-600' : 'text-gray-400'" />
          消込条件ルール
        </RouterLink>
        <RouterLink 
          to="/dashboard/tax-firm/settings/journal-rules" 
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors mt-1"
          :class="isActive('/dashboard/tax-firm/settings/journal-rules') ? 'bg-indigo-50 text-indigo-700 font-bold' : 'text-gray-700 hover:bg-gray-50 hover:text-indigo-600'"
        >
          <BookText :size="20" :class="isActive('/dashboard/tax-firm/settings/journal-rules') ? 'text-indigo-600' : 'text-gray-400'" />
          自動仕訳ルール
        </RouterLink>

        <button @click="signOut" class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-700 hover:bg-red-50 hover:text-red-600 font-medium transition-colors mt-2">
          <LogOut :size="20" class="text-gray-400 group-hover:text-red-600" />
          ログアウト
        </button>
      </div>
    </nav>

    <div class="p-4 border-t border-gray-200">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold uppercase">
          {{ companyName !== '読込中...' ? companyName.charAt(0) : '-' }}
        </div>
        <div class="overflow-hidden">
          <p class="text-sm font-bold text-gray-900 truncate" :title="companyName">{{ companyName }}</p>
          <p class="text-xs text-gray-500">{{ role }}</p>
        </div>
      </div>
    </div>
  </aside>
</template>
