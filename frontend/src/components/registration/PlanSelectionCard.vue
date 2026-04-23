<script setup lang="ts">
import { CheckCircle2, Circle } from 'lucide-vue-next';
import { formatCurrency, calculateTaxInclusive } from '@/lib/utils/formatters';

defineProps<{
  selectedPlanId: string;
  selectedOptions: string[];
  plans: any[];
  options: any[];
}>();

const emit = defineEmits<{
  (e: 'selectPlan', id: string): void;
  (e: 'toggleOption', id: string): void;
}>();

const handleSelectPlan = (id: string) => {
  emit('selectPlan', id);
};

const handleToggleOption = (id: string) => {
  emit('toggleOption', id);
};
</script>

<template>
  <section class="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 mb-8">
    <div class="mb-6 border-b border-gray-100 pb-4">
      <h2 class="text-xl font-bold text-gray-900">プラン登録</h2>
      <p class="text-sm text-gray-500 mt-1">
        利用目的に合ったプランとオプションを選択してください。<br />
        <span class="text-indigo-600 font-medium">※プランの変更はいつでも可能ですが、管理者アカウントでのログインが必要です。</span>
      </p>
    </div>

    <div class="space-y-8">
      <!-- Plans -->
      <div>
        <h3 class="text-base font-semibold text-gray-800 mb-4">基本プランを選択</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div
            v-for="plan in plans"
            :key="plan.id"
            @click="handleSelectPlan(plan.id)"
            class="relative p-6 rounded-xl border-2 cursor-pointer transition-all duration-200"
            :class="[
              selectedPlanId === plan.id
                ? 'border-indigo-600 bg-indigo-50/50 shadow-md'
                : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
            ]"
          >
            <div class="flex justify-between items-start mb-4">
              <div>
                <h4 class="font-bold text-lg" :class="selectedPlanId === plan.id ? 'text-indigo-900' : 'text-gray-900'">
                  {{ plan.name }}
                </h4>
                <div class="mt-2">
                  <div class="flex items-baseline gap-1">
                    <span class="text-2xl font-black text-gray-900">
                      {{ formatCurrency(calculateTaxInclusive(plan.price, 10)) }}
                    </span>
                    <span class="text-sm text-gray-500">/月</span>
                  </div>
                  <div class="text-xs text-gray-500 font-normal mt-0.5">(税抜 {{ formatCurrency(plan.price) }})</div>
                </div>
              </div>
              <CheckCircle2 v-if="selectedPlanId === plan.id" class="text-indigo-600" :size="24" />
              <Circle v-else class="text-gray-300" :size="24" />
            </div>
            <ul class="space-y-2 mt-4">
              <li v-for="(feature, idx) in plan.features" :key="idx" class="flex items-start gap-2 text-sm text-gray-600">
                <CheckCircle2 class="text-indigo-500 shrink-0 mt-0.5" :size="16" />
                <span>{{ feature }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Options -->
      <div>
        <h3 class="text-base font-semibold text-gray-800 mb-4">追加オプション（任意）</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label
            v-for="option in options"
            :key="option.id"
            class="flex items-center justify-between p-4 rounded-xl border cursor-pointer transition-all"
            :class="[
              selectedOptions.includes(option.id)
                ? 'border-indigo-600 bg-indigo-50/30'
                : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
            ]"
          >
            <div class="flex items-center gap-3">
              <input
                type="checkbox"
                :id="`opt-${option.id}`"
                class="w-5 h-5 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500"
                :checked="selectedOptions.includes(option.id)"
                @change="handleToggleOption(option.id)"
              />
              <span class="font-medium text-gray-900">{{ option.name }}</span>
            </div>
            <div class="text-gray-900 font-semibold text-right">
              +{{ formatCurrency(calculateTaxInclusive(option.price, 10)) }}<span class="text-xs text-gray-500 font-normal">/月<br>(税抜 {{ formatCurrency(option.price) }})</span>
            </div>
          </label>
        </div>
      </div>
    </div>
  </section>
</template>
