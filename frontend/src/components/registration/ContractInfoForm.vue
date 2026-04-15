<script setup lang="ts">
import { ref } from 'vue';
import { Building, Mail, MapPin, Lock, Globe, Handshake, AlertCircle, Eye, EyeOff, Phone, FileText } from 'lucide-vue-next';
import type { ContractFormValues } from '@/lib/utils/validations';

defineProps<{
  salesAgentName?: string;
  referrerName?: string;
  isTaxFirm?: boolean;
  isEditMode?: boolean;
  errors: Record<string, string>;
}>();

const formState = defineModel<Partial<ContractFormValues>>('formState', { required: true });
const showPassword = ref(false);

</script>

<template>
  <section class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 mb-8">
    <!-- Referral / Agent Banner (Optional) -->
    <div v-if="salesAgentName || referrerName" class="mb-8 p-4 bg-indigo-50 border border-indigo-100 rounded-xl flex items-start gap-3">
      <Handshake class="text-indigo-600 shrink-0 mt-0.5" :size="20" />
      <div>
        <h3 class="text-sm font-bold text-indigo-900 mb-1">ご紹介による登録</h3>
        <p class="text-sm text-indigo-700">
          <span v-if="salesAgentName">担当営業: {{ salesAgentName }}</span>
          <span v-if="salesAgentName && referrerName"> / </span>
          <span v-if="referrerName">ご紹介者: {{ referrerName }}</span>
          からのご案内で登録手続きを進めています。
        </p>
      </div>
    </div>

    <div class="mb-6 border-b border-gray-100 pb-4">
      <h2 class="text-xl font-bold text-gray-900">契約情報（法人・管理者アカウント設定）</h2>
      <p class="text-sm text-gray-500 mt-1">基本となる法人情報と、システム全体を管理するマスターアカウントを設定します</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Login ID (Email) -->
      <div class="space-y-2">
        <label for="loginEmail" class="block text-sm font-medium text-gray-700">
          管理者ログインID（メールアドレス） <span class="text-red-500">*</span>
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" :class="errors?.loginEmail ? 'text-red-400' : 'text-gray-400'">
            <Mail :size="18" />
          </div>
          <input
            type="text"
            id="loginEmail"
            v-model="formState.loginEmail"
            :disabled="isEditMode"
            class="block w-full pl-10 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 transition-colors"
            :class="[
              isEditMode ? 'bg-gray-100 text-gray-500 cursor-not-allowed border-gray-200' : 'bg-gray-50 text-gray-900',
              errors?.loginEmail ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'
            ]"
            placeholder="admin@example.com"
          />
        </div>
        <p v-if="errors?.loginEmail" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.loginEmail }}
        </p>
      </div>

      <!-- Password -->
      <div class="space-y-2">
        <label for="loginPassword" class="block text-sm font-medium text-gray-700">
          管理者パスワード <span class="text-red-500">*</span>
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" :class="errors?.loginPassword ? 'text-red-400' : 'text-gray-400'">
            <Lock :size="18" />
          </div>
          <input
            :type="showPassword ? 'text' : 'password'"
            id="loginPassword"
            v-model="formState.loginPassword"
            :disabled="isEditMode"
            class="block w-full pl-10 pr-10 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 transition-colors"
            :class="[
              isEditMode ? 'bg-gray-100 text-gray-500 cursor-not-allowed border-gray-200' : 'bg-gray-50 text-gray-900',
              errors?.loginPassword ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'
            ]"
            placeholder="••••••••"
          />
          <button 
            type="button" 
            @click="showPassword = !showPassword"
            class="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 focus:outline-none"
            :disabled="isEditMode"
          >
            <component :is="showPassword ? EyeOff : Eye" :size="18" />
          </button>
        </div>
        <p v-if="errors?.loginPassword" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.loginPassword }}
        </p>
      </div>

      <!-- Company Name -->
      <div class="space-y-2">
        <label for="companyName" class="block text-sm font-medium text-gray-700">
          法人名 <span class="text-red-500">*</span>
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" :class="errors?.companyName ? 'text-red-400' : 'text-gray-400'">
            <Building :size="18" />
          </div>
          <input
            type="text"
            id="companyName"
            v-model="formState.companyName"
            class="block w-full pl-10 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 bg-gray-50 text-gray-900 transition-colors"
            :class="errors?.companyName ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'"
            placeholder="株式会社サンプル"
          />
        </div>
        <p v-if="errors?.companyName" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.companyName }}
        </p>
      </div>

      <!-- URL (Optional) -->
      <div class="space-y-2">
        <label for="companyUrl" class="block text-sm font-medium text-gray-700">
          URL
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" :class="errors?.companyUrl ? 'text-red-400' : 'text-gray-400'">
            <Globe :size="18" />
          </div>
          <input
            type="text"
            id="companyUrl"
            v-model="formState.companyUrl"
            class="block w-full pl-10 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 bg-gray-50 text-gray-900 transition-colors"
            :class="errors?.companyUrl ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'"
            placeholder="https://example.com"
          />
        </div>
        <p v-if="errors?.companyUrl" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.companyUrl }}
        </p>
      </div>

      <!-- Address -->
      <div class="space-y-2 md:col-span-2">
        <label for="address" class="block text-sm font-medium text-gray-700">
          所在地 <span class="text-red-500">*</span>
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 top-3" :class="errors?.address ? 'text-red-400' : 'text-gray-400'">
            <MapPin :size="18" />
          </div>
          <textarea
            id="address"
            v-model="formState.address"
            :rows="2"
            class="block w-full pl-10 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 bg-gray-50 text-gray-900 transition-colors resize-none"
            :class="errors?.address ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'"
            placeholder="東京都千代田区〇〇 1-2-3"
          />
        </div>
        <p v-if="errors?.address" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.address }}
        </p>
      </div>

      <!-- Phone (Optional) -->
      <div class="space-y-2">
        <label for="phone" class="block text-sm font-medium text-gray-700">
          電話番号
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" :class="errors?.phone ? 'text-red-400' : 'text-gray-400'">
            <Phone :size="18" />
          </div>
          <input
            type="tel"
            id="phone"
            v-model="formState.phone"
            class="block w-full pl-10 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 bg-gray-50 text-gray-900 transition-colors"
            :class="errors?.phone ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'"
            placeholder="03-1234-5678"
          />
        </div>
        <p v-if="errors?.phone" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.phone }}
        </p>
      </div>

      <!-- Registration Number (Optional) -->
      <div class="space-y-2">
        <label for="registrationNumber" class="block text-sm font-medium text-gray-700">
          適格請求書発行事業者登録番号
        </label>
        <div class="relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" :class="errors?.registrationNumber ? 'text-red-400' : 'text-gray-400'">
            <FileText :size="18" />
          </div>
          <div class="absolute inset-y-0 left-10 flex items-center pointer-events-none">
            <span class="text-gray-500 font-medium text-sm">T</span>
          </div>
          <input
            type="text"
            id="registrationNumber"
            :value="formState.registrationNumber ? formState.registrationNumber.replace(/^T/, '') : ''"
            @input="(e) => { formState.registrationNumber = 'T' + (e.target as HTMLInputElement).value.replace(/^T/, '') }"
            class="block w-full pl-14 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-indigo-500 bg-gray-50 text-gray-900 transition-colors"
            :class="errors?.registrationNumber ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-indigo-500'"
            placeholder="1234567890123"
            maxlength="13"
          />
        </div>
        <p v-if="errors?.registrationNumber" class="text-xs text-red-500 flex items-center gap-1 mt-1">
          <AlertCircle :size="14" /> {{ errors.registrationNumber }}
        </p>
      </div>

      <!-- M&A Intent (Only for Tax Firms) -->
      <div v-if="isTaxFirm" class="space-y-3 md:col-span-2 mt-4 p-5 bg-gradient-to-r from-slate-50 to-gray-50 border border-slate-200 rounded-xl">
        <div>
          <label class="block text-sm font-bold text-slate-800">
            事業承継・M&Aに関する意向表示（任意）
          </label>
          <p class="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
            ※ 近い将来に事務所の譲渡や統合（M&A）をご検討されている場合、Tax-Agentのパートナー・ネットワークを通じて最適なマッチングや事業承継の支援を優先的にご案内することが可能です。現在の状況に最も近いものをお選びください。
          </p>
        </div>
        <div class="space-y-2 mt-3">
          <label class="flex items-center gap-3 p-3 border border-slate-200 rounded-lg bg-white cursor-pointer hover:border-indigo-300 transition-colors">
            <input type="radio" value="none" v-model="formState.maIntent" class="w-4 h-4 text-indigo-600 focus:ring-indigo-500 border-gray-300" />
            <span class="text-sm text-gray-700 font-medium">現在は検討していない</span>
          </label>
          <label class="flex items-center gap-3 p-3 border border-slate-200 rounded-lg bg-white cursor-pointer hover:border-indigo-300 transition-colors">
            <input type="radio" value="considering" v-model="formState.maIntent" class="w-4 h-4 text-indigo-600 focus:ring-indigo-500 border-gray-300" />
            <span class="text-sm text-gray-700 font-medium">数年以内の事業承継・譲渡を検討している</span>
          </label>
          <label class="flex items-center gap-3 p-3 border border-slate-200 rounded-lg bg-white cursor-pointer hover:border-indigo-300 transition-colors">
            <input type="radio" value="immediate" v-model="formState.maIntent" class="w-4 h-4 text-indigo-600 focus:ring-indigo-500 border-gray-300" />
            <span class="text-sm text-gray-700 font-medium">早急に譲渡先を探している、または話を進めたい</span>
          </label>
        </div>
      </div>
    </div>
  </section>
</template>
