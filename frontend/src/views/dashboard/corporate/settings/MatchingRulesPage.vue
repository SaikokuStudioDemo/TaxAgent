<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
    Plus,
    Search,
    Edit,
    Trash2,
    Save,
    X,
    ArrowRightLeft
} from 'lucide-vue-next';
import { useMatchingRules, type MatchingRule } from '@/composables/useMatchingRules';

const { rules, isLoading, fetchRules, createRule, updateRule, deleteRule } = useMatchingRules();

const searchQuery = ref('');

const filteredRules = computed(() => {
    if (!searchQuery.value) return rules.value;
    const lowerQuery = searchQuery.value.toLowerCase();
    return rules.value.filter(r =>
        r.target_field.toLowerCase().includes(lowerQuery) ||
        r.condition_type.toLowerCase().includes(lowerQuery) ||
        r.action.toLowerCase().includes(lowerQuery)
    );
});

// モーダル用ステート
const showModal = ref(false);
const isEditing = ref(false);
const isSaving = ref(false);
const editingRule = ref<Omit<MatchingRule, 'id' | 'created_at'> & { id: string }>({
    id: '', name: '', target_field: '取引先グループ化（親会社等への名寄せ）', condition_type: '請求書自動合算', condition_value: '', action: '複数請求書を束ねて一括消込候補に提示', is_active: true
});

onMounted(() => {
    fetchRules();
});

const openNewModal = () => {
    editingRule.value = {
        id: '', name: '', target_field: '取引先グループ化（親会社等への名寄せ）', condition_type: '請求書自動合算', condition_value: '', action: '複数請求書を束ねて一括消込候補に提示', is_active: true
    };
    isEditing.value = false;
    showModal.value = true;
};

const editRule = (rule: MatchingRule) => {
    editingRule.value = { ...rule };
    isEditing.value = true;
    showModal.value = true;
};

const handleDeleteRule = async (id: string) => {
    if (!confirm('このルールを削除してもよろしいですか？')) return;
    const success = await deleteRule(id);
    if (!success) alert('削除に失敗しました。');
};

const saveRule = async () => {
    isSaving.value = true;
    try {
        const { id, ...data } = editingRule.value;
        if (isEditing.value) {
            await updateRule(id, data);
        } else {
            await createRule(data);
        }
        showModal.value = false;
    } catch {
        alert('保存に失敗しました。');
    } finally {
        isSaving.value = false;
    }
};

</script>

<template>
    <div class="p-6 md:p-8 max-w-7xl mx-auto">
        <!-- Header -->
        <div class="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-8">
            <div class="flex-1 pr-4">
                <h1 class="text-2xl font-bold text-slate-900 flex items-center gap-2">
                    <ArrowRightLeft class="w-6 h-6 text-blue-600" />
                    消込条件ルール設定
                </h1>
                <div class="mt-2 text-sm text-slate-600 leading-relaxed space-y-1">
                    <p><span class="font-bold text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">AI自動補正:</span> 基本的な名寄せ（半角全角の違い、株式会社/㈱の表記揺れ等）や、少額の振込手数料判定などはAIが過去の傾向から自動で推論・補正します。</p>
                    <p>AIの自動推論では判断が難しい<span class="font-semibold text-slate-800">「特殊な合算払い（A社とB社の請求がC社名義で振り込まれる等）」</span>の独自ルールがある場合のみ、こちらに登録してください。</p>
                </div>
            </div>
            <button @click="openNewModal" class="shrink-0 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg text-sm font-bold transition-colors shadow-sm w-[180px]">
                <Plus class="w-5 h-5" />
                <span>新規ルール作成</span>
            </button>
        </div>

        <!-- Toolbar -->
        <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col sm:flex-row gap-4 mb-6">
            <div class="relative flex-1">
                <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                    v-model="searchQuery"
                    type="text"
                    placeholder="ルール名、対象項目、アクションで検索..."
                    class="w-full pl-9 pr-4 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                />
            </div>
        </div>

        <!-- Table -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-50 border-b border-slate-200">
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">ステータス</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">対象項目</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">条件</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">設定値</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">アクション</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase text-right">操作</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        <tr v-if="isLoading">
                            <td colspan="6" class="p-8 text-center text-slate-500 text-sm">読み込み中...</td>
                        </tr>
                        <template v-else>
                        <tr v-for="rule in filteredRules" :key="rule.id" class="hover:bg-slate-50 transition-colors group">
                            <td class="p-4">
                                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-bold"
                                    :class="rule.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">
                                    {{ rule.is_active ? '有効' : '無効' }}
                                </span>
                            </td>
                            <td class="p-4">
                                <span class="text-sm font-bold text-slate-800">{{ rule.target_field }}</span>
                            </td>
                            <td class="p-4">
                                <span class="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-50 text-blue-700 font-medium text-xs border border-blue-100">
                                    {{ rule.condition_type }}
                                </span>
                            </td>
                            <td class="p-4">
                                <span class="text-sm text-slate-600">{{ rule.condition_value }}</span>
                            </td>
                            <td class="p-4">
                                <span class="text-sm font-medium text-slate-700">{{ rule.action }}</span>
                            </td>
                            <td class="p-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button @click="editRule(rule)" class="p-1.5 text-slate-400 hover:text-primary hover:bg-primary/10 rounded transition-colors" title="編集">
                                        <Edit class="w-4 h-4" />
                                    </button>
                                    <button @click="handleDeleteRule(rule.id)" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors" title="削除">
                                        <Trash2 class="w-4 h-4" />
                                    </button>
                                </div>
                            </td>
                        </tr>
                        <tr v-if="filteredRules.length === 0">
                            <td colspan="6" class="p-8 text-center text-slate-500 text-sm">
                                設定されているルールがありません。
                            </td>
                        </tr>
                        </template>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Rule Editor Modal -->
        <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div class="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" @click="showModal = false"></div>

            <div class="bg-white rounded-xl shadow-xl w-full max-w-lg relative z-10 flex flex-col overflow-hidden max-h-[90vh]">
                <div class="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                    <h2 class="text-lg font-bold text-slate-800">
                        {{ isEditing ? 'ルールの編集' : 'ルールの新規追加' }}
                    </h2>
                    <button @click="showModal = false" class="text-slate-400 hover:text-slate-600 transition-colors p-1">
                        <X class="w-5 h-5" />
                    </button>
                </div>

                <div class="p-6 overflow-y-auto space-y-4">
                    <div class="flex items-center gap-3 mb-2">
                        <label class="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" v-model="editingRule.is_active" class="sr-only peer">
                            <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                            <span class="ml-3 text-sm font-medium text-slate-700">ルールを有効化</span>
                        </label>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-700 mb-1.5">対象ルール種別</label>
                        <select v-model="editingRule.target_field" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600">
                            <option>取引先グループ化（親会社等への名寄せ）</option>
                            <option>特殊な振込先名義の紐付け</option>
                            <option>その他 AIへの個別指示</option>
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-700 mb-1.5">マッチング条件（AIへの指示内容）</label>
                        <select v-model="editingRule.condition_type" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600">
                            <option>請求書自動合算</option>
                            <option>特定キーワードに基づく強制マッチング</option>
                            <option>除外キーワード指定</option>
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-700 mb-1.5">条件の具体例・詳細記述</label>
                        <input type="text" v-model="editingRule.condition_value" placeholder="例: A社とB社の請求はいつも親会社のC社名義で振り込まれる" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600">
                        <p class="text-[10px] text-slate-500 mt-1">※AIが標準で判断できない、貴社特有の振込・名寄せルールを具体的に文章で指示してください。</p>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-700 mb-1.5">期待するアクション</label>
                        <select v-model="editingRule.action" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600">
                            <option>複数請求書を束ねて一括消込候補に提示</option>
                            <option>自動消込を実行</option>
                            <option>要確認フラグを立てて担当者に通知</option>
                        </select>
                    </div>
                </div>

                <div class="px-6 py-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3">
                    <button @click="showModal = false" class="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">
                        キャンセル
                    </button>
                    <button @click="saveRule" :disabled="isSaving" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-bold rounded-lg transition-colors flex items-center gap-2">
                        <Save class="w-4 h-4" /> {{ isSaving ? '保存中...' : '保存する' }}
                    </button>
                </div>
            </div>
        </div>

    </div>
</template>
