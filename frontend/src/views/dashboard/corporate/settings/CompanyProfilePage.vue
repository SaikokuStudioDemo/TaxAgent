<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Edit2, Trash2, Building2, CheckCircle, CreditCard, Star, Loader2, Search } from 'lucide-vue-next';
import { useCompanyProfiles, type CompanyProfile } from '@/composables/useCompanyProfiles';
import { useBankAccounts, type BankAccount } from '@/composables/useBankAccounts';

const { profiles, isLoading: profilesLoading, fetchProfiles, createProfile, updateProfile, deleteProfile } = useCompanyProfiles();
const { accounts, isLoading: accountsLoading, fetchBankAccounts, createBankAccount, updateBankAccount, deleteBankAccount, setDefaultBankAccount, lookupBank, lookupBranch } = useBankAccounts();

// Profile modal state
const isProfileModalOpen = ref(false);
const editingProfileId = ref<string | null>(null);
const isSavingProfile = ref(false);

const profileForm = ref({
  profile_name: '',
  company_name: '',
  phone: '',
  address: '',
  registration_number: '',
  is_default: false,
});

// Bank account modal state
const isBankModalOpen = ref(false);
const editingAccountId = ref<string | null>(null);
const currentProfileId = ref<string | null>(null);
const isSavingAccount = ref(false);
const isLookingUpBank = ref(false);
const isLookingUpBranch = ref(false);
const bankLookupError = ref('');
const branchLookupError = ref('');

const bankForm = ref({
  bank_code: '',
  bank_name: '',
  branch_code: '',
  branch_name: '',
  account_type: 'ordinary' as 'ordinary' | 'checking',
  account_number: '',
  account_holder: '',
  is_default: false,
});

const handleBankCodeInput = async () => {
  bankLookupError.value = '';
  const code = bankForm.value.bank_code.trim();
  if (code.length !== 4) return;
  isLookingUpBank.value = true;
  const result = await lookupBank(code);
  isLookingUpBank.value = false;
  if (result) {
    bankForm.value.bank_name = result.bank_name;
    // Reset branch when bank changes
    bankForm.value.branch_code = '';
    bankForm.value.branch_name = '';
    branchLookupError.value = '';
  } else {
    bankLookupError.value = '該当する金融機関が見つかりませんでした';
  }
};

const handleBranchCodeInput = async () => {
  branchLookupError.value = '';
  const bankCode = bankForm.value.bank_code.trim();
  const branchCode = bankForm.value.branch_code.trim();
  if (!bankCode || branchCode.length !== 3) return;
  isLookingUpBranch.value = true;
  const result = await lookupBranch(bankCode, branchCode);
  isLookingUpBranch.value = false;
  if (result) {
    bankForm.value.branch_name = result.branch_name;
  } else {
    branchLookupError.value = '該当する支店が見つかりませんでした';
  }
};

onMounted(async () => {
  await fetchProfiles();
  await fetchBankAccounts();
});

const accountsForProfile = (profileId: string) =>
  accounts.value.filter(a => a.profile_id === profileId);

const accountTypeLabel = (type: string) => type === 'ordinary' ? '普通' : '当座';

// Profile actions
const openCreateProfileModal = () => {
  editingProfileId.value = null;
  profileForm.value = { profile_name: '', company_name: '', phone: '', address: '', registration_number: '', is_default: false };
  isProfileModalOpen.value = true;
};

const openEditProfileModal = (profile: CompanyProfile) => {
  editingProfileId.value = profile.id;
  profileForm.value = {
    profile_name: profile.profile_name,
    company_name: profile.company_name,
    phone: profile.phone ?? '',
    address: profile.address ?? '',
    registration_number: profile.registration_number ?? '',
    is_default: profile.is_default,
  };
  isProfileModalOpen.value = true;
};

const saveProfile = async () => {
  isSavingProfile.value = true;
  try {
    const data = {
      profile_name: profileForm.value.profile_name,
      company_name: profileForm.value.company_name,
      phone: profileForm.value.phone || undefined,
      address: profileForm.value.address || undefined,
      registration_number: profileForm.value.registration_number || undefined,
      is_default: profileForm.value.is_default,
    };
    if (editingProfileId.value) {
      await updateProfile(editingProfileId.value, data);
    } else {
      await createProfile(data as Omit<CompanyProfile, 'id'>);
    }
    isProfileModalOpen.value = false;
  } finally {
    isSavingProfile.value = false;
  }
};

const removeProfile = async (id: string) => {
  if (confirm('この自社プロファイルを削除してもよろしいですか？')) {
    await deleteProfile(id);
  }
};

// Bank account actions
const openCreateBankModal = (profileId: string) => {
  currentProfileId.value = profileId;
  editingAccountId.value = null;
  bankForm.value = { bank_code: '', bank_name: '', branch_code: '', branch_name: '', account_type: 'ordinary', account_number: '', account_holder: '', is_default: false };
  bankLookupError.value = '';
  branchLookupError.value = '';
  isBankModalOpen.value = true;
};

const openEditBankModal = (account: BankAccount) => {
  currentProfileId.value = account.profile_id ?? null;
  editingAccountId.value = account.id;
  bankForm.value = {
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
  isBankModalOpen.value = true;
};

const saveBankAccount = async () => {
  if (!currentProfileId.value) return;
  isSavingAccount.value = true;
  try {
    if (editingAccountId.value) {
      await updateBankAccount(editingAccountId.value, bankForm.value);
    } else {
      await createBankAccount({ ...bankForm.value, profile_id: currentProfileId.value });
    }
    isBankModalOpen.value = false;
  } finally {
    isSavingAccount.value = false;
  }
};

const removeAccount = async (id: string) => {
  if (confirm('この銀行口座を削除してもよろしいですか？')) {
    await deleteBankAccount(id);
  }
};

const handleSetDefault = async (id: string) => {
  await setDefaultBankAccount(id);
};
</script>

<template>
  <div class="max-w-6xl mx-auto p-4 sm:p-8">
    <div class="mb-8 flex justify-between items-end">
      <div>
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Building2 :size="24" class="text-indigo-600" />
          自社情報管理
        </h1>
        <p class="text-gray-500 mt-2">自社マスター設定 / 請求元プロファイル。本社や支社、別名義など複数の請求元プロファイルと銀行口座を管理できます。</p>
      </div>
      <button @click="openCreateProfileModal" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
        <Plus :size="16" />
        新規プロファイルを作成
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="profilesLoading" class="text-center text-gray-400 py-16">読み込み中...</div>

    <!-- Profiles List -->
    <div v-else class="space-y-6">
      <div
        v-for="profile in profiles"
        :key="profile.id"
        class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden hover:border-indigo-300 transition-colors"
      >
        <!-- Profile Header -->
        <div class="p-5 border-b border-gray-100 bg-gray-50 flex items-start justify-between">
          <div class="flex items-center gap-3">
            <Building2 :size="20" class="text-gray-400 shrink-0" />
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-lg text-gray-900">{{ profile.profile_name }}</h3>
                <span v-if="profile.is_default" class="bg-indigo-100 text-indigo-700 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1 border border-indigo-200">
                  <CheckCircle :size="10" /> デフォルト
                </span>
              </div>
              <p class="text-sm text-gray-600 font-medium">{{ profile.company_name }}</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button @click="openEditProfileModal(profile)" class="p-1.5 text-gray-500 hover:text-indigo-600 hover:bg-white rounded transition-colors shadow-sm border border-transparent hover:border-gray-200">
              <Edit2 :size="14" />
            </button>
            <button @click="removeProfile(profile.id)" class="p-1.5 text-gray-500 hover:text-red-600 hover:bg-white rounded transition-colors shadow-sm border border-transparent hover:border-gray-200" :disabled="profile.is_default">
              <Trash2 :size="14" />
            </button>
          </div>
        </div>

        <!-- Profile Details -->
        <div class="p-5 grid grid-cols-1 md:grid-cols-3 gap-4 border-b border-gray-100">
          <div>
            <label class="text-[10px] font-bold text-gray-400 uppercase">登録番号</label>
            <p class="text-sm font-mono text-gray-600">{{ profile.registration_number || '—' }}</p>
          </div>
          <div>
            <label class="text-[10px] font-bold text-gray-400 uppercase">電話番号</label>
            <p class="text-sm text-gray-600">{{ profile.phone || '—' }}</p>
          </div>
          <div>
            <label class="text-[10px] font-bold text-gray-400 uppercase">所在地</label>
            <p class="text-sm text-gray-600 text-xs">{{ profile.address || '—' }}</p>
          </div>
        </div>

        <!-- Bank Accounts Section -->
        <div class="p-5">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <CreditCard :size="16" class="text-gray-500" />
              <span class="text-sm font-bold text-gray-700">振込先口座</span>
              <span class="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">{{ accountsForProfile(profile.id).length }}件</span>
            </div>
            <button @click="openCreateBankModal(profile.id)" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-3 py-1 rounded-lg transition-colors flex items-center gap-1">
              <Plus :size="12" /> 口座を追加
            </button>
          </div>

          <div v-if="accountsLoading" class="text-center text-gray-400 text-sm py-4">読み込み中...</div>
          <div v-else-if="accountsForProfile(profile.id).length === 0" class="text-center text-gray-400 text-sm py-4 border border-dashed border-gray-200 rounded-lg">
            銀行口座が登録されていません
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="account in accountsForProfile(profile.id)"
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
                <button v-if="!account.is_default" @click="handleSetDefault(account.id)" class="text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 px-2 py-1 rounded transition-colors font-medium border border-transparent hover:border-indigo-200">
                  デフォルトに設定
                </button>
                <button @click="openEditBankModal(account)" class="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-white rounded transition-colors border border-transparent hover:border-gray-200">
                  <Edit2 :size="13" />
                </button>
                <button @click="removeAccount(account.id)" class="p-1.5 text-gray-400 hover:text-red-600 hover:bg-white rounded transition-colors border border-transparent hover:border-gray-200">
                  <Trash2 :size="13" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Profile Modal -->
    <div v-if="isProfileModalOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-gray-900/50 backdrop-blur-sm" @click="isProfileModalOpen = false"></div>
      <div class="bg-white rounded-xl shadow-xl w-full max-w-lg relative z-10 overflow-hidden flex flex-col max-h-[90vh]">
        <div class="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
          <h3 class="text-lg font-bold text-gray-900">{{ editingProfileId ? 'プロファイルを編集' : '新規プロファイルを作成' }}</h3>
          <button @click="isProfileModalOpen = false" class="text-gray-400 hover:text-gray-600 text-xl font-bold leading-none">&times;</button>
        </div>
        <div class="p-6 overflow-y-auto space-y-4">
          <div>
            <label class="block text-sm font-bold text-gray-700 mb-1">プロファイル表示名 <span class="text-red-500">*</span></label>
            <input v-model="profileForm.profile_name" type="text" placeholder="例: 本社、関西支社" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500" />
          </div>
          <div class="pt-2 border-t border-gray-100">
            <h4 class="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-3">請求書への印字内容</h4>
            <div class="space-y-4">
              <div>
                <label class="block text-xs font-bold text-gray-700 mb-1">会社名 / 屋号 <span class="text-red-500">*</span></label>
                <input v-model="profileForm.company_name" type="text" placeholder="株式会社TaxAgent" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500" />
              </div>
              <div>
                <label class="block text-xs font-bold text-gray-700 mb-1">適格請求書発行事業者登録番号</label>
                <div class="flex">
                  <span class="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 bg-gray-50 text-gray-500 sm:text-sm font-mono">T</span>
                  <input v-model="profileForm.registration_number" type="text" placeholder="1234567890" class="flex-1 block w-full border border-gray-300 rounded-none rounded-r-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 font-mono" />
                </div>
              </div>
              <div>
                <label class="block text-xs font-bold text-gray-700 mb-1">所在地</label>
                <textarea v-model="profileForm.address" rows="2" placeholder="〒150-0000&#10;東京都渋谷区..." class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"></textarea>
              </div>
              <div>
                <label class="block text-xs font-bold text-gray-700 mb-1">電話番号</label>
                <input v-model="profileForm.phone" type="text" placeholder="03-0000-0000" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 font-mono" />
              </div>
            </div>
          </div>
          <div class="pt-4 flex items-center">
            <input id="isDefault" v-model="profileForm.is_default" type="checkbox" class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded" />
            <label for="isDefault" class="ml-2 block text-sm text-gray-900 font-medium">デフォルトの請求元として使用する</label>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3 shrink-0">
          <button @click="isProfileModalOpen = false" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors">キャンセル</button>
          <button @click="saveProfile" :disabled="isSavingProfile || !profileForm.profile_name || !profileForm.company_name" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm disabled:bg-indigo-300 disabled:cursor-not-allowed">
            {{ editingProfileId ? '保存する' : '作成する' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Bank Account Modal -->
    <div v-if="isBankModalOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-gray-900/50 backdrop-blur-sm" @click="isBankModalOpen = false"></div>
      <div class="bg-white rounded-xl shadow-xl w-full max-w-md relative z-10 overflow-hidden flex flex-col max-h-[90vh]">
        <div class="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
          <h3 class="text-lg font-bold text-gray-900 flex items-center gap-2">
            <CreditCard :size="18" class="text-indigo-600" />
            {{ editingAccountId ? '銀行口座を編集' : '口座を追加' }}
          </h3>
          <button @click="isBankModalOpen = false" class="text-gray-400 hover:text-gray-600 text-xl font-bold leading-none">&times;</button>
        </div>
        <div class="p-6 overflow-y-auto space-y-4">
          <!-- Bank Code + Name -->
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">金融機関コード（4桁）</label>
            <div class="flex gap-2">
              <div class="relative w-28 shrink-0">
                <input
                  v-model="bankForm.bank_code"
                  type="text"
                  maxlength="4"
                  placeholder="0001"
                  @input="handleBankCodeInput"
                  class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500 pr-8"
                />
                <Loader2 v-if="isLookingUpBank" :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                <Search v-else :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300" />
              </div>
              <div class="flex-1">
                <input
                  v-model="bankForm.bank_name"
                  type="text"
                  placeholder="銀行名（コード入力で自動補完）"
                  class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                  :class="{ 'bg-indigo-50 border-indigo-200': bankForm.bank_name && bankForm.bank_code }"
                />
              </div>
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
                  v-model="bankForm.branch_code"
                  type="text"
                  maxlength="3"
                  placeholder="001"
                  @input="handleBranchCodeInput"
                  :disabled="!bankForm.bank_code"
                  class="w-full border border-gray-300 rounded-lg p-2.5 text-sm font-mono focus:ring-indigo-500 focus:border-indigo-500 pr-8 disabled:bg-gray-50 disabled:text-gray-400"
                />
                <Loader2 v-if="isLookingUpBranch" :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-indigo-400 animate-spin" />
                <Search v-else :size="14" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300" />
              </div>
              <div class="flex-1">
                <input
                  v-model="bankForm.branch_name"
                  type="text"
                  placeholder="支店名（コード入力で自動補完）"
                  class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                  :class="{ 'bg-indigo-50 border-indigo-200': bankForm.branch_name && bankForm.branch_code }"
                />
              </div>
            </div>
            <p v-if="branchLookupError" class="text-xs text-red-500 mt-1">{{ branchLookupError }}</p>
            <p v-else class="text-[10px] text-gray-400 mt-1">コード不明の場合は支店名を直接入力してください</p>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">口座種別</label>
            <select v-model="bankForm.account_type" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500">
              <option value="ordinary">普通</option>
              <option value="checking">当座</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">口座番号 <span class="text-red-500">*</span></label>
            <input v-model="bankForm.account_number" type="text" placeholder="例: 1234567" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 font-mono" />
          </div>
          <div>
            <label class="block text-xs font-bold text-gray-700 mb-1">口座名義 <span class="text-red-500">*</span></label>
            <input v-model="bankForm.account_holder" type="text" placeholder="例: カブシキガイシャタックスエージェント" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 font-mono" />
          </div>
          <div class="flex items-center">
            <input id="bankIsDefault" v-model="bankForm.is_default" type="checkbox" class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded" />
            <label for="bankIsDefault" class="ml-2 block text-sm text-gray-900 font-medium">デフォルト口座として使用する</label>
          </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3 shrink-0">
          <button @click="isBankModalOpen = false" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors">キャンセル</button>
          <button
            @click="saveBankAccount"
            :disabled="isSavingAccount || !bankForm.bank_name || !bankForm.branch_name || !bankForm.account_number || !bankForm.account_holder"
            class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm disabled:bg-indigo-300 disabled:cursor-not-allowed"
          >
            {{ editingAccountId ? '保存する' : '追加する' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
