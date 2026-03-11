<script setup lang="ts">
import { ref, computed } from 'vue';
import { Plus, Trash2, Save, GripVertical, AlertCircle, ArrowRight, X, Receipt, FileText } from 'lucide-vue-next';

interface RuleCondition {
  id: string;
  field: 'amount' | 'category' | 'always';
  operator: '>=' | '<=' | '==' | '';
  value: string | number;
}

interface RuleApprover {
  id: string;
  roleId: string;
}

interface ApprovalRule {
  id: string;
  name: string;
  appliesTo: ('receipt' | 'received_invoice')[];
  conditions: RuleCondition[];
  approvers: RuleApprover[];
}

// Tab state: which document type to show
type RuleTab = 'receipt' | 'received_invoice';
const activeRuleTab = ref<RuleTab>('receipt');

const allRules = ref<ApprovalRule[]>([
  {
    id: 'rule-1',
    name: '100万円以上の特別決裁（社長承認）',
    appliesTo: ['receipt', 'received_invoice'],
    conditions: [
      { id: 'c-1', field: 'amount', operator: '>=', value: 1000000 }
    ],
    approvers: [
      { id: 'a-1', roleId: 'direct_manager' },
      { id: 'a-2', roleId: 'director' },
      { id: 'a-3', roleId: 'ceo' }
    ]
  },
  {
    id: 'rule-2',
    name: '交際費の特別承認',
    appliesTo: ['receipt'],
    conditions: [
      { id: 'c-2', field: 'category', operator: '==', value: '交際費' }
    ],
    approvers: [
      { id: 'a-4', roleId: 'direct_manager' }
    ]
  },
  {
    id: 'rule-3',
    name: '基本ルート（全件）',
    appliesTo: ['receipt'],
    conditions: [
      { id: 'c-3', field: 'always', operator: '', value: '' }
    ],
    approvers: [
      { id: 'a-5', roleId: 'direct_manager' }
    ]
  },
  {
    id: 'rule-4',
    name: '受領請求書の基本承認ルート（全件）',
    appliesTo: ['received_invoice'],
    conditions: [
      { id: 'c-4', field: 'always', operator: '', value: '' }
    ],
    approvers: [
      { id: 'a-6', roleId: 'accounting' },
      { id: 'a-7', roleId: 'direct_manager' }
    ]
  },
  {
    id: 'rule-5',
    name: '30万円以上の受領請求書',
    appliesTo: ['received_invoice'],
    conditions: [
      { id: 'c-5', field: 'amount', operator: '>=', value: 300000 }
    ],
    approvers: [
      { id: 'a-8', roleId: 'accounting' },
      { id: 'a-9', roleId: 'direct_manager' },
      { id: 'a-10', roleId: 'director' }
    ]
  }
]);

// Filtered rules by active tab
const rules = computed(() =>
  allRules.value.filter(r => r.appliesTo.includes(activeRuleTab.value))
);

const receiptCount = computed(() => allRules.value.filter(r => r.appliesTo.includes('receipt')).length);
const invoiceCount = computed(() => allRules.value.filter(r => r.appliesTo.includes('received_invoice')).length);

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
  allRules.value.push({
    id: `rule-${Date.now()}`,
    name: '新しいルール',
    appliesTo: [activeRuleTab.value],
    conditions: [{ id: `c-${Date.now()}`, field: 'amount', operator: '>=', value: 0 }],
    approvers: [{ id: `a-${Date.now()}`, roleId: activeRuleTab.value === 'received_invoice' ? 'accounting' : 'direct_manager' }]
  });
};

const removeRule = (ruleId: string) => {
  const idx = allRules.value.findIndex(r => r.id === ruleId);
  if (idx > -1) allRules.value.splice(idx, 1);
};

const addCondition = (rule: ApprovalRule) => {
  rule.conditions.push({ id: `c-${Date.now()}`, field: 'amount', operator: '>=', value: 0 });
};

const removeCondition = (rule: ApprovalRule, cIndex: number) => {
  rule.conditions.splice(cIndex, 1);
};

const addApprover = (rule: ApprovalRule) => {
  rule.approvers.push({ id: `a-${Date.now()}`, roleId: 'direct_manager' });
};

const removeApprover = (rule: ApprovalRule, aIndex: number) => {
  rule.approvers.splice(aIndex, 1);
};
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="flex justify-between items-end mb-6">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">承認ルール作成 (Settings)</h1>
        <p class="text-gray-500 mt-1">AIが判定できない場合や、独自の承認要件がある場合にルールを設定します。金額や勘定科目に応じて承認者を定義します。</p>
      </div>
      <button class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg flex items-center gap-2 font-medium transition-colors shadow-sm">
        <Save :size="18" />
        設定を保存する
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
        受領請求書（支払承認）
        <span class="ml-1 inline-flex items-center justify-center px-2 py-0.5 text-xs font-bold rounded-full"
          :class="activeRuleTab === 'received_invoice' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-200 text-gray-600'">
          {{ invoiceCount }}
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
          <span v-else>💡 受領請求書がアップロードされると、このルールに基づき支払承認フローが開始されます。</span>
        </p>
      </div>
    </div>

    <!-- Rules Container -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex-1">
      <div class="p-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
        <h2 class="font-bold text-gray-700">
          <span v-if="activeRuleTab === 'receipt'">領収書 承認ルール定義</span>
          <span v-else>受領請求書 支払承認ルール定義</span>
        </h2>
        <button @click="addRule" class="bg-blue-600 hover:bg-blue-700 text-white text-sm flex items-center gap-1.5 px-4 py-2 rounded-lg font-medium transition-colors shadow-sm">
          <Plus :size="16" />
          新規ルール作成
        </button>
      </div>

      <div class="p-6 space-y-4 max-h-[calc(100vh-380px)] overflow-y-auto">
        
        <div v-for="(rule) in rules" :key="rule.id" class="flex items-start gap-4 p-4 border border-gray-200 rounded-lg bg-gray-50/50 hover:border-blue-300 transition-colors group">
          <div class="mt-3 text-gray-400 cursor-move">
            <GripVertical :size="20" />
          </div>
          
          <div class="flex-1 space-y-5">
            <!-- Rule Name + Applies To badges -->
            <div class="flex items-center gap-3">
              <div class="flex-1">
                <label class="block text-xs font-semibold text-gray-500 mb-1">ルール名</label>
                <input type="text" v-model="rule.name" class="w-full bg-white border border-gray-300 rounded px-3 py-2 text-sm focus:ring-1 focus:ring-blue-500 focus:border-blue-500 font-medium text-gray-900">
              </div>
              <div class="shrink-0 pt-5">
                <div class="flex gap-1.5">
                  <span v-if="rule.appliesTo.includes('receipt')" class="flex items-center gap-1 bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded text-[10px] font-bold">
                    <Receipt :size="10" /> 領収書
                  </span>
                  <span v-if="rule.appliesTo.includes('received_invoice')" class="flex items-center gap-1 bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded text-[10px] font-bold">
                    <FileText :size="10" /> 受領請求書
                  </span>
                </div>
              </div>
            </div>

            <!-- Conditions & Approvers Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              <!-- Left: Conditions (AND Logic) -->
              <div class="bg-white p-4 rounded border border-gray-100 shadow-sm relative">
                <div class="flex justify-between items-center mb-3">
                  <label class="block text-xs font-bold text-gray-700">適用条件 (すべて満たす場合)</label>
                  <button @click="addCondition(rule)" class="text-blue-600 hover:text-blue-800 text-xs font-medium flex items-center gap-0.5">
                    <Plus :size="14" /> 条件追加
                  </button>
                </div>
                
                <div class="space-y-3">
                  <div v-for="(cond, cIndex) in rule.conditions" :key="cond.id" class="flex items-start gap-2 relative group/cond">
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
              <div class="bg-blue-50/50 p-4 rounded border border-blue-100 shadow-sm relative">
                <div class="flex justify-between items-center mb-3">
                  <label class="block text-xs font-bold text-blue-900">承認フロー (順番に承認)</label>
                  <button @click="addApprover(rule)" class="text-blue-600 hover:text-blue-800 text-xs font-medium flex items-center gap-0.5">
                    <Plus :size="14" /> ステップ追加
                  </button>
                </div>

                <div class="space-y-3">
                  <div v-for="(approver, aIndex) in rule.approvers" :key="approver.id" class="flex items-center gap-2 relative group/app">
                    <span class="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center border border-blue-200">
                      {{ aIndex + 1 }}
                    </span>
                    <select v-model="approver.roleId" class="flex-1 bg-white border border-blue-200 text-blue-900 font-medium rounded px-3 py-1.5 text-xs focus:ring-1 focus:ring-blue-500 shadow-sm">
                      <option v-for="role in approverRoles" :key="role.id" :value="role.id">{{ role.name }}</option>
                    </select>
                    <button v-if="rule.approvers.length > 1" @click="removeApprover(rule, aIndex)" class="text-blue-300 hover:text-red-500 opacity-0 group-hover/app:opacity-100 transition-opacity">
                      <X :size="16" />
                    </button>
                    <!-- Arrow down between steps -->
                    <div v-if="aIndex < rule.approvers.length - 1" class="absolute -bottom-3 left-3 text-blue-300 z-10">
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

      </div>
    </div>
  </div>
</template>
