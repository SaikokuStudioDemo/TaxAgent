<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { X, Building2, User, Mail, Phone, MapPin, FileText, CheckCircle2 } from 'lucide-vue-next';
import BankAccountSection from '@/components/shared/BankAccountSection.vue';

const props = defineProps<{
  show: boolean;
  editData?: any; // If editing an existing client
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'save', client: any): void;
}>();

// Form Data - Default structure conforms to what an Invoice Issuer/Recipient needs
const formData = ref({
  id: '',
  name: '',
  companyRegistrationNumber: '',
  department: '',
  contactPerson: '',
  email: '',
  phone: '',
  postalCode: '',
  address: '',
  paymentTerms: '末日締め翌月末払い', // Default terms
  internalNotes: ''
});

const isSaving = ref(false);
const showSuccess = ref(false);

// editData.id が存在する場合（編集モード）のみ銀行口座セクションを表示
const existingClientId = computed(() => props.editData?.id ?? null);

onMounted(() => {
  if (props.editData) {
    formData.value = { ...props.editData };
  } else {
    // Generate mock ID for new clients
    formData.value.id = 'C-' + Math.floor(1000 + Math.random() * 9000);
  }
});

const handleSave = async () => {
  if (!formData.value.name) {
    alert('取引先名（会社名）は必須です。');
    return;
  }

  isSaving.value = true;
  
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 600));
  isSaving.value = false;
  showSuccess.value = true;
  
  // Short delay to show success animation before closing
  setTimeout(() => {
    emit('save', { ...formData.value });
    showSuccess.value = false;
  }, 1000);
};

const handleClose = () => {
  if (!showSuccess.value) {
    emit('close');
  }
};
</script>

<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <!-- Backdrop -->
    <div 
      class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity" 
      @click="handleClose"
    ></div>

    <!-- Modal Content -->
    <div 
      class="bg-white rounded-2xl shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh] relative z-10 transform scale-100 transition-all overflow-hidden"
    >
      <!-- Success State Overlay -->
      <div v-if="showSuccess" class="absolute inset-0 bg-white/95 backdrop-blur z-20 flex flex-col items-center justify-center">
        <div class="w-20 h-20 bg-emerald-100 text-emerald-500 rounded-full flex items-center justify-center mb-6">
          <CheckCircle2 :size="40" />
        </div>
        <h3 class="text-2xl font-bold text-slate-800">取引先を保存しました</h3>
        <p class="text-slate-500 mt-2">{{ formData.name }}</p>
      </div>

      <!-- Header -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-indigo-100 text-indigo-600 rounded-xl flex items-center justify-center">
            <Building2 :size="20" />
          </div>
          <div>
            <h2 class="text-lg font-bold text-slate-800 tracking-tight">{{ editData ? '取引先情報の編集' : '新規取引先の登録' }}</h2>
            <p class="text-xs text-slate-500 font-medium mt-0.5">請求先データのマスターとして利用・自動補完されます</p>
          </div>
        </div>
        <button 
          @click="handleClose" 
          class="text-slate-400 hover:text-slate-600 p-2 hover:bg-slate-100 rounded-full transition-colors"
        >
          <X :size="24" />
        </button>
      </div>

      <!-- Body -->
      <div class="p-6 overflow-y-auto overflow-x-hidden flex-1 custom-scrollbar">
        <div class="space-y-6">
          
          <!-- Basic Company Info -->
          <div>
            <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>基本情報
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="md:col-span-2">
                <label class="block text-sm font-medium text-slate-700 mb-1">取引先名 (会社名) <span class="text-red-500">*</span></label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><Building2 :size="16" /></span>
                  <input type="text" v-model="formData.name" placeholder="例: 株式会社サンプル" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all">
                </div>
              </div>
              
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">法人番号 / 登録番号</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><FileText :size="16" /></span>
                  <input type="text" v-model="formData.companyRegistrationNumber" placeholder="例: T1234567890123" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono">
                </div>
              </div>

              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">支払条件</label>
                <select v-model="formData.paymentTerms" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all">
                  <option value="末日締め翌月末払い">末日締め翌月末払い</option>
                  <option value="末日締め翌々月末払い">末日締め翌々月末払い</option>
                  <option value="20日締め翌月20日払い">20日締め翌月20日払い</option>
                  <option value="都度払い / 前払い">都度払い / 前払い</option>
                  <option value="その他">その他 (備考に記載)</option>
                </select>
              </div>
            </div>
          </div>

          <hr class="border-slate-100">

          <!-- Contact Person -->
          <div>
            <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>担当者・連絡先
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">部署名</label>
                <input type="text" v-model="formData.department" placeholder="例: 経理部" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all">
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">担当者名</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><User :size="16" /></span>
                  <input type="text" v-model="formData.contactPerson" placeholder="例: 山田 太郎" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all">
                </div>
              </div>
              
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">メールアドレス</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><Mail :size="16" /></span>
                  <input type="email" v-model="formData.email" placeholder="例: yamada@example.com" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono">
                </div>
              </div>
              
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">電話番号</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><Phone :size="16" /></span>
                  <input type="tel" v-model="formData.phone" placeholder="例: 03-1234-5678" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono">
                </div>
              </div>
            </div>
          </div>

          <hr class="border-slate-100">

          <!-- Address -->
          <div>
            <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>所在地情報
            </h3>
            <div class="space-y-4">
              <div class="w-1/3">
                <label class="block text-sm font-medium text-slate-700 mb-1">郵便番号</label>
                <input type="text" v-model="formData.postalCode" placeholder="例: 100-0001" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono">
              </div>
              
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">住所</label>
                <div class="relative">
                  <span class="absolute left-3 top-3 text-slate-400"><MapPin :size="16" /></span>
                  <textarea v-model="formData.address" placeholder="都道府県・市区町村・番地・建物名" rows="2" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all resize-none"></textarea>
                </div>
              </div>
            </div>
          </div>

          <hr class="border-slate-100">

          <!-- Internal Notes -->
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">社内用メモ (請求書には印字されません)</label>
            <textarea v-model="formData.internalNotes" placeholder="特記事項や注意事項などがあれば入力..." rows="2" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all resize-none"></textarea>
          </div>

          <!-- Bank Accounts (edit mode only) -->
          <template v-if="existingClientId">
            <hr class="border-slate-100">
            <div>
              <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>振込先口座
              </h3>
              <BankAccountSection owner-type="client" :client-id="existingClientId" />
            </div>
          </template>
          <div v-else class="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-500 text-center">
            取引先を保存後、振込先口座を登録できます。
          </div>

        </div>
      </div>

      <!-- Footer Actions -->
      <div class="px-6 py-4 border-t border-slate-100 bg-slate-50/50 shrink-0 flex items-center justify-end gap-3 rounded-b-2xl">
        <button 
          @click="handleClose" 
          class="px-5 py-2.5 text-sm font-bold text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
        >
          キャンセル
        </button>
        <button 
          @click="handleSave" 
          :disabled="isSaving || !formData.name"
          class="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm disabled:bg-indigo-300 disabled:cursor-not-allowed flex items-center justify-center min-w-[120px]"
        >
          <span v-if="isSaving" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          <span v-else>保存する</span>
        </button>
      </div>

    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: #cbd5e1;
  border-radius: 20px;
}
</style>
