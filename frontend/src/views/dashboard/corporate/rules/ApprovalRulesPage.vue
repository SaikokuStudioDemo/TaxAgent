<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Plus, Trash2, Save, AlertCircle, ArrowRight, X, Receipt, FileText, Send, Loader2, FolderKanban } from 'lucide-vue-next';
import { useApprovalRules, type ApprovalRule } from '@/composables/useApprovalRules';
import { useProjects } from '@/composables/useProjects';
import { useEmployees } from '@/composables/useEmployees';

// Tab state: which document type to show
type RuleTab = 'receipt' | 'received_invoice' | 'issued_invoice' | 'project';
const activeRuleTab = ref<RuleTab>('receipt');

const allRules = ref<ApprovalRule[]>([]);

const { rules: rulesFromApi, isLoading, fetchRules, createRule, updateRule, deleteRule } = useApprovalRules();
const { projects, fetchProjects } = useProjects();
const { fetchEmployees } = useEmployees();
const isSaving = ref(false);

onMounted(async () => {
  fetchProjects();
  fetchEmployees();
  await fetchRules();
  if (rulesFromApi.value.length > 0) {
    allRules.value = [...rulesFromApi.value];
  }
});

// Filtered rules by active tab
const rules = computed(() =>
  allRules.value.filter(r => r.applies_to.includes(activeRuleTab.value))
);

const receiptCount = computed(() => allRules.value.filter(r => r.applies_to.includes('receipt')).length);
const receivedInvoiceCount = computed(() => allRules.value.filter(r => r.applies_to.includes('received_invoice')).length);
const issuedInvoiceCount = computed(() => allRules.value.filter(r => r.applies_to.includes('issued_invoice')).length);
const projectRuleCount = computed(() => allRules.value.filter(r => r.applies_to.includes('project')).length);

const categories = ['消耗品費', '交際費', '会議費', '通信費', '旅費交通費', '新聞図書費'];
const approverRoles = [
  { id: 'project_manager', name: 'プロジェクトマネージャー (PM)' },
  { id: 'group_leader', name: '直属の係長/リーダー (Group Leader)' },
  { id: 'direct_manager', name: '直属の部門長 (Direct Manager)' },
  { id: 'director', name: '本部長 (Director)' },
  { id: 'ceo', name: '代表取締役 (CEO)' },
  { id: 'accounting', name: '経理担当 (Accounting)' }
];

const addRule = () => {
  if (activeRuleTab.value === 'project') {
    allRules.value.push({
      id: `rule-${Date.now()}`,
      name: '新しいプロジェクトルール',
      applies_to: ['project'],
      project_id: '',
      conditions: [],
      steps: [{ step: 1, role: 'specific_person', required: true, user_id: '', approver_name: '' }],
      active: true,
      created_at: '',
    });
  } else {
    allRules.value.push({
      id: `rule-${Date.now()}`,
      name: '新しいルール',
      applies_to: [activeRuleTab.value],
      conditions: [{ field: 'amount', operator: '>=', value: 0 }],
      steps: [{ step: 1, role: activeRuleTab.value === 'received_invoice' ? 'accounting' : 'direct_manager', required: true }],
      active: true,
      created_at: '',
    });
  }
};

const getProjectMembers = (projectId: string) => {
  const proj = projects.value.find(p => p.id === projectId);
  return proj?.members || [];
};

const onProjectApproverChange = (rule: ApprovalRule, aIndex: number, userId: string) => {
  const members = getProjectMembers(rule.project_id || '');
  const member = members.find(m => m.user_id === userId);
  if (member) {
    rule.steps[aIndex].user_id = userId;
    rule.steps[aIndex].approver_name = member.name;
  }
};

const removeRule = async (ruleId: string) => {
  if (!ruleId.startsWith('rule-')) {
    if (!confirm('このルールを削除してもよろしいですか？')) return;
    const success = await deleteRule(ruleId);
    if (!success) {
      alert('削除に失敗しました。');
      return;
    }
  }
  const idx = allRules.value.findIndex(r => r.id === ruleId);
  if (idx > -1) allRules.value.splice(idx, 1);
};

const saveRules = async () => {
  isSaving.value = true;
  try {
    for (const rule of allRules.value) {
      const isProjectRule = rule.applies_to.includes('project');
      const payload = {
        name: rule.name,
        applies_to: rule.applies_to,
        project_id: rule.project_id || undefined,
        conditions: isProjectRule ? [] : rule.conditions.map(c => ({
          field: c.field,
          operator: c.operator,
          value: c.field === 'amount' ? Number(c.value) : c.value
        })),
        steps: rule.steps.map((s, idx) => ({
          step: idx + 1,
          role: s.role,
          required: true,
          ...(s.user_id ? { user_id: s.user_id, approver_name: s.approver_name } : {}),
        })),
        active: true
      };

      if (rule.id.startsWith('rule-')) {
        const created = await createRule(payload);
        rule.id = created.id;
      } else {
        await updateRule(rule.id, payload);
      }
    }
    alert('設定を保存しました。');
  } catch(e: any) {
    alert(`保存に失敗しました。\n${e.message ?? ''}`);
  } finally {
    isSaving.value = false;
  }
};

const addCondition = (rule: ApprovalRule) => {
  rule.conditions.push({ field: 'amount', operator: '>=', value: 0 });
};

const removeCondition = (rule: ApprovalRule, cIndex: number) => {
  rule.conditions.splice(cIndex, 1);
};

const addApprover = (rule: ApprovalRule) => {
  rule.steps.push({ step: rule.steps.length + 1, role: 'direct_manager', required: true });
};

const removeApprover = (rule: ApprovalRule, aIndex: number) => {
  rule.steps.splice(aIndex, 1);
};
</script>

<template>
  <div class="flex flex-col space-y-6">
    <!-- Header -->
    <div class="flex justify-between items-end mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">承認ルール作成 (Settings)</h1>
        <p class="text-gray-500 mt-1">AIが判定できない場合や、独自の承認要件がある場合にルールを設定します。金額や勘定科目に応じて承認者を定義します。</p>
      </div>
      <button @click="saveRules" :disabled="isSaving" class="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white px-5 py-2.5 rounded-lg flex items-center gap-2 font-medium transition-colors shadow-sm">
        <Loader2 v-if="isSaving" class="animate-spin" :size="18" />
        <Save v-else :size="18" />
        {{ isSaving ? '保存中...' : '設定を保存する' }}
      </button>
    </div>

    <!-- Document Type Tabs -->
    <div class="flex gap-1 bg-gray-100 p-1.5 rounded-xl mb-6 shadow-inner w-full">
      <button
        @click="activeRuleTab = 'receipt'"
        class="flex-1 flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition-all"
        :class="activeRuleTab === 'receipt' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
      >
        <Receipt :size="16" />
        経費精算領収書
        <span class="ml-1 inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold rounded-full"
          :class="activeRuleTab === 'receipt' ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'">
          {{ receiptCount }}
        </span>
      </button>
      <button
        @click="activeRuleTab = 'received_invoice'"
        class="flex-1 flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition-all"
        :class="activeRuleTab === 'received_invoice' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
      >
        <FileText :size="16" />
        受領請求書
        <span class="ml-1 inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold rounded-full"
          :class="activeRuleTab === 'received_invoice' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-200 text-gray-600'">
          {{ receivedInvoiceCount }}
        </span>
      </button>
      <button
        @click="activeRuleTab = 'issued_invoice'"
        class="flex-1 flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition-all"
        :class="activeRuleTab === 'issued_invoice' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
      >
        <Send :size="16" />
        発行請求書
        <span class="ml-1 inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold rounded-full"
          :class="activeRuleTab === 'issued_invoice' ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600'">
          {{ issuedInvoiceCount }}
        </span>
      </button>
      <button
        @click="activeRuleTab = 'project'"
        class="flex-1 flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition-all"
        :class="activeRuleTab === 'project' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'"
      >
        <FolderKanban :size="16" />
        プロジェクト
        <span class="ml-1 inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold rounded-full"
          :class="activeRuleTab === 'project' ? 'bg-violet-100 text-violet-700' : 'bg-gray-200 text-gray-600'">
          {{ projectRuleCount }}
        </span>
      </button>
    </div>

    <!-- Alert Context -->
    <div class="bg-blue-50 border border-blue-100 rounded-lg p-4 mb-6 flex gap-3 text-blue-800">
      <AlertCircle class="mt-0.5 flex-shrink-0" :size="20" />
      <div class="text-sm leading-relaxed">
        <p class="font-bold mb-1">ルールの適用順序について</p>
        <p>上から順番に条件を判定し、最初に一致したルールの承認者がアサインされます。<br>
        金額に関わらず必ず特定の承認を通したい場合は、リストの一番下に「すべての条件（常に）」のルールを配置してください。</p>
        <p class="mt-1 text-blue-700">
          <span v-if="activeRuleTab === 'receipt'">💡 経費領収書が提出されると、金額・科目に基づきこのルールが自動適用されます。</span>
          <span v-else-if="activeRuleTab === 'received_invoice'">💡 受領請求書がアップロードされると、このルールに基づき支払承認フローが開始されます。</span>
          <span v-else-if="activeRuleTab === 'project'">💡 プロジェクトを選択し、そのプロジェクトの責任者から承認者を指定します。プロジェクトに紐づいた書類はこのルートが優先適用されます。</span>
          <span v-else>💡 請求書を発行する際、金額に基づきこのルールに従った承認が必要になります。</span>
        </p>
      </div>
    </div>

    <!-- Rules Container -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div class="p-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center shrink-0">
        <h2 class="font-bold text-gray-700">
          <span v-if="activeRuleTab === 'receipt'">領収書 承認ルール定義</span>
          <span v-else-if="activeRuleTab === 'received_invoice'">受領請求書 支払承認ルール定義</span>
          <span v-else-if="activeRuleTab === 'project'">プロジェクト別 承認ルール定義</span>
          <span v-else>発行請求書 承認ルール定義</span>
        </h2>
        <button @click="addRule" class="bg-blue-600 hover:bg-blue-700 text-white text-sm flex items-center gap-1.5 px-4 py-2 rounded-lg font-medium transition-colors shadow-sm">
          <Plus :size="16" />
          新規ルール作成
        </button>
      </div>

      <div class="p-6 space-y-4 relative">
        <div v-if="isLoading" class="flex items-center justify-center py-12">
            <Loader2 class="w-8 h-8 text-blue-500 animate-spin" />
        </div>
        <template v-else>
        <div v-for="(rule) in rules" :key="rule.id" class="flex items-start gap-4 p-4 border border-gray-200 rounded-lg bg-gray-50/50 hover:border-blue-300 transition-colors group">
          <div class="flex-1 space-y-5">
            <!-- Rule Name + Applies To badges -->
            <div class="flex items-center gap-3">
              <div class="flex-1">
                <label class="block text-xs font-semibold text-gray-500 mb-1">ルール名</label>
                <input type="text" v-model="rule.name" class="w-full bg-white border border-gray-300 rounded px-3 py-2 text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 font-medium text-gray-900">
              </div>
              <div class="shrink-0 pt-5">
                <div class="flex gap-1.5">
                  <span v-if="rule.applies_to.includes('receipt')" class="flex items-center gap-1 bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded text-[10px] font-bold">
                    <Receipt :size="10" /> 領収書
                  </span>
                  <span v-if="rule.applies_to.includes('received_invoice')" class="flex items-center gap-1 bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded text-[10px] font-bold">
                    <FileText :size="10" /> 受領請求書
                  </span>
                  <span v-if="rule.applies_to.includes('project')" class="flex items-center gap-1 bg-violet-50 text-violet-700 border border-violet-200 px-2 py-0.5 rounded text-[10px] font-bold">
                    <FolderKanban :size="10" /> プロジェクト
                  </span>
                </div>
              </div>
            </div>

            <!-- Project selector (project rules only) -->
            <div v-if="rule.applies_to.includes('project')" class="bg-violet-50 border border-violet-100 rounded p-3">
              <label class="block text-xs font-semibold text-violet-700 mb-1">対象プロジェクト</label>
              <select v-model="rule.project_id" class="w-full bg-white border border-violet-200 rounded px-2 py-1.5 text-sm focus:ring-1 focus:ring-violet-500">
                <option value="">プロジェクトを選択...</option>
                <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}</option>
              </select>
            </div>

            <!-- Conditions & Approvers Grid -->
            <div :class="rule.applies_to.includes('project') ? '' : 'grid grid-cols-1 md:grid-cols-2 gap-6'">

              <!-- Left: Conditions (AND Logic) — hidden for project rules -->
              <div v-if="!rule.applies_to.includes('project')" class="bg-white p-4 rounded border border-gray-100 shadow-sm relative">
                <div class="flex justify-between items-center mb-3">
                  <label class="block text-xs font-bold text-gray-700">適用条件 (すべて満たす場合)</label>
                  <button @click="addCondition(rule)" class="text-blue-600 hover:text-blue-800 text-xs font-medium flex items-center gap-0.5">
                    <Plus :size="14" /> 条件追加
                  </button>
                </div>
                
                <div class="space-y-3">
                  <div v-for="(cond, cIndex) in rule.conditions" :key="cIndex" class="flex items-start gap-2 relative group/cond">
                    <div class="w-1/3">
                      <select v-model="cond.field" class="w-full bg-gray-50 border border-gray-200 rounded px-2 py-1.5 text-xs focus:ring-1 focus:ring-blue-500">
                        <option value="always">常に対象</option>
                        <option value="amount">金額 (税込)</option>
                        <option value="category">勘定科目</option>
                      </select>
                    </div>

                    <template v-if="cond.field === 'amount'">
                      <div class="w-1/4">
                        <select v-model="cond.operator" class="w-full bg-gray-50 border border-gray-200 rounded px-2 py-1.5 text-xs focus:ring-1 focus:ring-blue-500">
                          <option value=">=">以上</option>
                          <option value="<=">以下</option>
                        </select>
                      </div>
                      <div class="flex-1 relative">
                        <span class="absolute left-2 top-1.5 text-gray-400 text-xs text-center font-medium">¥</span>
                        <input type="number" v-model="cond.value" class="w-full bg-gray-50 border border-gray-200 rounded pl-5 pr-2 py-1.5 text-xs focus:ring-1 focus:ring-blue-500 text-right">
                      </div>
                    </template>

                    <template v-else-if="cond.field === 'category'">
                      <div class="w-1/4">
                        <select v-model="cond.operator" class="w-full bg-gray-50 border border-gray-200 rounded px-2 py-1.5 text-xs focus:ring-1 focus:ring-blue-500">
                          <option value="==">が一致</option>
                        </select>
                      </div>
                      <div class="flex-1">
                        <select v-model="cond.value" class="w-full bg-gray-50 border border-gray-200 rounded px-2 py-1.5 text-xs focus:ring-1 focus:ring-blue-500">
                          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
                        </select>
                      </div>
                    </template>
                    
                    <button v-if="rule.conditions.length > 1" @click="removeCondition(rule, cIndex)" class="mt-1 text-gray-300 hover:text-red-500 opacity-0 group-hover/cond:opacity-100 transition-opacity">
                      <X :size="16" />
                    </button>
                    <!-- AND label between conditions -->
                    <div v-if="cIndex < rule.conditions.length - 1" class="absolute -bottom-3 left-1/2 -translate-x-1/2 text-[10px] font-bold text-gray-400 bg-white px-1 z-10">AND</div>
                  </div>
                </div>
              </div>

              <!-- Right: Approvers (Sequential Logic) -->
              <div :class="rule.applies_to.includes('project') ? 'bg-violet-50/50 p-4 rounded border border-violet-100 shadow-sm relative' : 'bg-blue-50/50 p-4 rounded border border-blue-100 shadow-sm relative'">
                <div class="flex justify-between items-center mb-3">
                  <label :class="rule.applies_to.includes('project') ? 'block text-xs font-bold text-violet-900' : 'block text-xs font-bold text-blue-900'">承認フロー (順番に承認)</label>
                  <button @click="addApprover(rule)" :class="rule.applies_to.includes('project') ? 'text-violet-600 hover:text-violet-800 text-xs font-medium flex items-center gap-0.5' : 'text-blue-600 hover:text-blue-800 text-xs font-medium flex items-center gap-0.5'">
                    <Plus :size="14" /> ステップ追加
                  </button>
                </div>

                <div class="space-y-3">
                  <div v-for="(approver, aIndex) in rule.steps" :key="aIndex" class="flex items-center gap-2 relative group/app">
                    <span :class="rule.applies_to.includes('project') ? 'flex-shrink-0 w-6 h-6 rounded-full bg-violet-100 text-violet-700 text-xs font-bold flex items-center justify-center border border-violet-200' : 'flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center border border-blue-200'">
                      {{ aIndex + 1 }}
                    </span>
                    <!-- Project rules: show project members selector -->
                    <template v-if="rule.applies_to.includes('project')">
                      <select
                        :value="approver.user_id"
                        @change="onProjectApproverChange(rule, aIndex, ($event.target as HTMLSelectElement).value)"
                        class="flex-1 bg-white border border-violet-200 text-violet-900 font-medium rounded px-3 py-1.5 text-xs focus:ring-1 focus:ring-violet-500 shadow-sm"
                        :disabled="!rule.project_id"
                      >
                        <option value="">{{ rule.project_id ? '責任者を選択...' : 'まずプロジェクトを選択' }}</option>
                        <option v-for="m in getProjectMembers(rule.project_id || '')" :key="m.user_id" :value="m.user_id">{{ m.name }}</option>
                      </select>
                    </template>
                    <!-- Standard rules: show role selector -->
                    <template v-else>
                      <select v-model="approver.role" class="flex-1 bg-white border border-blue-200 text-blue-900 font-medium rounded px-3 py-1.5 text-xs focus:ring-1 focus:ring-blue-500 shadow-sm">
                        <option v-for="role in approverRoles" :key="role.id" :value="role.id">{{ role.name }}</option>
                      </select>
                    </template>
                    <button v-if="rule.steps.length > 1" @click="removeApprover(rule, aIndex)" :class="rule.applies_to.includes('project') ? 'text-violet-300 hover:text-red-500 opacity-0 group-hover/app:opacity-100 transition-opacity' : 'text-blue-300 hover:text-red-500 opacity-0 group-hover/app:opacity-100 transition-opacity'">
                      <X :size="16" />
                    </button>
                    <!-- Arrow down between steps -->
                    <div v-if="aIndex < rule.steps.length - 1" :class="rule.applies_to.includes('project') ? 'absolute -bottom-3 left-3 text-violet-300 z-10' : 'absolute -bottom-3 left-3 text-blue-300 z-10'">
                      <ArrowRight :size="14" class="origin-center rotate-90" />
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </div>

          <!-- Delete -->
          <button @click="removeRule(rule.id)" class="mt-7 text-gray-300 hover:text-red-500 transition-colors p-2 rounded hover:bg-red-50">
            <Trash2 :size="18" />
          </button>
        </div>

        <div v-if="rules.length === 0" class="text-center py-16 text-gray-400 text-sm border-2 border-dashed border-gray-200 rounded-lg">
          <component :is="activeRuleTab === 'receipt' ? Receipt : FileText" :size="40" class="mx-auto mb-3 text-gray-300" />
          <p class="font-medium text-gray-500">ルールが設定されていません</p>
          <p class="mt-1 text-xs">「新規ルール作成」からルールを追加してください。</p>
        </div>

        </template>
      </div>
    </div>
  </div>
</template>
