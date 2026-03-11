<script setup lang="ts">
import { ref } from 'vue';
import { Plus, Edit2, Trash2, Building2, CheckCircle } from 'lucide-vue-next';
import { useCompanyProfiles, type CompanyProfile } from '@/composables/useCompanyProfiles';

const { profiles, deleteProfile } = useCompanyProfiles();

// UI state
const isModalOpen = ref(false);
const editingProfileId = ref<string | null>(null);

// Form state
const form = ref<Omit<CompanyProfile, 'id'>>({
  name: '',
  officialName: '',
  address: '',
  phone: '',
  registrationNumber: '',
  bankDetails: '',
  isDefault: false
});

const openCreateModal = () => {
    editingProfileId.value = null;
    form.value = {
        name: '',
        officialName: '',
        address: '',
        phone: '',
        registrationNumber: '',
        bankDetails: '',
        isDefault: false
    };
    isModalOpen.value = true;
};

const openEditModal = (profile: CompanyProfile) => {
    editingProfileId.value = profile.id;
    form.value = { ...profile };
    isModalOpen.value = true;
};

const saveProfile = () => {
    const { updateProfile, addProfile } = useCompanyProfiles();
    
    if (editingProfileId.value) {
        updateProfile(editingProfileId.value, form.value);
    } else {
        addProfile(form.value);
    }
    isModalOpen.value = false;
};

const removeProfile = (id: string) => {
    if (confirm('この自社プロファイルを削除してもよろしいですか？')) {
        deleteProfile(id);
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
        <p class="text-gray-500 mt-2">自社マスター設定 / 請求元プロファイル。本社や支社、別名義など複数の請求元プロファイルを管理できます。</p>
      </div>
      <button @click="openCreateModal" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
        <Plus :size="16" />
        新規プロファイルを作成
      </button>
    </div>

    <!-- Profiles List -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div v-for="profile in profiles" :key="profile.id" class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden flex flex-col group relative hover:border-indigo-300 transition-colors">
            
            <!-- Default Badge -->
            <div v-if="profile.isDefault" class="absolute top-4 right-4 bg-indigo-100 text-indigo-700 text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1 border border-indigo-200">
                <CheckCircle :size="10" /> デフォルト
            </div>

            <!-- Header -->
            <div class="p-5 border-b border-gray-100 bg-gray-50">
                <div class="flex items-center gap-2 mb-1">
                    <Building2 :size="16" class="text-gray-400" />
                    <span class="text-xs font-bold text-gray-500 uppercase tracking-wider">プロファイル名</span>
                </div>
                <h3 class="font-bold text-lg text-gray-900 truncate pr-16">{{ profile.name }}</h3>
            </div>

            <!-- Body -->
            <div class="p-5 flex-1 space-y-4">
                <div>
                    <label class="text-[10px] font-bold text-gray-400 uppercase">会社名 / 屋号</label>
                    <p class="text-sm font-medium text-gray-800">{{ profile.officialName }}</p>
                </div>
                <div>
                    <label class="text-[10px] font-bold text-gray-400 uppercase">登録番号</label>
                    <p class="text-sm font-mono text-gray-600">{{ profile.registrationNumber }}</p>
                </div>
                <div>
                    <label class="text-[10px] font-bold text-gray-400 uppercase">所在地</label>
                    <p class="text-sm text-gray-600 whitespace-pre-line text-xs">{{ profile.address }}</p>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="text-[10px] font-bold text-gray-400 uppercase">電話番号</label>
                        <p class="text-xs text-gray-600">{{ profile.phone }}</p>
                    </div>
                </div>
                <div>
                    <label class="text-[10px] font-bold text-gray-400 uppercase">振込先口座</label>
                    <p class="text-xs text-gray-600 bg-gray-50 p-2 rounded border border-gray-100 mt-1 whitespace-pre-line">{{ profile.bankDetails }}</p>
                </div>
            </div>

            <!-- Footer Actions -->
            <div class="px-4 py-3 bg-gray-50 border-t border-gray-100 flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button @click="openEditModal(profile)" class="p-1.5 text-gray-500 hover:text-indigo-600 hover:bg-white rounded transition-colors shadow-sm border border-transparent hover:border-gray-200">
                    <Edit2 :size="14" />
                </button>
                <button @click="removeProfile(profile.id)" class="p-1.5 text-gray-500 hover:text-red-600 hover:bg-white rounded transition-colors shadow-sm border border-transparent hover:border-gray-200" :disabled="profile.isDefault">
                    <Trash2 :size="14" />
                </button>
            </div>
        </div>
    </div>

    <!-- Modal Form -->
    <div v-if="isModalOpen" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-gray-900/50 backdrop-blur-sm" @click="isModalOpen = false"></div>
        <div class="bg-white rounded-xl shadow-xl w-full max-w-lg relative z-10 overflow-hidden flex flex-col max-h-[90vh]">
            
            <div class="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                <h3 class="text-lg font-bold text-gray-900">{{ editingProfileId ? 'プロファイルを編集' : '新規プロファイルを作成' }}</h3>
                <button @click="isModalOpen = false" class="text-gray-400 hover:text-gray-600 text-xl font-bold leading-none">&times;</button>
            </div>

            <div class="p-6 overflow-y-auto space-y-4">
                <div>
                    <label class="block text-sm font-bold text-gray-700 mb-1">プロファイル表示名 <span class="text-red-500">*</span></label>
                    <input v-model="form.name" type="text" placeholder="例: 本社、関西支社、個人名義" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500" />
                </div>
                
                <div class="pt-2 border-t border-gray-100">
                    <h4 class="text-xs font-bold text-indigo-600 uppercase tracking-wider mb-3">請求書への印字内容</h4>
                    
                    <div class="space-y-4">
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-1">会社名 / 屋号 <span class="text-red-500">*</span></label>
                            <input v-model="form.officialName" type="text" placeholder="株式会社TaxAgent" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500" />
                        </div>
                        
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-1">適格請求書発行事業者登録番号</label>
                            <div class="flex">
                                <span class="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 bg-gray-50 text-gray-500 sm:text-sm font-mono">T</span>
                                <input v-model="form.registrationNumber" type="text" placeholder="1234567890" class="flex-1 block w-full border border-gray-300 rounded-none rounded-r-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 font-mono" />
                            </div>
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-1">所在地</label>
                            <textarea v-model="form.address" rows="2" placeholder="〒150-0000&#10;東京都渋谷区..." class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"></textarea>
                        </div>
                        
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-1">電話番号</label>
                            <input v-model="form.phone" type="text" placeholder="03-0000-0000" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 font-mono" />
                        </div>

                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-1">振込先口座情報</label>
                            <textarea v-model="form.bankDetails" rows="2" placeholder="〇〇銀行 △△支店 普通 1234567 ｶ)ﾀｯｸｽｴｰｼﾞｪﾝﾄ" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"></textarea>
                        </div>
                    </div>
                </div>

                <div class="pt-4 flex items-center">
                    <input id="isDefault" v-model="form.isDefault" type="checkbox" class="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded" />
                    <label for="isDefault" class="ml-2 block text-sm text-gray-900 font-medium">デフォルトの請求元として使用する</label>
                </div>
            </div>

            <div class="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3 shrink-0">
                <button @click="isModalOpen = false" class="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors">キャンセル</button>
                <button @click="saveProfile" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm">
                    {{ editingProfileId ? '保存する' : '作成する' }}
                </button>
            </div>
        </div>
    </div>
  </div>
</template>
