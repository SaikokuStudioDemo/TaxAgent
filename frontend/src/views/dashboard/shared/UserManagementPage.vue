<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-vue-next';
import UserPermissionList, { UserData } from '@/components/registration/UserPermissionList.vue';
import { useAuth } from '@/composables/useAuth';
import { api } from '@/lib/api';

const route = useRoute();
const { getToken } = useAuth();

const isLoading = ref(true);
const isInvitingId = ref<string | null>(null);
const isDeletingId = ref<string | null>(null);
const errorMsg = ref('');
const successMsg = ref('');

const isTaxFirm = computed(() => route.path.includes('/tax-firm'));

const users = ref<UserData[]>([]);
const departments = ref<any[]>([]);

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const fetchUsers = async () => {
    isLoading.value = true;
    errorMsg.value = '';

    try {
        const token = await getToken();
        if (!token) throw new Error('認証エラー: トークンが見つかりません');

        const res = await fetch(`${apiUrl}/users/employees`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!res.ok) throw new Error('ユーザー情報の取得に失敗しました。');

        const data = await res.json();
        users.value = data.map((emp: any) => ({
            id: emp._id || emp.email,
            name: emp.name,
            email: emp.email,
            role: emp.role || 'staff',
            departmentId: emp.departmentId || '',
            groupId: emp.groupId || '',
            status: 'invited' as const,
            permissions: emp.permissions || { dataProcessing: true, reportExtraction: true },
            usageFee: emp.usageFee,
        }));
    } catch (err: any) {
        console.error('Failed to fetch employees:', err);
        errorMsg.value = err.message || 'データ取得エラーが発生しました。';
    } finally {
        isLoading.value = false;
    }
};

const fetchDepartments = async () => {
    try {
        const data = await api.get<any[]>('/departments');
        departments.value = data.map((d: any) => ({
            id: d.id,
            label: d.name,
            groups: (d.groups || []).map((g: any) => ({ id: g.id, label: g.name }))
        }));
    } catch (e) {
        console.error('Failed to fetch departments', e);
    }
};

onMounted(() => {
    fetchUsers();
    fetchDepartments();
});

const patchUser = async (u: UserData) => {
    const token = await getToken();
    if (!token) return;
    fetch(`${apiUrl}/users/employees/${u.id}`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            role: u.role,
            permissions: u.permissions,
            usageFee: u.usageFee,
            departmentId: u.departmentId,
            groupId: u.groupId,
            bank_display_name: u.bank_display_name,
        }),
    }).catch(() => {});
};

const handleUsersUpdate = (newUsers: UserData[]) => {
    // Find the changed existing user and patch immediately
    const changed = newUsers.find((newU, i) => {
        const oldU = users.value[i];
        return oldU && !newU.id.startsWith('user-') && newU.status === 'invited'
            && JSON.stringify(newU) !== JSON.stringify(oldU);
    });
    users.value = newUsers;
    if (changed) patchUser(changed);
};

const handleSingleInvite = async (userId: string) => {
    isInvitingId.value = userId;
    errorMsg.value = '';
    successMsg.value = '';

    try {
        const token = await getToken();
        if (!token) throw new Error('認証エラー: トークンが見つかりません');

        const targetUser = users.value.find(u => u.id === userId);
        if (!targetUser) return;

        if (!targetUser.email.includes('@')) {
            throw new Error('有効なメールアドレスを入力してください。');
        }

        const res = await fetch(`${apiUrl}/users/employees`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify([targetUser])
        });

        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new Error(errorData.detail || '招待エラーが発生しました。');
        }

        successMsg.value = `${targetUser.name || targetUser.email}さんに招待メールを送信しました。`;
        await fetchUsers();

    } catch (err: any) {
        console.error('Failed to send invite:', err);
        errorMsg.value = err.message || '招待メールの送信に失敗しました。';
    } finally {
        isInvitingId.value = null;
    }
};

const handleDeleteUser = async (userId: string) => {
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
        if (!token) throw new Error('認証エラー: トークンが見つかりません');

        const res = await fetch(`${apiUrl}/users/employees/${userId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            throw new Error(errorData.detail || 'ユーザーの削除に失敗しました。');
        }

        successMsg.value = 'ユーザーを削除しました。';
        await fetchUsers();

    } catch (err: any) {
        console.error('Failed to delete user:', err);
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
        :users="users"
        @update:users="handleUsersUpdate"
        :showUsageFee="false"
        :hidePermissions="isTaxFirm"
        :inlineMode="true"
        :isInvitingId="isInvitingId"
        :isDeletingId="isDeletingId"
        :departments="departments"
        @invite="handleSingleInvite"
        @delete="handleDeleteUser"
      />
    </div>
  </div>
</template>
