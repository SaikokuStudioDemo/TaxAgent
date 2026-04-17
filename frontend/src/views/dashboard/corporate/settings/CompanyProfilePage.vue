<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Edit2, Trash2, Building2, CheckCircle, Link, AlertTriangle } from 'lucide-vue-next';
import { useCompanyProfiles, type CompanyProfile } from '@/composables/useCompanyProfiles';
import BankAccountSection from '@/components/shared/BankAccountSection.vue';
import { useAuth } from '@/composables/useAuth';
import { api } from '@/lib/api';

const { profiles, isLoading: profilesLoading, fetchProfiles, createProfile, updateProfile, deleteProfile } = useCompanyProfiles();
const { userProfile, getToken, isAdmin, signOut } = useAuth();

// ── 解約機能 ──────────────────────────────────────────────────────────────
const showCancelDialog = ref(false);
const isCancelling = ref(false);
const cancelError = ref<string | null>(null);

const handleCancel = async () => {
  isCancelling.value = true;
  cancelError.value = null;
  try {
    await api.post('/users/cancel', {});
    // 解約成功 → 即座にログアウトしてトップページへ
    await signOut();
  } catch (e: any) {
    cancelError.value = e.message ?? '解約処理に失敗しました。もう一度お試しください。';
    isCancelling.value = false;
  }
};

// 税理士法人との紐付けリクエスト
const taxFirmEmail = ref('');
const isRequestingLinkage = ref(false);
const linkageRequestSent = ref(false);

const requestLinkage = async () => {
  if (!taxFirmEmail.value) return;
  isRequestingLinkage.value = true;
  try {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
    const token = await getToken();
    const res = await fetch(`${apiUrl}/invitations/linkage-request`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ tax_firm_email: taxFirmEmail.value })
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.detail || 'エラーが発生しました');
      return;
    }
    linkageRequestSent.value = true;
  } finally {
    isRequestingLinkage.value = false;
  }
};

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

onMounted(fetchProfiles);

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
          <BankAccountSection owner-type="corporate" :profile-id="profile.id" />
        </div>
      </div>
    </div>

    <!-- 税理士法人との連携セクション（未紐付けの場合のみ表示） -->
    <div v-if="userProfile && !userProfile.advising_tax_firm_id" class="mt-10 bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div class="p-5 border-b border-gray-100 bg-gray-50 flex items-center gap-3">
        <Link :size="20" class="text-indigo-500 shrink-0" />
        <div>
          <h3 class="font-bold text-gray-900">税理士法人との連携</h3>
          <p class="text-sm text-gray-500 mt-0.5">担当税理士法人のメールアドレスを入力すると、承認リクエストを送信します。税理士法人が承認するとデータの共有が開始されます。</p>
        </div>
      </div>
      <div class="p-5">
        <div v-if="linkageRequestSent" class="flex items-start gap-3 p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-sm text-emerald-700">
          <CheckCircle :size="18" class="shrink-0 mt-0.5" />
          <p>承認リクエストを送信しました。税理士法人からの承認をお待ちください。</p>
        </div>
        <div v-else class="flex gap-3">
          <input
            v-model="taxFirmEmail"
            type="email"
            placeholder="tax-firm@example.com"
            class="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
          />
          <button
            @click="requestLinkage"
            :disabled="isRequestingLinkage || !taxFirmEmail"
            class="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {{ isRequestingLinkage ? '送信中...' : '連携リクエストを送信する' }}
          </button>
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
  </div>

  <!-- ══════════════════════════════════════════════════════ -->
  <!-- 危険ゾーン（admin のみ表示）                             -->
  <!-- ══════════════════════════════════════════════════════ -->
  <div v-if="isAdmin" class="max-w-4xl mx-auto px-6 pb-10">
    <div class="border border-red-200 rounded-xl overflow-hidden">
      <div class="bg-red-50 px-6 py-4 flex items-center gap-2 border-b border-red-200">
        <AlertTriangle class="text-red-500 shrink-0" :size="18" />
        <h2 class="text-base font-bold text-red-700">危険ゾーン</h2>
      </div>
      <div class="px-6 py-5 bg-white">
        <div class="flex items-start justify-between gap-6">
          <div>
            <p class="text-sm font-semibold text-slate-800">サービスの解約</p>
            <p class="text-xs text-slate-500 mt-1">
              解約すると、サービスへのアクセスができなくなります。データは保持されます。
            </p>
          </div>
          <button
            @click="showCancelDialog = true"
            class="shrink-0 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 transition-colors"
          >
            サービスを解約する
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- ── 解約確認ダイアログ ───────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="showCancelDialog"
      class="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
    >
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
        <div class="flex items-center gap-3 mb-4">
          <div class="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
            <AlertTriangle class="text-red-600" :size="20" />
          </div>
          <h3 class="text-lg font-bold text-slate-800">本当に解約しますか？</h3>
        </div>

        <ul class="text-sm text-slate-600 space-y-2 mb-5 ml-2">
          <li class="flex items-start gap-2">
            <span class="text-red-400 mt-0.5">・</span>
            サービスへのアクセスができなくなります
          </li>
          <li class="flex items-start gap-2">
            <span class="text-slate-400 mt-0.5">・</span>
            データは保持されます
          </li>
          <li class="flex items-start gap-2">
            <span class="text-slate-400 mt-0.5">・</span>
            再契約はサポートにお問い合わせください
          </li>
        </ul>

        <div v-if="cancelError" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
          {{ cancelError }}
        </div>

        <div class="flex gap-3 justify-end">
          <button
            @click="showCancelDialog = false; cancelError = null"
            :disabled="isCancelling"
            class="px-4 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors"
          >
            キャンセル
          </button>
          <button
            @click="handleCancel"
            :disabled="isCancelling"
            class="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-40 transition-colors"
          >
            {{ isCancelling ? '処理中...' : '解約する' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
