<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Edit2, Trash2, CreditCard, Star, Loader2 } from 'lucide-vue-next';
import { useBankAccounts, type BankAccount } from '@/composables/useBankAccounts';

const props = defineProps<{
  ownerType: 'corporate' | 'client';
  profileId?: string;
  clientId?: string;
}>();

const {
  accounts, isLoading,
  fetchBankAccounts, createBankAccount, updateBankAccount, deleteBankAccount,
  setDefaultBankAccount, lookupBank, lookupBranch, searchBanks, searchBranches,
} = useBankAccounts();

onMounted(() => {
  fetchBankAccounts({ profileId: props.profileId, clientId: props.clientId });
});

// ---------------------------------------------------------------------------
// フォーム状態
// ---------------------------------------------------------------------------
const isModalOpen = ref(false);
const editingAccountId = ref<string | null>(null);
const isSaving = ref(false);

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

// ---------------------------------------------------------------------------
// 銀行コード入力 → 名前補完
// ---------------------------------------------------------------------------
const isLookingUpBank = ref(false);
const bankCodeError = ref('');

const handleBankCodeInput = async () => {
  bankCodeError.value = '';
  const code = form.value.bank_code.trim();
  if (code.length !== 4) return;
  isLookingUpBank.value = true;
  const result = await lookupBank(code);
  isLookingUpBank.value = false;
  if (result) {
    form.value.bank_name = result.bank_name;
    bankSuggestions.value = [];
    // 銀行が変わったら支店をリセット
    form.value.branch_code = '';
    form.value.branch_name = '';
    branchSuggestions.value = [];
  } else {
    bankCodeError.value = '見つかりません';
  }
};

// ---------------------------------------------------------------------------
// 銀行名インクリメンタルサーチ
// ---------------------------------------------------------------------------
const bankSuggestions = ref<{ code: string; name: string; kana: string }[]>([]);
const isSearchingBank = ref(false);
let bankSearchTimer: ReturnType<typeof setTimeout> | null = null;

const handleBankNameInput = () => {
  const q = form.value.bank_name.trim();
  if (!q || q.length < 1) { bankSuggestions.value = []; return; }
  if (bankSearchTimer) clearTimeout(bankSearchTimer);
  bankSearchTimer = setTimeout(async () => {
    isSearchingBank.value = true;
    bankSuggestions.value = await searchBanks(q);
    isSearchingBank.value = false;
  }, 200);
};

const selectBank = (item: { code: string; name: string }) => {
  form.value.bank_code = item.code;
  form.value.bank_name = item.name;
  bankSuggestions.value = [];
  // 銀行が変わったら支店をリセット
  form.value.branch_code = '';
  form.value.branch_name = '';
  branchSuggestions.value = [];
};

// ---------------------------------------------------------------------------
// 支店コード入力 → 名前補完
// ---------------------------------------------------------------------------
const isLookingUpBranch = ref(false);
const branchCodeError = ref('');

const handleBranchCodeInput = async () => {
  branchCodeError.value = '';
  const bankCode = form.value.bank_code.trim();
  const branchCode = form.value.branch_code.trim();
  if (!bankCode || branchCode.length !== 3) return;
  isLookingUpBranch.value = true;
  const result = await lookupBranch(bankCode, branchCode);
  isLookingUpBranch.value = false;
  if (result) {
    form.value.branch_name = result.branch_name;
    branchSuggestions.value = [];
  } else {
    branchCodeError.value = '見つかりません';
  }
};

// ---------------------------------------------------------------------------
// 支店名インクリメンタルサーチ
// ---------------------------------------------------------------------------
const branchSuggestions = ref<{ code: string; name: string; kana: string }[]>([]);
const isSearchingBranch = ref(false);
let branchSearchTimer: ReturnType<typeof setTimeout> | null = null;

const handleBranchNameInput = () => {
  const bankCode = form.value.bank_code.trim();
  const q = form.value.branch_name.trim();
  if (!bankCode || !q || q.length < 1) { branchSuggestions.value = []; return; }
  if (branchSearchTimer) clearTimeout(branchSearchTimer);
  branchSearchTimer = setTimeout(async () => {
    isSearchingBranch.value = true;
    branchSuggestions.value = await searchBranches(bankCode, q);
    isSearchingBranch.value = false;
  }, 200);
};

const selectBranch = (item: { code: string; name: string }) => {
  form.value.branch_code = item.code;
  form.value.branch_name = item.name;
  branchSuggestions.value = [];
};

// ---------------------------------------------------------------------------
// モーダル開閉
// ---------------------------------------------------------------------------
const resetForm = () => {
  form.value = { bank_code: '', bank_name: '', branch_code: '', branch_name: '', account_type: 'ordinary', account_number: '', account_holder: '', is_default: false };
  bankCodeError.value = '';
  branchCodeError.value = '';
  bankSuggestions.value = [];
  branchSuggestions.value = [];
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
  bankCodeError.value = '';
  branchCodeError.value = '';
  bankSuggestions.value = [];
  branchSuggestions.value = [];
  isModalOpen.value = true;
};

// ---------------------------------------------------------------------------
// 保存 / 削除
// ---------------------------------------------------------------------------
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
      <button @click="openCreate" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-3 py-1 rounded-lg transition-colors flex items-center gap-1">
        <Plus :size="12" /> 口座を追加
      </button>
    </div>

    <!-- Account List -->
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
          <span v-if="account.is_default" class="shrink-0 inline-flex items-center gap-1 text-[10px] font-bold text-indigo-600 bg-indigo-100 border border-indigo-200 rounded-full px-2 py-0.5">
            <Star :size="9" /> デフォルト
          </span>
          <div class="min-w-0">
            <p class="text-sm font-bold text-gray-800 truncate">
              {{ account.bank_name }} {{ account.branch_name }}
              <span class="font-normal text-gray-500 ml-1">{{ accountTypeLabel(account.account_type) }} {{ account.account_number }}</span>
            </p>
            <p class="text-xs text-gray-500">{{ account.account_holder }}</p>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0 ml-2">
          <button v-if="!account.is_default" @click="setDefaultBankAccount(account.id)" class="text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 px-2 py-1 rounded transition-colors font-medium border border-transparent hover:border-indigo-200">
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

    <!-- Modal (Teleported to avoid z-index conflicts) -->
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

          <div class="p-6 overflow-y-auto space-y-5">

            <!-- ── 金融機関 ── -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-2">金融機関</label>
              <div class="flex gap-2">
                <!-- コード入力 -->
                <div class="relative w-28 shrink-0">
                  <input
                    v-model="form.bank_code"
                    type="text" maxlength="4" placeholder="コード"
                    @input="handleBankCodeInput"
                    class="w-full border rounded-lg p-2.5 text-sm font-mono pr-8 focus:ring-indigo-500 focus:border-indigo-500"
                    :class="bankCodeError ? 'border-red-300 bg-red-50' : 'border-gray-300'"
                  />
                  <Loader2 v-if="isLookingUpBank" :size="13" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                </div>
                <!-- 名前入力（サジェスト付き） -->
                <div class="relative flex-1">
                  <input
                    v-model="form.bank_name"
                    type="text" placeholder="銀行名で検索 or 直接入力"
                    @input="handleBankNameInput"
                    class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                    :class="{ 'bg-indigo-50 border-indigo-200': form.bank_name && form.bank_code }"
                  />
                  <Loader2 v-if="isSearchingBank" :size="13" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                  <!-- サジェストドロップダウン -->
                  <ul v-if="bankSuggestions.length" class="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    <li
                      v-for="item in bankSuggestions"
                      :key="item.code"
                      @mousedown.prevent="selectBank(item)"
                      class="flex items-center justify-between px-3 py-2 hover:bg-indigo-50 cursor-pointer text-sm"
                    >
                      <span class="font-medium text-gray-800">{{ item.name }}</span>
                      <span class="text-xs text-gray-400 font-mono ml-2">{{ item.code }}</span>
                    </li>
                  </ul>
                </div>
              </div>
              <p v-if="bankCodeError" class="text-xs text-red-500 mt-1">{{ bankCodeError }}</p>
              <p v-else class="text-[10px] text-gray-400 mt-1">コード（4桁）入力 or 銀行名で検索</p>
            </div>

            <!-- ── 支店 ── -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-2">支店</label>
              <div class="flex gap-2">
                <!-- コード入力 -->
                <div class="relative w-28 shrink-0">
                  <input
                    v-model="form.branch_code"
                    type="text" maxlength="3" placeholder="コード"
                    @input="handleBranchCodeInput"
                    :disabled="!form.bank_code"
                    class="w-full border rounded-lg p-2.5 text-sm font-mono pr-8 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
                    :class="branchCodeError ? 'border-red-300 bg-red-50' : 'border-gray-300'"
                  />
                  <Loader2 v-if="isLookingUpBranch" :size="13" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                </div>
                <!-- 名前入力（サジェスト付き） -->
                <div class="relative flex-1">
                  <input
                    v-model="form.branch_name"
                    type="text" placeholder="支店名で検索 or 直接入力"
                    @input="handleBranchNameInput"
                    :disabled="!form.bank_code"
                    class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
                    :class="{ 'bg-indigo-50 border-indigo-200': form.branch_name && form.branch_code }"
                  />
                  <Loader2 v-if="isSearchingBranch" :size="13" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                  <!-- サジェストドロップダウン -->
                  <ul v-if="branchSuggestions.length" class="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    <li
                      v-for="item in branchSuggestions"
                      :key="item.code"
                      @mousedown.prevent="selectBranch(item)"
                      class="flex items-center justify-between px-3 py-2 hover:bg-indigo-50 cursor-pointer text-sm"
                    >
                      <span class="font-medium text-gray-800">{{ item.name }}</span>
                      <span class="text-xs text-gray-400 font-mono ml-2">{{ item.code }}</span>
                    </li>
                  </ul>
                </div>
              </div>
              <p v-if="branchCodeError" class="text-xs text-red-500 mt-1">{{ branchCodeError }}</p>
              <p v-else class="text-[10px] text-gray-400 mt-1">コード（3桁）入力 or 支店名で検索（銀行選択後）</p>
            </div>

            <!-- ── 口座種別 ── -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">口座種別</label>
              <select v-model="form.account_type" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500">
                <option value="ordinary">普通</option>
                <option value="checking">当座</option>
              </select>
            </div>

            <!-- ── 口座番号 ── -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">口座番号 <span class="text-red-500">*</span></label>
              <input v-model="form.account_number" type="text" placeholder="例: 1234567" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500" />
            </div>

            <!-- ── 口座名義 ── -->
            <div>
              <label class="block text-xs font-bold text-gray-700 mb-1">口座名義 <span class="text-red-500">*</span></label>
              <input v-model="form.account_holder" type="text" placeholder="例: カブシキガイシャタックスエージェント" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500" />
            </div>

            <!-- ── デフォルト ── -->
            <div class="flex items-center gap-2">
              <input id="bankSectionIsDefault" v-model="form.is_default" type="checkbox" class="h-4 w-4 text-indigo-600 border-gray-300 rounded" />
              <label for="bankSectionIsDefault" class="text-sm text-gray-900 font-medium">デフォルト口座として使用する</label>
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
