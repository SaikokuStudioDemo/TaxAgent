<script setup lang="ts">
import { ref, computed } from 'vue';
import { Plus, Trash2, Send, Check } from 'lucide-vue-next';
import { APPROVAL_LEVELS } from '@/lib/constants/mockData';

export interface UserData {
  id: string;
  name: string;
  email: string;
  role: string;
  departmentId?: string;
  groupId?: string;
  status: 'draft' | 'invited';
  permissions: {
    dataProcessing: boolean;
    reportExtraction: boolean;
  };
  usageFee?: number;
}

const props = withDefaults(defineProps<{
  users: UserData[];
  showUsageFee?: boolean;
  hidePermissions?: boolean;
  inlineMode?: boolean;
  isInvitingId?: string | null;
  isDeletingId?: string | null;
}>(), {
  showUsageFee: false,
  hidePermissions: false,
  inlineMode: false,
  isInvitingId: null,
  isDeletingId: null
});

const emit = defineEmits<{
  (e: 'update:users', value: UserData[]): void;
  (e: 'invite', userId: string): void;
  (e: 'delete', userId: string): void;
}>();

const bulkFee = ref<string>('');
const isApplied = ref(false);

const handleApplyBulkFee = () => {
  const num = parseInt(bulkFee.value, 10);
  if (!isNaN(num)) {
    const updatedUsers = props.users.map(u => ({ ...u, usageFee: num }));
    emit('update:users', updatedUsers);
    isApplied.value = true;
    setTimeout(() => { isApplied.value = false; }, 3000);
  }
};

const handleAddUser = () => {
  const newUser: UserData = {
    id: `user-${Date.now()}`,
    name: '',
    email: '',
    role: 'staff',
    departmentId: '',
    groupId: '',
    status: 'draft',
    permissions: {
      dataProcessing: false,
      reportExtraction: false,
    },
    usageFee: parseInt(bulkFee.value, 10) || 0
  };
  emit('update:users', [...props.users, newUser]);
};

const handleRemoveUser = (id: string) => {
  if (props.inlineMode) {
    emit('delete', id);
  } else {
    emit('update:users', props.users.filter(u => u.id !== id));
  }
};

const handleUpdateUser = (id: string, field: string, value: string | boolean | number) => {
  const updatedUsers = props.users.map(u => {
    if (u.id === id) {
      if (field.includes('.')) {
        const [parent, child] = field.split('.') as [keyof UserData, string];
        return {
          ...u,
          [parent]: {
            ...(u[parent] as Record<string, unknown>),
            [child]: value
          }
        };
      }
      return { ...u, [field]: value };
    }
    return u;
  });
  emit('update:users', updatedUsers);
};

const handleSendInvite = (id: string) => {
  if (props.inlineMode) {
    emit('invite', id);
  } else {
    alert('※デモ環境のため、実際のメール送信は行われません。ステータスのみが「送信済」に変更されます。');
    const updatedUsers = props.users.map(u => u.id === id ? { ...u, status: 'invited' as const } : u);
    emit('update:users', updatedUsers);
  }
};

const hasEmptyUser = computed(() => {
  return props.users.some(u => u.status === 'draft' && (u.name.trim() === '' || u.email.trim() === ''));
});

// Mock Departments to match OrganizationPage.vue
const DEPARTMENTS = [
  { id: '', label: '未設定 (部門指定なし)' },
  { id: 'dept-1', label: '経営陣', groups: [] },
  { 
    id: 'dept-2', 
    label: '営業部', 
    groups: [
      { id: 'grp-2-1', label: '営業1課' },
      { id: 'grp-2-2', label: '営業2課' }
    ]
  },
  { 
    id: 'dept-3', 
    label: 'システム開発部', 
    groups: [
      { id: 'grp-3-1', label: 'フロントエンドチーム' },
      { id: 'grp-3-2', label: 'バックエンドチーム' }
    ]
  }
];
</script>

<template>
  <section class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
    <div class="flex justify-between items-center mb-6 border-b border-gray-100 pb-4">
      <div>
        <h2 class="text-xl font-bold text-gray-900">ユーザー登録・権限設定</h2>
        <p class="text-sm text-gray-500 mt-1">
          追加ユーザーのログインID(メールアドレス)と権限を設定します。<br />
          ※登録後、各ユーザーにパスワード設定用の招待メールが自動送信されます。
        </p>
      </div>
      <button
        type="button"
        @click="handleAddUser"
        :disabled="hasEmptyUser"
        class="flex items-center gap-2 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 px-4 py-2 rounded-lg font-medium transition-colors border border-indigo-100 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Plus :size="18" />
        ユーザー追加
      </button>
    </div>

    <!-- Bulk Usage Fee Setting -->
    <div v-if="showUsageFee" class="mb-4 p-4 bg-indigo-50 border border-indigo-100 rounded-xl flex items-center justify-between">
      <div>
        <h3 class="text-sm font-bold text-indigo-900">ユーザー利用料の一括設定 (月額)</h3>
        <p class="text-xs text-indigo-700 mt-1">追加する全ユーザーに同じ金額の月額利用料を適用する場合は、こちらに入力して「適用」を押してください。</p>
      </div>
      <div class="flex items-center gap-2">
        <div class="relative">
          <span class="absolute inset-y-0 left-3 flex items-center text-gray-500 font-medium">¥</span>
          <input
            type="text"
            placeholder="0"
            :value="bulkFee"
            @input="bulkFee = ($event.target as HTMLInputElement).value.replace(/[^0-9]/g, '')"
            class="w-40 pl-7 pr-3 py-2 border border-gray-200 rounded-md focus:ring-2 focus:ring-indigo-500 bg-white"
          />
        </div>
        <button
          type="button"
          @click="handleApplyBulkFee"
          :disabled="!bulkFee"
          class="px-4 py-2 rounded-md font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center min-w-[5rem]"
          :class="isApplied ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-indigo-600 text-white hover:bg-indigo-700'"
        >
          <span v-if="isApplied" class="flex items-center justify-center gap-1"><Check :size="16" /> 適用済み</span>
          <span v-else>適用</span>
        </button>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse min-w-[900px]">
        <thead>
          <tr class="bg-gray-50 border-y border-gray-200 text-xs font-semibold text-gray-700">
            <th class="py-3 px-3 w-[22%]">氏名 / ログインID</th>
            <template v-if="!props.hidePermissions">
              <th class="py-3 px-3 w-[15%] whitespace-nowrap">所属部門</th>
              <th class="py-3 px-3 w-[15%] whitespace-nowrap">承認レベル</th>
              <th class="py-3 px-3 w-[11%] text-center whitespace-nowrap">処理権限</th>
              <th class="py-3 px-3 w-[11%] text-center whitespace-nowrap">抽出権限</th>
            </template>
            <th v-if="showUsageFee" class="py-3 px-3 w-[15%] text-right">利用料 (月額)</th>
            <th class="py-3 px-3 w-min text-center min-w-[5rem]">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100 text-sm font-medium">
          <tr v-for="user in users" :key="user.id" class="hover:bg-gray-50/50 transition-colors group">
            <td class="py-3 px-3 align-top">
              <div class="space-y-1.5">
                <input
                  type="text"
                  placeholder="氏名を入力"
                  :value="user.name"
                  @input="handleUpdateUser(user.id, 'name', ($event.target as HTMLInputElement).value)"
                  class="w-full px-3 py-1.5 border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-500 bg-white"
                />
                <input
                  type="email"
                  placeholder="ログインID (メールアドレス)"
                  :value="user.email"
                  @input="handleUpdateUser(user.id, 'email', ($event.target as HTMLInputElement).value)"
                  class="w-full px-3 py-1.5 border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-500 bg-white"
                />
              </div>
            </td>

            <template v-if="!props.hidePermissions">
              <!-- Department & Group Selection -->
              <td class="py-3 px-3 align-top pt-4">
                <div class="space-y-1.5">
                  <select
                    :value="user.departmentId"
                    @change="handleUpdateUser(user.id, 'departmentId', ($event.target as HTMLSelectElement).value); handleUpdateUser(user.id, 'groupId', '')"
                    class="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-500 bg-white text-gray-700 font-medium text-xs"
                  >
                    <option v-for="dept in DEPARTMENTS" :key="dept.id" :value="dept.id">
                      {{ dept.label }}
                    </option>
                  </select>

                  <select
                    v-if="user.departmentId && DEPARTMENTS.find(d => d.id === user.departmentId)?.groups?.length"
                    :value="user.groupId"
                     @change="handleUpdateUser(user.id, 'groupId', ($event.target as HTMLSelectElement).value)"
                    class="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-500 bg-gray-50 text-gray-700 font-medium text-xs"
                  >
                    <option value="">(チームを選択)</option>
                    <option v-for="group in DEPARTMENTS.find(d => d.id === user.departmentId)?.groups" :key="group.id" :value="group.id">
                      {{ group.label }}
                    </option>
                  </select>
                </div>
              </td>

              <!-- Role Selection -->
              <td class="py-3 px-3 align-top pt-4">
                <select
                  :value="user.role"
                  @change="handleUpdateUser(user.id, 'role', ($event.target as HTMLSelectElement).value)"
                  class="w-full px-2 py-1.5 border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-500 bg-white text-gray-700 font-medium text-xs"
                >
                  <option v-for="level in APPROVAL_LEVELS" :key="level.value" :value="level.value">
                    {{ level.label }}
                  </option>
                </select>
              </td>

              <!-- Data Processing Toggle -->
              <td class="py-3 px-3 align-top pt-4 text-center">
                <label class="inline-flex items-center cursor-pointer relative">
                  <input
                    type="checkbox"
                    class="sr-only"
                    :checked="user.permissions.dataProcessing"
                    @change="handleUpdateUser(user.id, 'permissions.dataProcessing', ($event.target as HTMLInputElement).checked)"
                  />
                  <div class="w-9 h-5 rounded-full transition-colors flex items-center px-0.5" :class="user.permissions.dataProcessing ? 'bg-indigo-600' : 'bg-gray-300'">
                    <div class="w-4 h-4 bg-white rounded-full shadow-sm transform transition-transform" :class="user.permissions.dataProcessing ? 'translate-x-4' : 'translate-x-0'"></div>
                  </div>
                </label>
              </td>

              <!-- Report Extraction Toggle -->
              <td class="py-3 px-3 align-top pt-4 text-center">
                <label class="inline-flex items-center cursor-pointer relative">
                  <input
                    type="checkbox"
                    class="sr-only"
                    :checked="user.permissions.reportExtraction"
                    @change="handleUpdateUser(user.id, 'permissions.reportExtraction', ($event.target as HTMLInputElement).checked)"
                  />
                  <div class="w-9 h-5 rounded-full transition-colors flex items-center px-0.5" :class="user.permissions.reportExtraction ? 'bg-emerald-500' : 'bg-gray-300'">
                    <div class="w-4 h-4 bg-white rounded-full shadow-sm transform transition-transform" :class="user.permissions.reportExtraction ? 'translate-x-4' : 'translate-x-0'"></div>
                  </div>
                </label>
              </td>
            </template>

            <!-- Usage Fee (Conditional) -->
            <td v-if="showUsageFee" class="py-3 px-3 align-top pt-4 text-right">
              <div class="relative inline-flex items-center">
                <span class="absolute inset-y-0 left-2 flex items-center text-gray-500 pointer-events-none text-xs">¥</span>
                <input
                  type="text"
                  :value="user.usageFee === 0 ? '' : user.usageFee ?? ''"
                  @input="(e) => {
                    const stripped = (e.target as HTMLInputElement).value.replace(/[^0-9]/g, '');
                    handleUpdateUser(user.id, 'usageFee', parseInt(stripped || '0', 10));
                  }"
                  placeholder="0"
                  class="w-full pl-6 pr-2 py-1 border border-gray-200 rounded-md focus:ring-1 focus:ring-indigo-500 bg-white text-right text-sm"
                />
              </div>
            </td>

            <!-- Action Buttons -->
            <td class="py-3 px-3 align-top pt-3 text-center w-24">
              <div class="flex flex-col gap-1 items-center justify-center">
                <span v-if="user.status === 'invited'" class="flex items-center gap-1 text-xs text-emerald-600 font-bold bg-emerald-50 px-2 py-1 rounded w-full justify-center">
                  <Check :size="14" /> 送信済
                </span>
                <button
                  v-else-if="user.name.trim() !== '' && user.email.trim() !== '' && user.email.includes('@')"
                  type="button"
                  @click="handleSendInvite(user.id)"
                  :disabled="isInvitingId === user.id"
                  class="flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-2 py-1.5 rounded-md transition-colors w-full justify-center font-bold disabled:opacity-50"
                  title="招待メールを送信"
                >
                  <span v-if="isInvitingId === user.id" class="animate-spin w-3 h-3 border-2 border-indigo-600 border-t-transparent rounded-full mr-1"></span>
                  <Send v-else :size="14" /> 
                  {{ isInvitingId === user.id ? '送信中...' : '招待' }}
                </button>
                <button
                  v-else
                  type="button"
                  @click="handleRemoveUser(user.id)"
                  :disabled="isDeletingId === user.id"
                  class="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 hover:bg-red-50 px-2 py-1.5 rounded-md transition-colors w-full justify-center disabled:opacity-50"
                  title="削除"
                >
                  <span v-if="isDeletingId === user.id" class="animate-spin w-3 h-3 border-2 border-red-500 border-t-transparent rounded-full mr-1"></span>
                  <Trash2 v-else :size="16" /> 
                  削除
                </button>

                <!-- Allow deleting invited users too -->
                <button
                  v-if="user.status === 'invited'"
                  type="button"
                  @click="handleRemoveUser(user.id)"
                  :disabled="isDeletingId === user.id"
                  class="text-[10px] text-gray-400 hover:text-red-500 underline mt-1 disabled:opacity-50"
                >
                  {{ isDeletingId === user.id ? '削除中...' : '削除' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="users.length === 0" class="text-center py-8 text-gray-500 bg-gray-50 rounded-lg mt-4 border border-dashed border-gray-200">
        ユーザーが登録されていません。「ユーザー追加」ボタンから追加してください。
      </div>
    </div>
  </section>
</template>
