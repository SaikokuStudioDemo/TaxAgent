<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { RouterLink } from 'vue-router';
import { useAuth } from '@/composables/useAuth';
import { useAdvisor } from '@/composables/useAdvisor';
import {
  LayoutDashboard,
  Receipt,
  FileText,
  Settings,
  UserCircle,
  Paperclip,
  Image as ImageIcon,
  Mic,
  Send,
  CheckCircle,
  LogOut,
  Users,
  CreditCard,
  Building2,
  ChevronLeft,
  ChevronRight,
  MessageSquareText,
  ArrowRightLeft,
  BookText
} from 'lucide-vue-next';

const isLeftSidebarOpen = ref(true);
const isRightSidebarOpen = ref(true);

const { currentUser, getToken, signOut } = useAuth();
const { messages, isLoading, sendMessage, initChat } = useAdvisor();

const profileName = ref('読込中...');
const role = ref('法人管理者');
const userInput = ref('');

const handleChatSend = () => {
    if (!userInput.value.trim()) return;
    sendMessage(userInput.value);
    userInput.value = '';
};

onMounted(async () => {
    initChat();
    if (!currentUser.value) return;
    try {
        const token = await getToken();
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
        const response = await fetch(`${apiUrl}/users/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            const resData = await response.json();
            if (resData.type === 'corporate') {
                profileName.value = resData.data?.companyName || 'Unknown Company';
                role.value = '法人代表';
            } else if (resData.type === 'employee') {
                profileName.value = resData.data?.name || 'Unknown User';
                role.value = resData.data?.role === 'admin' ? '管理者' : 'スタッフ';
            }
        }
    } catch (err) {
        console.error("Failed to fetch profile", err);
        profileName.value = 'エラー';
    }
});
</script>

<template>
  <div class="flex h-screen bg-gray-50 overflow-hidden font-sans">
    <!-- Left Navigation Sidebar -->
    <aside :class="['bg-slate-900 text-white flex flex-col justify-between flex-shrink-0 relative z-30 shadow-xl transition-all duration-300', isLeftSidebarOpen ? 'w-64' : 'w-20']">
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
        <div class="p-4 border-b border-white/10 flex items-center h-20" :class="isLeftSidebarOpen ? 'justify-start' : 'justify-center'">
          <div class="flex items-center gap-3 overflow-hidden" :class="isLeftSidebarOpen ? 'ml-2' : ''">
            <div class="w-8 h-8 bg-blue-500 rounded flex items-center justify-center shrink-0">
              <div class="w-4 h-4 border-2 border-white grid grid-cols-2 gap-[2px]">
                <div class="bg-white"></div>
                <div></div>
                <div></div>
                <div class="bg-white"></div>
              </div>
            </div>
            <span v-if="isLeftSidebarOpen" class="font-bold text-lg tracking-wide whitespace-nowrap">Tax-Agent</span>
          </div>
        </div>

        <!-- Nav Links -->
        <nav class="flex-1 overflow-y-auto px-3 py-6 space-y-8 no-scrollbar">
          <!-- Summary Section -->
          <div>
            <RouterLink to="/dashboard/corporate" exact-active-class="bg-blue-600 text-white" class="flex items-center gap-3 px-3 py-2.5 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg font-medium transition-colors" :class="{'justify-center': !isLeftSidebarOpen}">
              <LayoutDashboard :size="20" class="shrink-0" />
              <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">サマリー</span>
            </RouterLink>
          </div>

          <!-- Receipts -->
          <div>
            <p v-if="isLeftSidebarOpen" class="px-3 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">領収書</p>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/receipts/upload" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="領収書提出">
                <Receipt :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">領収書提出</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/receipts/approvals" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="領収書承認状況">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">領収書承認状況</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/receipts/matching" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="マッチング確認">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">マッチング確認</span>
              </RouterLink>
            </div>
          </div>

          <!-- Invoices -->
          <div>
            <p v-if="isLeftSidebarOpen" class="px-3 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 mt-4">請求書</p>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/invoices/create" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="請求書発行">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">請求書発行</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/list" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="請求書リスト">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">請求書リスト <span class="text-[10px] text-slate-500 ml-1 block leading-none mt-0.5">発行 / 受領 / 下書き</span></span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/receive" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="受領請求書アップロード">
                <FileText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">受領請求書アップロード</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/approvals" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="受領請求書承認状況">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">受領請求書承認状況</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/invoices/matching" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="マッチング確認 (入金)">
                <CheckCircle :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">マッチング確認 (入金)</span>
              </RouterLink>
            </div>
          </div>

          <!-- Bank & Card Integration -->
          <div>
            <p v-if="isLeftSidebarOpen" class="px-3 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 mt-4">口座・カード連携</p>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/banking/import" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="データアップロード">
                <CreditCard :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">データアップロード</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/ai/training" class="flex items-center gap-3 px-3 py-2 text-emerald-400 hover:text-emerald-300 hover:bg-white/5 rounded-lg transition-colors" active-class="bg-emerald-600/20 text-emerald-300" :class="{'justify-center': !isLeftSidebarOpen}" title="AIトレーニング">
                <Cpu :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">AIトレーニング</span>
              </RouterLink>
            </div>
          </div>

          <!-- Rules -->
          <div>
            <p v-if="isLeftSidebarOpen" class="px-3 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 mt-4">ルール設定</p>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/rules/approvals" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="承認ルール作成">
                <Settings :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">承認ルール作成</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/settings/matching-rules" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="消込条件ルール設定">
                <ArrowRightLeft :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">消込条件ルール</span>
              </RouterLink>

              <RouterLink to="/dashboard/corporate/settings/journal-rules" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="自動仕訳ルール設定">
                <BookText :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">自動仕訳ルール</span>
              </RouterLink>
            </div>
          </div>

          <!-- Settings (User & Organization Management) -->
          <div>
            <p v-if="isLeftSidebarOpen" class="px-3 text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 mt-4">設定</p>
            <div class="space-y-1" :class="{'mt-4': !isLeftSidebarOpen}">
              <RouterLink to="/dashboard/corporate/settings/organization" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="部門・プロジェクト編成">
                <Users :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">部門・プロジェクト編成</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/settings/company" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="自社情報管理">
                <Building2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">自社情報管理</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/settings/clients" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="取引先管理">
                <Building2 :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">取引先管理</span>
              </RouterLink>
              <RouterLink to="/dashboard/corporate/users" class="flex items-center gap-3 px-3 py-2 text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors" active-class="bg-blue-600/20 text-white" :class="{'justify-center': !isLeftSidebarOpen}" title="ユーザー一覧">
                <Users :size="18" class="shrink-0" /> <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">ユーザー一覧</span>
              </RouterLink>
            </div>
          </div>
        </nav>

        <!-- User Profile -->
        <div class="p-4 border-t border-white/10 flex flex-col items-center">
          <div class="flex items-center gap-3 px-2 py-2 cursor-pointer hover:bg-white/5 rounded-lg transition-colors w-full" :class="{'justify-center': !isLeftSidebarOpen}" title="プロフィール設定">
            <UserCircle :size="32" class="text-slate-300 shrink-0" />
            <div class="flex-1 min-w-0" v-if="isLeftSidebarOpen">
              <p class="text-sm font-medium text-white truncate" :title="profileName">{{ profileName !== '読込中...' ? profileName : '...' }}</p>
              <p class="text-xs text-slate-400 truncate">{{ role }}</p>
            </div>
            <Settings :size="16" class="text-slate-400 shrink-0" v-if="isLeftSidebarOpen" />
          </div>
          <button @click="signOut" class="w-full mt-2 flex items-center gap-3 py-2 text-slate-300 hover:text-red-400 hover:bg-white/5 rounded-lg transition-colors text-sm font-medium" :class="isLeftSidebarOpen ? 'px-3' : 'justify-center'" title="ログアウト">
            <LogOut :size="18" class="shrink-0" />
            <span v-if="isLeftSidebarOpen" class="whitespace-nowrap">ログアウト</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- Center Content (Main Dashboard) -->
    <main class="flex-1 flex flex-col min-w-0 bg-[#F5F7FA] relative z-10">

      <div class="flex-1 overflow-y-auto no-scrollbar relative min-h-0 container mx-auto p-4 lg:p-8">
        <router-view />
      </div>
    </main>

    <!-- Right Panel (AI/Chat Assistant) -->
    <aside :class="['bg-white border-l border-gray-200 flex flex-col flex-shrink-0 relative z-30 shadow-sm transition-all duration-300', isRightSidebarOpen ? 'w-[360px]' : 'w-0']">
      <!-- Floating Toggle Right -->
      <button 
        @click="isRightSidebarOpen = !isRightSidebarOpen"
        class="absolute top-8 bg-white border border-gray-200 text-gray-500 hover:text-emerald-600 rounded-full shadow-md z-50 flex items-center justify-center transition-all hover:scale-105"
        :class="!isRightSidebarOpen ? '-left-[64px] w-12 h-12 shadow-lg text-emerald-600 border-none bg-white' : '-left-3 p-1.5 w-8 h-8'"
        :title="isRightSidebarOpen ? 'アシスタントを閉じる' : 'アシスタントを開く'"
      >
        <ChevronRight v-if="isRightSidebarOpen" :size="16" />
        <MessageSquareText v-else :size="20" />
      </button>

      <div class="flex flex-col h-full w-[360px]" :class="!isRightSidebarOpen ? 'overflow-hidden opacity-0' : 'opacity-100 transition-opacity duration-300 delay-100'">
        <div class="p-4 border-b border-gray-100 flex items-center justify-between bg-white h-20 shrink-0">
          <h3 class="font-bold text-gray-800 text-lg flex items-center gap-2">
            <div class="w-2.5 h-2.5 bg-emerald-500 rounded-full animate-pulse"></div>
            アシスタント
          </h3>
        </div>

      <div class="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50/50" ref="chatScrollContainer">
        <div v-for="(msg, i) in messages" :key="i" :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']">
          <div :class="[
            'px-4 py-2.5 rounded-2xl max-w-[85%] text-sm shadow-sm leading-relaxed',
            msg.role === 'user' 
              ? 'bg-blue-600 text-white rounded-tr-sm' 
              : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm'
          ]">
            {{ msg.text }}
          </div>
        </div>
        <div v-if="isLoading" class="flex justify-start">
           <div class="bg-indigo-50 border border-indigo-100 text-indigo-700 px-4 py-3 rounded-2xl rounded-tl-sm text-sm shadow-sm animate-pulse flex items-center gap-2">
              <span class="w-2 h-2 bg-indigo-500 rounded-full animate-bounce"></span>
              思考中...
           </div>
        </div>
      </div>

      <!-- Chat Input Field -->
      <div class="p-4 bg-white border-t border-gray-100">
        <form @submit.prevent="handleChatSend" class="flex items-center bg-gray-100 rounded-full pl-4 pr-1.5 py-1.5 mb-2 focus-within:ring-2 focus-within:ring-blue-500 focus-within:bg-white transition-all shadow-inner">
          <input
            v-model="userInput"
            type="text"
            placeholder="アドバイザーに相談..."
            class="flex-1 bg-transparent border-none focus:ring-0 text-sm min-w-0 py-2 text-gray-700 placeholder-gray-400 outline-none"
          />
          <div class="flex items-center gap-1 text-gray-400 shrink-0">
            <button type="button" class="hover:text-blue-600 transition-colors p-1.5 rounded-full hover:bg-gray-200"><Paperclip :size="16" /></button>
            <button type="submit" :disabled="!userInput.trim() || isLoading" class="bg-blue-600 text-white p-2 rounded-full hover:bg-blue-700 shadow-md ml-1 hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:translate-y-0">
              <Send :size="16" class="ml-0.5" />
            </button>
          </div>
        </form>
        <div class="text-center py-2">
          <button class="text-xs text-blue-600 hover:text-blue-800 font-medium hover:underline">1週間の会話要約を取得する</button>
        </div>
      </div>
      </div>
    </aside>
  </div>
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
