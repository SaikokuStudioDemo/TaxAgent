<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { X, Building2, User, Mail, Phone, MapPin, FileText, CheckCircle2, CreditCard } from 'lucide-vue-next';
import BankAccountSection from '@/components/shared/BankAccountSection.vue';
import { useClients } from '@/composables/useClients';

const props = defineProps<{
  show: boolean;
  editData?: any;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'saved'): void;
}>();

const { createClient, updateClient } = useClients();

const isEditing = computed(() => !!props.editData?.id);

// ── 新規作成: 2ステップウィザード ──
const step = ref<'form' | 'banks'>('form');
const newClientId = ref<string | null>(null);
const newClientName = ref('');

// ── 編集: タブ ──
const activeTab = ref<'info' | 'banks'>('info');

// ── フォームデータ ──
const formData = ref({
  name: '',
  companyRegistrationNumber: '',
  department: '',
  contactPerson: '',
  email: '',
  phone: '',
  postalCode: '',
  address: '',
  paymentTerms: '末日締め翌月末払い',
  internalNotes: '',
});

const isSaving = ref(false);
const saveSuccess = ref(false);
const errorMsg = ref('');

// モーダルが開くたびにリセット
watch(() => props.show, (val) => {
  if (!val) return;
  step.value = 'form';
  newClientId.value = null;
  newClientName.value = '';
  activeTab.value = 'info';
  saveSuccess.value = false;
  errorMsg.value = '';
  formData.value = props.editData
    ? {
        name: props.editData.name ?? '',
        companyRegistrationNumber: props.editData.companyRegistrationNumber ?? '',
        department: props.editData.department ?? '',
        contactPerson: props.editData.contactPerson ?? '',
        email: props.editData.email ?? '',
        phone: props.editData.phone ?? '',
        postalCode: props.editData.postalCode ?? '',
        address: props.editData.address ?? '',
        paymentTerms: props.editData.paymentTerms ?? '末日締め翌月末払い',
        internalNotes: props.editData.internalNotes ?? '',
      }
    : { name: '', companyRegistrationNumber: '', department: '', contactPerson: '',
        email: '', phone: '', postalCode: '', address: '',
        paymentTerms: '末日締め翌月末払い', internalNotes: '' };
});

const buildPayload = () => ({
  name: formData.value.name,
  registration_number: formData.value.companyRegistrationNumber,
  department: formData.value.department,
  contact_person: formData.value.contactPerson,
  email: formData.value.email,
  phone: formData.value.phone,
  postal_code: formData.value.postalCode,
  address: formData.value.address,
  payment_terms: formData.value.paymentTerms,
  internal_notes: formData.value.internalNotes,
});

const handleSave = async () => {
  if (!formData.value.name) {
    errorMsg.value = '取引先名（会社名）は必須です。';
    return;
  }
  isSaving.value = true;
  errorMsg.value = '';
  try {
    if (isEditing.value) {
      // 編集: 保存後もモーダルを開いたまま（タブで口座管理に移れる）
      await updateClient(props.editData.id, buildPayload());
      emit('saved');
      saveSuccess.value = true;
      setTimeout(() => { saveSuccess.value = false; }, 2000);
    } else {
      // 新規作成: 保存後に口座登録ステップへ
      const created = await createClient(buildPayload() as any);
      if (!created) throw new Error('取引先の作成に失敗しました。');
      newClientId.value = created.id;
      newClientName.value = formData.value.name;
      emit('saved'); // 親がリストを更新
      step.value = 'banks';
    }
  } catch (e: any) {
    errorMsg.value = e.message || '保存に失敗しました。';
  } finally {
    isSaving.value = false;
  }
};

const handleClose = () => {
  if (!isSaving.value) emit('close');
};
</script>

<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="handleClose"></div>

    <div class="bg-white rounded-2xl shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh] relative z-10 overflow-hidden">

      <!-- ── ヘッダー ── -->
      <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/50 shrink-0">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl flex items-center justify-center"
              :class="step === 'banks' ? 'bg-emerald-100 text-emerald-600' : 'bg-indigo-100 text-indigo-600'">
              <CheckCircle2 v-if="step === 'banks'" :size="20" />
              <Building2 v-else :size="20" />
            </div>
            <div>
              <h2 class="text-lg font-bold text-slate-800 tracking-tight leading-tight">
                <template v-if="!isEditing && step === 'form'">新規取引先の登録</template>
                <template v-else-if="!isEditing && step === 'banks'">振込先口座を追加</template>
                <template v-else>取引先情報の編集</template>
              </h2>
              <p class="text-xs text-slate-500 mt-0.5">
                <template v-if="!isEditing && step === 'form'">基本情報を入力してください（1/2）</template>
                <template v-else-if="!isEditing && step === 'banks'">
                  <span class="text-emerald-600 font-semibold">{{ newClientName }}</span> を作成しました。口座を登録できます（2/2）
                </template>
                <template v-else>{{ props.editData?.name }}</template>
              </p>
            </div>
          </div>
          <button @click="handleClose" class="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors">
            <X :size="20" />
          </button>
        </div>

        <!-- 編集モード: タブ -->
        <div v-if="isEditing" class="flex gap-1 mt-4 bg-slate-100 rounded-lg p-1 w-fit">
          <button
            @click="activeTab = 'info'"
            class="px-4 py-1.5 rounded-md text-sm font-semibold transition-all"
            :class="activeTab === 'info' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
          >
            基本情報
          </button>
          <button
            @click="activeTab = 'banks'"
            class="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-semibold transition-all"
            :class="activeTab === 'banks' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
          >
            <CreditCard :size="13" />
            振込先口座
          </button>
        </div>

        <!-- 新規作成: ステップインジケーター -->
        <div v-else class="flex items-center gap-2 mt-4">
          <div class="flex items-center gap-1.5">
            <div class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
              :class="step === 'form' ? 'bg-indigo-600 text-white' : 'bg-emerald-500 text-white'">
              <CheckCircle2 v-if="step === 'banks'" :size="14" />
              <span v-else>1</span>
            </div>
            <span class="text-xs font-medium" :class="step === 'form' ? 'text-indigo-600' : 'text-emerald-600'">基本情報</span>
          </div>
          <div class="w-8 h-px" :class="step === 'banks' ? 'bg-emerald-400' : 'bg-slate-300'"></div>
          <div class="flex items-center gap-1.5">
            <div class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
              :class="step === 'banks' ? 'bg-indigo-600 text-white' : 'bg-slate-200 text-slate-500'">2</div>
            <span class="text-xs font-medium" :class="step === 'banks' ? 'text-indigo-600' : 'text-slate-400'">振込先口座</span>
          </div>
        </div>
      </div>

      <!-- ── ボディ ── -->
      <div class="flex-1 overflow-y-auto custom-scrollbar">

        <!-- 保存成功バナー（編集モード） -->
        <Transition name="slide-down">
          <div v-if="saveSuccess" class="px-6 pt-4">
            <div class="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-sm font-medium">
              <CheckCircle2 :size="16" class="shrink-0" />
              基本情報を保存しました
            </div>
          </div>
        </Transition>

        <!-- エラーバナー -->
        <div v-if="errorMsg" class="px-6 pt-4">
          <div class="p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm font-medium">{{ errorMsg }}</div>
        </div>

        <!-- 基本情報フォーム（新規 Step1 / 編集 基本情報タブ） -->
        <div v-if="step === 'form' || (isEditing && activeTab === 'info')" class="p-6 space-y-6">

          <!-- 基本情報 -->
          <div>
            <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>基本情報
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="md:col-span-2">
                <label class="block text-sm font-medium text-slate-700 mb-1">取引先名 (会社名) <span class="text-red-500">*</span></label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><Building2 :size="16" /></span>
                  <input type="text" v-model="formData.name" placeholder="例: 株式会社サンプル" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">法人番号 / 登録番号</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><FileText :size="16" /></span>
                  <input type="text" v-model="formData.companyRegistrationNumber" placeholder="例: T1234567890123" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono" />
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

          <!-- 担当者・連絡先 -->
          <div>
            <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>担当者・連絡先
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">部署名</label>
                <input type="text" v-model="formData.department" placeholder="例: 経理部" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all" />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">担当者名</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><User :size="16" /></span>
                  <input type="text" v-model="formData.contactPerson" placeholder="例: 山田 太郎" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">メールアドレス</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><Mail :size="16" /></span>
                  <input type="email" v-model="formData.email" placeholder="例: yamada@example.com" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">電話番号</label>
                <div class="relative">
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"><Phone :size="16" /></span>
                  <input type="tel" v-model="formData.phone" placeholder="例: 03-1234-5678" class="w-full pl-9 pr-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono" />
                </div>
              </div>
            </div>
          </div>

          <hr class="border-slate-100">

          <!-- 所在地 -->
          <div>
            <h3 class="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>所在地情報
            </h3>
            <div class="space-y-4">
              <div class="w-1/3">
                <label class="block text-sm font-medium text-slate-700 mb-1">郵便番号</label>
                <input type="text" v-model="formData.postalCode" placeholder="例: 100-0001" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all font-mono" />
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

          <!-- メモ -->
          <div>
            <label class="block text-sm font-medium text-slate-700 mb-1">社内用メモ (請求書には印字されません)</label>
            <textarea v-model="formData.internalNotes" placeholder="特記事項や注意事項などがあれば入力..." rows="2" class="w-full px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all resize-none"></textarea>
          </div>

        </div>

        <!-- 振込先口座（編集タブ / 新規 Step2） -->
        <div v-else-if="(isEditing && activeTab === 'banks') || (!isEditing && step === 'banks')" class="p-6">
          <BankAccountSection
            owner-type="client"
            :client-id="isEditing ? props.editData.id : newClientId ?? undefined"
          />
        </div>

      </div>

      <!-- ── フッター ── -->
      <div class="px-6 py-4 border-t border-slate-100 bg-slate-50/50 shrink-0 flex items-center justify-end gap-3 rounded-b-2xl">

        <!-- 新規作成 Step1 -->
        <template v-if="!isEditing && step === 'form'">
          <button @click="handleClose" class="px-5 py-2.5 text-sm font-bold text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
            キャンセル
          </button>
          <button @click="handleSave" :disabled="isSaving || !formData.name"
            class="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm disabled:bg-indigo-300 disabled:cursor-not-allowed flex items-center gap-2 min-w-[120px] justify-center">
            <span v-if="isSaving" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
            <span v-else>作成する →</span>
          </button>
        </template>

        <!-- 新規作成 Step2 -->
        <template v-else-if="!isEditing && step === 'banks'">
          <button @click="handleClose" class="px-5 py-2.5 text-sm font-bold text-slate-500 hover:text-slate-700 transition-colors">
            スキップ
          </button>
          <button @click="handleClose" class="px-5 py-2.5 text-sm font-bold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition-colors shadow-sm">
            完了
          </button>
        </template>

        <!-- 編集 基本情報タブ -->
        <template v-else-if="isEditing && activeTab === 'info'">
          <button @click="handleClose" class="px-5 py-2.5 text-sm font-bold text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
            閉じる
          </button>
          <button @click="handleSave" :disabled="isSaving || !formData.name"
            class="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm disabled:bg-indigo-300 disabled:cursor-not-allowed flex items-center gap-2 min-w-[120px] justify-center">
            <span v-if="isSaving" class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
            <span v-else>保存する</span>
          </button>
        </template>

        <!-- 編集 振込先口座タブ -->
        <template v-else-if="isEditing && activeTab === 'banks'">
          <button @click="handleClose" class="px-5 py-2.5 text-sm font-bold text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
            閉じる
          </button>
        </template>

      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 6px; }
.custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
.custom-scrollbar::-webkit-scrollbar-thumb { background-color: #cbd5e1; border-radius: 20px; }

.slide-down-enter-active, .slide-down-leave-active { transition: all 0.25s ease; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
