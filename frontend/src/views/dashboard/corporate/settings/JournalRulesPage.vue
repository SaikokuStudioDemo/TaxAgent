<script setup lang="ts">
import { ref, computed } from 'vue';
import { 
    Plus, 
    Search, 
    Edit, 
    Trash2, 
    Save, 
    X,
    BookText
} from 'lucide-vue-next';

interface JournalRule {
    id: string;
    keyword: string;           // 抽出対象のキーワード（例: AMAZON, Slack）
    targetField: '取引先名' | '品目・摘要'; // どこを見て判断するか
    accountSubject: string;    // 自動割り当てする勘定科目（例: 消耗品費）
    taxDivision: string;       // 税区分（例: 課税仕入10%）
    isActive: boolean;
}

// モックデータ：自動仕訳ルール
// ユーザーフィードバック: 「仕訳ルールに関しては、取引先名であったり、商品によっても変わってくると思う」
const rules = ref<JournalRule[]>([
    {
        id: 'J-001',
        keyword: 'AMAZON.CO.JP',
        targetField: '取引先名',
        accountSubject: '消耗品費',
        taxDivision: '課税仕入 10%',
        isActive: true
    },
    {
        id: 'J-002',
        keyword: 'Slack',
        targetField: '品目・摘要',
        accountSubject: '通信費',
        taxDivision: '課税仕入 10%',
        isActive: true
    },
    {
        id: 'J-003',
        keyword: 'タクシー',
        targetField: '品目・摘要',
        accountSubject: '旅費交通費',
        taxDivision: '課税仕入 10%',
        isActive: true
    },
    {
        id: 'J-004',
        keyword: '接待',
        targetField: '品目・摘要',
        accountSubject: '交際費',
        taxDivision: '課税仕入 10%',
        isActive: true
    }
]);

const searchQuery = ref('');

const filteredRules = computed(() => {
    if (!searchQuery.value) return rules.value;
    const lowerQuery = searchQuery.value.toLowerCase();
    return rules.value.filter(r => 
        r.keyword.toLowerCase().includes(lowerQuery) || 
        r.accountSubject.toLowerCase().includes(lowerQuery)
    );
});

// モーダル用ステート
const showModal = ref(false);
const isEditing = ref(false);
const editingRule = ref<JournalRule>({
    id: '', keyword: '', targetField: '品目・摘要', accountSubject: '消耗品費', taxDivision: '課税仕入 10%', isActive: true
});

const openNewModal = () => {
    editingRule.value = {
        id: '', keyword: '', targetField: '品目・摘要', accountSubject: '消耗品費', taxDivision: '課税仕入 10%', isActive: true
    };
    isEditing.value = false;
    showModal.value = true;
};

const editRule = (rule: JournalRule) => {
    editingRule.value = { ...rule };
    isEditing.value = true;
    showModal.value = true;
};

const deleteRule = (id: string) => {
    if (confirm('この仕訳ルールを削除してもよろしいですか？')) {
        rules.value = rules.value.filter(r => r.id !== id);
    }
};

const saveRule = () => {
    if (isEditing.value) {
        const index = rules.value.findIndex(r => r.id === editingRule.value.id);
        if (index !== -1) {
            rules.value[index] = { ...editingRule.value };
        }
    } else {
        rules.value.push({
            ...editingRule.value,
            id: `J-00${rules.value.length + 1}`
        });
    }
    showModal.value = false;
};

</script>

<template>
    <div class="p-6 md:p-8 max-w-7xl mx-auto">
        <!-- Header -->
        <div class="flex flex-col md:flex-row md:items-start justify-between gap-4 mb-8">
            <div class="flex-1 pr-4">
                <h1 class="text-2xl font-bold text-slate-900 flex items-center gap-2">
                    <BookText class="w-6 h-6 text-blue-600" />
                    自動仕訳ルール設定
                </h1>
                <div class="mt-2 text-sm text-slate-600 leading-relaxed space-y-1">
                    <p><span class="font-bold text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">AI自動推論:</span> 基本的な取引明細（摘要や取引先名）からの勘定科目・税区分の割り当ては、AIが明細内容から推論して自動補完します。</p>
                    <p>AIが判断できない特殊な取引や、<span class="font-semibold text-slate-800">「社内独自の勘定項目に強制的に振り分けたい特定のキーワード」</span>がある場合のみ、こちらにルールを追加してください。</p>
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
                    placeholder="キーワード名、勘定科目で検索..." 
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
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">キーワード</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">対象フィールド</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">勘定科目</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase">税区分</th>
                            <th class="p-4 text-xs font-bold text-slate-500 uppercase text-right">操作</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                        <tr v-for="rule in filteredRules" :key="rule.id" class="hover:bg-slate-50 transition-colors group">
                            <td class="p-4">
                                <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-bold" 
                                    :class="rule.isActive ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'">
                                    {{ rule.isActive ? '有効' : '無効' }}
                                </span>
                            </td>
                            <td class="p-4">
                                <span class="text-sm font-bold text-slate-800">{{ rule.keyword }}</span>
                            </td>
                            <td class="p-4">
                                <span class="text-sm text-slate-600">{{ rule.targetField }}</span>
                            </td>
                            <td class="p-4">
                                <span class="inline-flex items-center justify-center px-2.5 py-1 rounded-md bg-purple-50 text-purple-700 font-medium text-xs border border-purple-100">
                                    {{ rule.accountSubject }}
                                </span>
                            </td>
                            <td class="p-4">
                                <span class="text-sm text-slate-600">{{ rule.taxDivision }}</span>
                            </td>
                            <td class="p-4 text-right">
                                <div class="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button @click="editRule(rule)" class="p-1.5 text-slate-400 hover:text-primary hover:bg-primary/10 rounded transition-colors" title="編集">
                                        <Edit class="w-4 h-4" />
                                    </button>
                                    <button @click="deleteRule(rule.id)" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors" title="削除">
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
                        {{ isEditing ? '仕訳ルールの編集' : 'ルールの新規追加' }}
                    </h2>
                    <button @click="showModal = false" class="text-slate-400 hover:text-slate-600 transition-colors p-1">
                        <X class="w-5 h-5" />
                    </button>
                </div>
                
                <div class="p-6 overflow-y-auto space-y-4">
                    <div class="flex items-center gap-3 mb-2">
                        <label class="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" v-model="editingRule.isActive" class="sr-only peer">
                            <div class="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                            <span class="ml-3 text-sm font-medium text-slate-700">ルールを有効化</span>
                        </label>
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-700 mb-1.5">キーワード（抽出対象）</label>
                        <input type="text" v-model="editingRule.keyword" placeholder="例: Amazon, Suica など" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary">
                    </div>

                    <div>
                        <label class="block text-xs font-bold text-slate-700 mb-1.5">判断基準フィールド</label>
                        <select v-model="editingRule.targetField" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary">
                            <option>取引先名</option>
                            <option>品目・摘要</option>
                        </select>
                        <p class="text-[10px] text-slate-500 mt-1">※商品名や取引先名のどちらをキーワード検索の対象にするか選択してください。</p>
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-bold text-slate-700 mb-1.5">割り当て: 勘定科目</label>
                            <select v-model="editingRule.accountSubject" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary">
                                <option>消耗品費</option>
                                <option>通信費</option>
                                <option>旅費交通費</option>
                                <option>交際費</option>
                                <option>支払手数料</option>
                                <option>売上高</option>
                                <option>対象外（登録しない）</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 mb-1.5">割り当て: 税区分</label>
                            <select v-model="editingRule.taxDivision" class="w-full border border-slate-300 rounded-lg p-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary">
                                <option>課税仕入 10%</option>
                                <option>課税仕入 8% (軽減)</option>
                                <option>非課税仕入</option>
                                <option>不課税仕入</option>
                            </select>
                        </div>
                    </div>
                </div>
                
                <div class="px-6 py-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3">
                    <button @click="showModal = false" class="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors">
                        キャンセル
                    </button>
                    <button @click="saveRule" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-lg transition-colors flex items-center gap-2">
                        <Save class="w-4 h-4" /> 保存する
                    </button>
                </div>
            </div>
        </div>

    </div>
</template>
