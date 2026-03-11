<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { 
  Building2, 
  Users, 
  Settings, 
  Activity, 
  ShieldAlert,
  BarChart3,
  LogOut
} from 'lucide-vue-next';
import { useAuth } from '@/composables/useAuth';

const route = useRoute();
const { signOut } = useAuth();
const companyName = ref('Tax-Agent 運営局');
const role = ref('特権管理者');

const isActive = (path: string) => {
    if (path === '/dashboard/admin' && route.path === '/dashboard/admin') return true;
    if (path !== '/dashboard/admin' && route.path.startsWith(path)) return true;
    return false;
};
</script>

<template>
  <aside class="w-64 bg-slate-900 border-r border-slate-800 flex flex-col fixed h-full z-10 text-slate-300">
    <div class="p-6 border-b border-slate-800">
      <h1 class="text-xl font-extrabold text-[#38bdf8]">Tax-Agent Admin</h1>
      <p class="text-xs text-slate-500 mt-1">運営局 ダッシュボード</p>
    </div>

    <nav class="flex-1 p-4 space-y-1">
      <RouterLink 
        to="/dashboard/admin" 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors"
        :class="isActive('/dashboard/admin') ? 'bg-slate-800 text-white font-bold' : 'hover:bg-slate-800 hover:text-white'"
      >
        <Activity :size="20" :class="isActive('/dashboard/admin') ? 'text-sky-400' : 'text-slate-500'" />
        プラットフォーム全体
      </RouterLink>
      
      <RouterLink 
        to="#" 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors hover:bg-slate-800 hover:text-white"
      >
        <Building2 :size="20" class="text-slate-500" />
        税理士法人一覧
      </RouterLink>

      <RouterLink 
        to="#" 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors hover:bg-slate-800 hover:text-white"
      >
        <Users :size="20" class="text-slate-500" />
        一般法人一覧
      </RouterLink>

      <RouterLink 
        to="#" 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-colors hover:bg-slate-800 hover:text-white"
      >
        <BarChart3 :size="20" class="text-slate-500" />
        売上・分配金レポート
      </RouterLink>

      <div class="mt-8 pt-6 border-t border-slate-800">
        <h3 class="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">システム管理</h3>
        <a href="#" class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-800 hover:text-white font-medium transition-colors">
          <Settings :size="20" class="text-slate-500" />
          プラン・料金設定
        </a>
        <a href="#" class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-800 hover:text-white font-medium transition-colors">
          <ShieldAlert :size="20" class="text-slate-500" />
          監査ログ
        </a>
        <button @click="signOut" class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:bg-slate-800 hover:text-red-400 font-medium transition-colors mt-2">
          <LogOut :size="20" class="text-slate-500 group-hover:text-red-400" />
          ログアウト
        </button>
      </div>
    </nav>

    <div class="p-4 border-t border-slate-800">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center text-sky-400 font-bold uppercase border border-slate-700">
          A
        </div>
        <div class="overflow-hidden">
          <p class="text-sm font-bold text-white truncate">{{ companyName }}</p>
          <p class="text-xs text-slate-500">{{ role }}</p>
        </div>
      </div>
    </div>
  </aside>
</template>
