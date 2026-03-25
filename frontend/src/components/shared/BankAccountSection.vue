<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Edit2, Trash2, CreditCard, Star, Loader2, Search } from 'lucide-vue-next';
import { useBankAccounts, type BankAccount } from '@/composables/useBankAccounts';

const props = defineProps<{
  ownerType: 'corporate' | 'client';
  profileId?: string;
  clientId?: string;
}>();

const {
  accounts, isLoading,
  fetchBankAccounts, createBankAccount, updateBankAccount, deleteBankAccount,
  setDefaultBankAccount, lookupBank, lookupBranch,
} = useBankAccounts();

onMounted(() => {
  fetchBankAccounts({ profileId: props.profileId, clientId: props.clientId });
});

// Modal state
const isModalOpen = ref(false);
const editingAccountId = ref<string | null>(null);
const isSaving = ref(false);
const isLookingUpBank = ref(false);
const isLookingUpBranch = ref(false);
const bankLookupError = ref('');
const branchLookupError = ref('');

const form = ref({
  bank_code: '',
  bank_name: '',
  branch_code: '',
  branch_name: '',
  account_type: 'ordinary' as 'ordinary' | 'checking',
  account_number: '',
  account_holder: '',
  is_default: false,
});

const resetForm = () => {
  form.value = { bank_code: '', bank_name: '', branch_code: '', branch_name: '', account_type: 'ordinary', account_number: '', account_holder: '', is_default: false };
  bankLookupError.value = '';
  branchLookupError.value = '';
};

const openCreate = () => {
  editingAccountId.value = null;
  resetForm();
  isModalOpen.value = true;
};

const openEdit = (account: BankAccount) => {
  editingAccountId.value = account.id;
  form.value = {
    bank_code: account.bank_code ?? '',
    bank_name: account.bank_name,
    branch_code: account.branch_code ?? '',
    branch_name: account.branch_name,
    account_type: account.account_type,
    account_number: account.account_number,
    account_holder: account.account_holder,
    is_default: account.is_default,
  };
  bankLookupError.value = '';
  branchLookupError.value = '';
  isModalOpen.value = true;
};

const handleBankCodeInput = async () => {
  bankLookupError.value = '';
  const code = form.value.bank_code.trim();
  if (code.length !== 4) return;
  isLookingUpBank.value = true;
  const result = await lookupBank(code);
  isLookingUpBank.value = false;
  if (result) {
    form.value.bank_name = result.bank_name;
    form.value.branch_code = '';
    form.value.branch_name = '';
    branchLookupError.value = '';
  } else {
    bankLookupError.value = '該当する金融機関が見つかりませんでした';
  }
};

const handleBranchCodeInput = async () => {
  branchLookupError.value = '';
  const bankCode = form.value.bank_code.trim();
  const branchCode = form.value.branch_code.trim();
  if (!bankCode || branchCode.length !== 3) return;
  isLookingUpBranch.value = true;
  const result = await lookupBranch(bankCode, branchCode);
  isLookingUpBranch.value = false;
  if (result) {
    form.value.branch_name = result.branch_name;
  } else {
    branchLookupError.value = '該当する支店が見つかりませんでした';
  }
};

const save = async () => {
  isSaving.value = true;
  try {
    if (editingAccountId.value) {
      await updateBankAccount(editingAccountId.value, form.value);
    } else {
      await createBankAccount({
        ...form.value,
        owner_type: props.ownerType,
        profile_id: props.profileId,
        client_id: props.clientId,
      });
    }
    isModalOpen.value = false;
  } finally {
    isSaving.value = false;
  }
};

const remove = async (id: string) => {
  if (confirm('この銀行口座を削除してもよろしいですか？')) {
    await deleteBankAccount(id);
  }
};

const accountTypeLabel = (type: string) => type === 'ordinary' ? '普通' : '当座';
</script>

<template>
  <div>
    <!-- Section Header -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <CreditCard :size="16" class="text-gray-500" />
        <span class="text-sm font-bold text-gray-700">振込先口座</span>
        <span class="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">{{ accounts.length }}件</span>
      </div>
      <button
        @click="openCreate"
        class="text-xs font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-3 py-1 rounded-lg transition-colors flex items-center gap-1"
      >
        <Plus :size="12" /> 口座を追加
      </button>
    </div>

    <!-- List -->
    <div v-if="isLoading" class="text-center text-gray-400 text-sm py-4">読み込み中...</div>
    <div v-else-if="accounts.length === 0" class="text-center text-gray-400 text-sm py-4 border border-dashed border-gray-200 rounded-lg">
      銀行口座が登録されていません
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="account in accounts"
        :key="account.id"
        class="flex items-center justify-between p-3 rounded-lg border transition-colors"
        :class="account.is_default ? 'border-indigo-200 bg-indigo-50/30' : 'border-gray-100 bg-gray-50/50 hover:bg-gray-50'"
      >
        <div class="flex items-center gap-3 min-w-0">
          <div class="shrink-0">
            <span v-if="account.is_default" class="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-600 bg-indigo-100 border border-indigo-200 rounded-full px-2 py-0.5">
              <Star :size="9" /> デフォルト
            </span>
          </div>
          <div class="min-w-0">
            <p class="text-sm font-bold text-gray-800 truncate">
              {{ account.bank_name }} {{ account.branch_name }}
              <span class="font-normal text-gray-500 ml-1">{{ accountTypeLabel(account.account_type) }} {{ account.account_number }}</span>
            </p>
            <p class="text-xs text-gray-500">{{ account.account_holder }}</p>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0 ml-2">
          <button
            v-if="!account.is_default"
            @click="setDefaultBankAccount(account.id)"
            class="text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 px-2 py-1 rounded transition-colors font-medium border border-transparent hover:border-indigo-200"
          >
            デフォルトに設定
          </button>
          <button @click="openEdit(account)" class="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-white rounded transition-colors border border-transparent hover:border-gray-200">
            <Edit2 :size="13" />
          </button>
          <button @click="remove(account.id)" class="p-1.5 text-gray-400 hover:text-red-600 hover:bg-white rounded transition-colors border border-transparent hover:border-gray-200">
            <Trash2 :size="13" />
          </button>
        </div>
      </div>
    </div>

    <!-- Modal (teleported to body to avoid z-index conflicts) -->
    <Teleport to="body">
      <div v-if="isModalOpen" class="fixed inset-0 z-[70] flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-gray-900/50 backdrop-blur-sm" @click="isModalOpen = false"></div>
        <div class="bg-white rounded-xl shadow-xl w-full max-w-md relative z-10 overflow-hidden flex flex-col max-h-[90vh]">
          <div class="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
            <h3 class="text-lg font-bold text-gray-900 flex items-center gap-2">
              <CreditCard :size="18" class="text-indigo-600" />
              {{ editingAccountId ? '銀行口座を編集' : '口座を追加' }}
            </h3>
            <button @click="isModalOpen = false" class="text-gray-400 hover:text-gray-600 text-xl font-bold leading-none">&times;</button>
          </div>

          <div class="p-6 overflow-y-auto space-y-4">
            <!-- Bank Code + Name -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">金融機関コード（4桁）</label>
              <div class="flex gap-2">
                <div class="relative w-28 shrink-0">
                  <input
                    v-model="form.bank_code"
                    type="text"
                    maxlength="4"
                    placeholder="0001"
                    @input="handleBankCodeInput"
                    class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500 pr-8"
                  />
                  <Loader2 v-if="isLookingUpBank" :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                  <Search v-else :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300" />
                </div>
                <input
                  v-model="form.bank_name"
                  type="text"
                  placeholder="銀行名（コード入力で自動補完）"
                  class="flex-1 border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                  :class="{ 'bg-indigo-50 border-indigo-200': form.bank_name && form.bank_code }"
                />
              </div>
              <p v-if="bankLookupError" class="text-xs text-red-500 mt-1">{{ bankLookupError }}</p>
              <p v-else class="text-[10px] text-gray-400 mt-1">コード不明の場合は銀行名を直接入力してください</p>
            </div>

            <!-- Branch Code + Name -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">支店コード（3桁）</label>
              <div class="flex gap-2">
                <div class="relative w-28 shrink-0">
                  <input
                    v-model="form.branch_code"
                    type="text"
                    maxlength="3"
                    placeholder="001"
                    @input="handleBranchCodeInput"
                    :disabled="!form.bank_code"
                    class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500 pr-8 disabled:bg-gray-50 disabled:text-gray-400"
                  />
                  <Loader2 v-if="isLookingUpBranch" :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                  <Search v-else :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300" />
                </div>
                <input
                  v-model="form.branch_name"
                  type="text"
                  placeholder="支店名（コード入力で自動補完）"
                  class="flex-1 border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                  :class="{ 'bg-indigo-50 border-indigo-200': form.branch_name && form.branch_code }"
                />
              </div>
              <p v-if="branchLookupError" class="text-xs text-red-500 mt-1">{{ branchLookupError }}</p>
              <p v-else class="text-[10px] text-gray-400 mt-1">コード不明の場合は支店名を直接入力してください</p>
            </div>

            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">口座種別</label>
              <select v-model="form.account_type" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500">
                <option value="ordinary">普通</option>
                <option value="checking">当座</option>
              </select>
            </div>

            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">口座番号 <span class="text-red-500">*</span></label>
              <input
                v-model="form.account_number"
                type="text"
                placeholder="例: 1234567"
                class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">口座名義 <span class="text-red-500">*</span></label>
              <input
                v-model="form.account_holder"
                type="text"
                placeholder="例: カブシキガイシャタックスエージェント"
                class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            <div class="flex items-center">
              <input id="bankSectionIsDefault" v-model="form.is_default" type="checkbox" class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded" />
              <label for="bankSectionIsDefault" class="ml-2 block text-sm text-gray-900 font-medium">デフォルト口座として使用する</label>
            </div>
          </div>

          <div class="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3 shrink-0">
            <button @click="isModalOpen = false" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors">
              キャンセル
            </button>
            <button
              @click="save"
              :disabled="isSaving || !form.bank_name || !form.branch_name || !form.account_number || !form.account_holder"
              class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm disabled:bg-indigo-300 disabled:cursor-not-allowed"
            >
              {{ editingAccountId ? '保存する' : '追加する' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
