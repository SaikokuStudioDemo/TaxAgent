<script setup lang="ts">
import { computed } from 'vue';
import { formatCurrency, calculateTaxInclusive } from '@/lib/utils/formatters';
import { PLANS, OPTIONS } from '@/lib/constants/mockData';
import { calculateMonthlyFee } from '@/lib/utils/pricing';

const props = defineProps<{
  selectedPlanId: string;
  selectedOptions: string[];
}>();

const selectedPlan = computed(() => PLANS.find((p) => p.id === props.selectedPlanId));
const selectedOptionsData = computed(() => OPTIONS.filter((o) => props.selectedOptions.includes(o.id)));

const planPrice = computed(() => selectedPlan.value?.price || 0);
const totalPrice = computed(() => calculateMonthlyFee(props.selectedPlanId, props.selectedOptions));
</script>

<template>
  <div class="bg-indigo-900 rounded-2xl shadow-lg p-6 text-white sticky top-24">
    <h3 class="text-lg font-bold mb-6 border-b border-indigo-700 pb-3">お見積りサマリー</h3>

    <div class="space-y-4 mb-6">
      <!-- Plan row -->
      <div class="flex justify-between items-center text-sm">
        <span class="text-indigo-200">{{ selectedPlan?.name || 'プラン未選択' }}</span>
        <div class="text-right">
          <span class="font-semibold block">{{ formatCurrency(calculateTaxInclusive(planPrice)) }}</span>
          <span class="text-xs text-indigo-300 font-normal">税抜 {{ formatCurrency(planPrice) }}</span>
        </div>
      </div>

      <!-- Options rows -->
      <div v-for="opt in selectedOptionsData" :key="opt.id" class="flex justify-between items-center text-sm">
        <span class="text-indigo-200 truncate pr-4">{{ opt.name }}</span>
        <div class="text-right">
          <span class="font-semibold text-indigo-100 block">+{{ formatCurrency(calculateTaxInclusive(opt.price)) }}</span>
          <span class="text-xs text-indigo-300 font-normal">税抜 {{ formatCurrency(opt.price) }}</span>
        </div>
      </div>
      
      <div v-if="selectedOptionsData.length === 0" class="text-sm text-indigo-400 italic">追加オプションなし</div>
    </div>

    <div class="border-t border-indigo-700 pt-4 mt-6">
      <div class="flex justify-between items-end">
        <span class="text-sm text-indigo-200 mb-1">月額合計金額</span>
        <div class="text-right">
          <span class="text-3xl font-black text-white block">{{ formatCurrency(calculateTaxInclusive(totalPrice)) }}</span>
          <span class="text-sm text-indigo-300 font-normal mt-1 block">（税抜 {{ formatCurrency(totalPrice) }}）</span>
        </div>
      </div>
    </div>
  </div>
</template>
