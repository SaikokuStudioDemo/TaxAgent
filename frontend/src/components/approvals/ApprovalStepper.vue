<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { ShieldCheck, ArrowRight, Loader2, CheckCircle2, AlertCircle } from 'lucide-vue-next';
import { api } from '@/lib/api';
import { APPROVAL_LEVELS } from '@/lib/constants/mockData';

const props = withDefaults(defineProps<{
  documentType: 'receipt' | 'received_invoice' | 'issued_invoice';
  amount?: number;
  payload?: any;
  mode?: 'preview' | 'status' | 'history';
  history?: any[];
  currentStep?: number;
}>(), {
  currentStep: 1
});

const emit = defineEmits<{
  (e: 'update:requires-approval', required: boolean): void
}>();

interface ApprovalStep {
  step: number;
  role: string;
  required: boolean;
  status?: 'pending' | 'approved' | 'rejected' | 'returned' | 'skipped';
  approverName?: string;
  actionDate?: string;
  comment?: string;
}

const steps = ref<ApprovalStep[]>([]);
const isLoading = ref(false);
const matched = ref(false);
const error = ref<string | null>(null);

const fetchPreview = async () => {
  if (props.mode !== 'preview' || props.amount === undefined) return;
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.post<{ rule_id: string; steps: ApprovalStep[]; matched: boolean }>(
      '/approvals/rules/preview',
      {
        document_type: props.documentType,
        amount: props.amount,
        payload: props.payload
      }
    );
    steps.value = res.steps || [];
    matched.value = res.matched;
    emit('update:requires-approval', matched.value && steps.value.length > 0);
  } catch (err) {
    console.error('Failed to fetch approval preview', err);
    error.value = 'プレビューの取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};


const syncStatusSteps = () => {
  if (props.mode !== 'status' || !props.history) return;
  // Map history to steps
  steps.value = props.history.map((h, i) => ({
    step: h.step || i + 1,
    role: h.roleId || h.roleName || '承認者',
    required: true,
    status: h.status || 'pending',
    approverName: h.approverName,
    actionDate: h.actionDate,
    comment: h.comment
  }));
  matched.value = true;
};

watch(() => [props.amount, props.documentType, props.payload, props.mode, props.history], () => {
  if (props.mode === 'preview') {
    fetchPreview();
  } else {
    syncStatusSteps();
  }
}, { deep: true });

onMounted(() => {
  if (props.mode === 'preview') {
    fetchPreview();
  } else {
    syncStatusSteps();
  }
});

const getRoleLabel = (roleValue: string) => {
  return APPROVAL_LEVELS.find(l => l.value === roleValue)?.label || roleValue;
};

const getStepColorClasses = (step: ApprovalStep, index: number) => {
  if (props.mode === 'preview') {
    return step.required ? 'border-indigo-600 bg-indigo-50 text-indigo-600 shadow-sm shadow-indigo-100' : 'border-slate-300 bg-white text-slate-400';
  }
  
  // Status mode colors
  switch (step.status) {
    case 'approved': return 'border-emerald-500 bg-emerald-50 text-emerald-600';
    case 'rejected':
    case 'returned': return 'border-rose-500 bg-rose-50 text-rose-600';
    case 'pending': 
      return (index + 1 === props.currentStep) 
        ? 'border-blue-500 bg-blue-50 text-blue-600 ring-2 ring-blue-100 animate-pulse-slow' 
        : 'border-slate-200 bg-slate-50 text-slate-400';
    default: return 'border-slate-200 bg-slate-50 text-slate-400';
  }
};
</script>

<template>
  <div class="bg-white/50 backdrop-blur-sm border border-slate-200/60 rounded-2xl p-5 transition-all group shadow-sm">
    <div class="flex items-center gap-2 mb-5">
      <div class="p-1.5 bg-indigo-50 rounded-lg text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors duration-300">
        <ShieldCheck class="w-4 h-4" />
      </div>
      <span class="text-xs font-black text-slate-700 uppercase tracking-widest">{{ mode === 'preview' ? '承認ルート・プレビュー' : '承認進捗状況' }}</span>
      
      <div class="ml-auto flex items-center gap-1.5">
        <template v-if="mode === 'preview'">
          <span v-if="!matched && !isLoading" class="flex items-center gap-1 text-[10px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-bold border border-emerald-100">
             <CheckCircle2 class="w-3 h-3" /> 自動承認
          </span>
          <span v-else-if="matched && !isLoading" class="flex items-center gap-1 text-[10px] bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-bold border border-indigo-100">
             <ShieldCheck class="w-3 h-3" /> ルール適用中
          </span>
        </template>
        <template v-else>
          <span class="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">{{ steps.length }} Steps Flow</span>
        </template>
      </div>
    </div>

    <!-- Stepper UI -->
    <div v-if="isLoading" class="flex items-center justify-center py-6 h-[84px]">
      <Loader2 class="w-6 h-6 text-indigo-400 animate-spin" />
    </div>

    <div v-else-if="error" class="flex flex-col items-center justify-center py-4 h-[84px] text-red-500 gap-2">
      <AlertCircle class="w-5 h-5" />
      <span class="text-[10px] font-bold">{{ error }}</span>
    </div>

    <div v-else-if="steps.length > 0" class="flex items-center gap-4 overflow-x-auto pb-2 scrollbar-hide -mx-1 px-1 min-h-[84px]">
      <template v-for="(step, index) in steps" :key="index">
        <div class="flex flex-col items-center gap-2 group/step shrink-0 relative">
          <!-- Tooltip for comments/approvers in Status mode -->
          <div v-if="mode === 'status' && step.approverName" 
               class="absolute -top-12 bg-gray-900 text-white text-[9px] px-2 py-1 rounded opacity-0 group-hover/step:opacity-100 transition-opacity whitespace-nowrap z-20 shadow-xl pointer-events-none">
            {{ step.approverName }} <span v-if="step.actionDate" class="text-gray-400 ml-1">({{ step.actionDate }})</span>
            <div v-if="step.comment" class="border-t border-gray-700 mt-1 pt-1 italic text-gray-300">"{{ step.comment }}"</div>
            <div class="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-gray-900 rotate-45"></div>
          </div>

          <!-- Step Circle -->
          <div class="relative">
            <div class="w-10 h-10 rounded-full border-2 flex items-center justify-center transition-all duration-300 transform group-hover/step:scale-110"
                 :class="getStepColorClasses(step, index)">
              <CheckCircle2 v-if="mode === 'status' && step.status === 'approved'" class="w-5 h-5" />
              <AlertCircle v-else-if="mode === 'status' && (step.status === 'rejected' || step.status === 'returned')" class="w-5 h-5" />
              <span v-else class="text-xs font-black">{{ step.step }}</span>
            </div>
            
            <!-- Indicators -->
            <div v-if="mode === 'preview' && !step.required" class="absolute -top-1 -right-1 bg-white border border-slate-200 text-[8px] px-1 rounded text-slate-400 font-bold shadow-sm">任意</div>
            <div v-if="mode === 'status' && index + 1 === currentStep && step.status === 'pending'" class="absolute -top-1 -right-1 bg-blue-500 w-3 h-3 rounded-full border-2 border-white animate-ping"></div>
          </div>
          
          <!-- Role Label -->
          <div class="text-center">
            <p class="text-[10px] font-black text-slate-700 whitespace-nowrap">{{ getRoleLabel(step.role) }}</p>
            <p v-if="mode === 'preview' && step.required" class="text-[8px] text-indigo-400 font-bold uppercase tracking-tighter">Required</p>
            <p v-if="mode === 'status'" class="text-[8px] font-bold uppercase tracking-tight" 
               :class="step.status === 'approved' ? 'text-emerald-500' : step.status === 'pending' && index + 1 === currentStep ? 'text-blue-500' : 'text-slate-400'">
              {{ step.status }}
            </p>
          </div>
        </div>

        <!-- Connector -->
        <div v-if="index < steps.length - 1" class="flex items-center justify-center shrink-0 mb-6">
          <ArrowRight class="w-4 h-4 text-slate-300" :class="mode === 'status' && index + 1 < currentStep ? 'text-emerald-300' : 'animate-pulse-slow'" />
        </div>
      </template>
    </div>

    <div v-else class="flex flex-col items-center justify-center py-6 h-[84px] border-2 border-dashed border-slate-100 rounded-xl bg-slate-50/30">
      <CheckCircle2 class="w-6 h-6 text-emerald-300 mb-2" />
      <p class="text-[10px] text-slate-400 font-bold tracking-tight">承認不要：この書類は登録後に即時確定されます</p>
    </div>
  </div>
</template>

<style scoped>
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}
.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

@keyframes pulse-slow {
  0%, 100% { opacity: 1; transform: translateX(0); }
  50% { opacity: 0.5; transform: translateX(2px); }
}
.animate-pulse-slow {
  animation: pulse-slow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>
