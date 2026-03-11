<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-vue-next';
import UserPermissionList, { UserData } from '@/components/registration/UserPermissionList.vue';
import { useAuth } from '@/composables/useAuth';

const route = useRoute();
const { getToken } = useAuth();

const isLoading = ref(true);
const isInvitingId = ref<string | null>(null);
const isDeletingId = ref<string | null>(null);
const errorMsg = ref('');
const successMsg = ref('');

// We determine if this is the tax-firm dashboard based on the route URL
const isTaxFirm = computed(() => route.path.includes('/tax-firm'));

const users = ref<UserData[]>([]);

const fetchUsers = async () => {
    isLoading.value = true;
    errorMsg.value = '';
    
    try {
        // 開発用バイパスモードのモックデータ対応
        if (localStorage.getItem('DEV_BYPASS_AUTH') === 'true') {
            await new Promise(resolve => setTimeout(resolve, 500));
            users.value = [
                { id: 'mock-1', name: '山田 太郎', email: 'yamada@example.com', role: 'president', departmentId: 'dept-1', groupId: '', permissions: { dataProcessing: true, reportExtraction: true }, status: 'invited' },
                { id: 'mock-2', name: '佐藤 花子', email: 'sato@example.com', role: 'manager', departmentId: 'dept-2', groupId: '', permissions: { dataProcessing: true, reportExtraction: true }, status: 'invited' },
                { id: 'mock-3', name: '田中 健一', email: 'tanaka@example.com', role: 'group_leader', departmentId: 'dept-2', groupId: 'grp-2-1', permissions: { dataProcessing: true, reportExtraction: false }, status: 'invited' },
                { id: 'mock-4', name: '鈴木 一郎', email: 'suzuki@example.com', role: 'staff', departmentId: 'dept-2', groupId: 'grp-2-1', permissions: { dataProcessing: true, reportExtraction: false }, status: 'invited' },
                { id: 'mock-5', name: '伊藤 美咲', email: 'ito@example.com', role: 'group_leader', departmentId: 'dept-2', groupId: 'grp-2-2', permissions: { dataProcessing: true, reportExtraction: false }, status: 'invited' },
                { id: 'mock-6', name: '渡辺 翔太', email: 'watanabe@example.com', role: 'manager', departmentId: 'dept-3', groupId: '', permissions: { dataProcessing: true, reportExtraction: true }, status: 'invited' },
            ];
            return;
        }

        const token = await getToken();
        if (!token) throw new Error("認証エラー: トークンが見つかりません");
        
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
        const res = await fetch(`${apiUrl}/users/employees`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (!res.ok) {
            throw new Error('ユーザー情報の取得に失敗しました。');
        }
        
        const data = await res.json();
        // Map backend response to frontend UserData format
        users.value = data.map((emp: any) => ({
            id: emp.id || emp.email,
            name: emp.name,
            email: emp.email,
            role: emp.role || 'staff',
            status: 'invited', // existing users are assumed invited/active
            permissions: emp.permissions || { dataProcessing: true, reportExtraction: true }
        }));
    } catch (err: any) {
        console.error("Failed to fetch employees:", err);
        errorMsg.value = err.message || 'データ取得エラーが発生しました。';
    } finally {
        isLoading.value = false;
    }
};

onMounted(() => {
    fetchUsers();
});

const handleSingleInvite = async (userId: string) => {
    isInvitingId.value = userId;
    errorMsg.value = '';
    successMsg.value = '';
    
    try {
        const token = await getToken();
        if (!token) throw new Error("認証エラー: トークンが見つかりません");
        
        const targetUser = users.value.find(u => u.id === userId);
        if (!targetUser) return;
        
        if (!targetUser.email.includes('@')) {
             throw new Error("有効なメールアドレスを入力してください。");
        }

        const payload = [{
            email: targetUser.email,
            name: targetUser.name,
            role: targetUser.role,
            permissions: targetUser.permissions
        }];
        
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
        const res = await fetch(`${apiUrl}/users/employees`, {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new Error(errorData.detail || '招待エラーが発生しました。');
        }
        
        successMsg.value = `${targetUser.name || targetUser.email}さんに招待メールを送信しました。`;
        await fetchUsers(); 
        
    } catch (err: any) {
        console.error("Failed to send invite:", err);
        errorMsg.value = err.message || '招待メールの送信に失敗しました。';
    } finally {
        isInvitingId.value = null;
    }
};

const handleDeleteUser = async (userId: string) => {
    
    // If it's a draft user (not yet saved to DB), just remove it from UI array immediately
    if (userId.startsWith('user-')) {
        users.value = users.value.filter(u => u.id !== userId);
        return;
    }

    if (!confirm('このユーザーを完全に削除します。よろしいですか？')) return;

    isDeletingId.value = userId;
    errorMsg.value = '';
    successMsg.value = '';
    
    try {
        const token = await getToken();
        if (!token) throw new Error("認証エラー: トークンが見つかりません");
        
        const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";
        const res = await fetch(`${apiUrl}/users/employees/${userId}`, {
            method: 'DELETE',
            headers: { 
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new Error(errorData.detail || 'ユーザーの削除に失敗しました。');
        }
        
        successMsg.value = 'ユーザーを削除しました。';
        await fetchUsers(); 
        
    } catch (err: any) {
        console.error("Failed to delete user:", err);
        errorMsg.value = err.message || '削除エラーが発生しました。';
    } finally {
        isDeletingId.value = null;
    }
};

</script>

<template>
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 border-b border-gray-200 pb-5">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">ユーザー一覧・追加</h1>
        <p class="text-sm text-gray-500 mt-1">所属メンバーの管理と、ツールを利用するための権限設定を行います。</p>
      </div>
    </div>

    <!-- Feedback messages -->
    <div v-if="errorMsg" class="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3 text-red-700">
      <AlertCircle class="shrink-0 mt-0.5" :size="20" />
      <p class="text-sm font-medium">{{ errorMsg }}</p>
    </div>
    
    <div v-if="successMsg" class="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-start gap-3 text-emerald-700">
      <CheckCircle2 class="shrink-0 mt-0.5" :size="20" />
      <p class="text-sm font-medium">{{ successMsg }}</p>
    </div>
    
    <!-- Loading State -->
    <div v-if="isLoading" class="flex flex-col items-center justify-center py-20 text-indigo-500 gap-4">
      <Loader2 class="animate-spin" :size="40" />
      <p class="font-medium">ユーザー情報を読み込み中...</p>
    </div>

    <!-- Content -->
    <div v-else class="pb-10">
      <UserPermissionList 
        v-model:users="users"
        :showUsageFee="false"
        :hidePermissions="isTaxFirm"
        :inlineMode="true"
        :isInvitingId="isInvitingId"
        :isDeletingId="isDeletingId"
        @invite="handleSingleInvite"
        @delete="handleDeleteUser"
      />
    </div>
  </div>
</template>
