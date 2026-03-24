<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { Code, LayoutTemplate, Save, FileImage, GripVertical, Trash2, PlusCircle, Columns } from 'lucide-vue-next';

const props = defineProps<{
    show: boolean;
    initialName: string;
    initialHtml: string;
}>();

const emit = defineEmits<{
    (e: 'close'): void;
    (e: 'save', payload: { name: string, html: string }): void;
}>();

const templateName = ref(props.initialName);
const templateHtml = ref(props.initialHtml);
const activeTab = ref<'visual' | 'code'>('visual');

// Keep local state in sync when modal opens
watch(() => props.show, (newVal) => {
    if (newVal) {
        templateName.value = props.initialName.replace(/\.[^/.]+$/, ""); // Strip extension
        if (!templateName.value) templateName.value = '新規抽出テンプレート';
        templateHtml.value = props.initialHtml || '<div></div>';
        activeTab.value = 'code';
    }
});

const handleSave = () => {
    emit('save', {
        name: templateName.value,
        html: templateHtml.value
    });
};

// Simplified dynamic preview strictly for modal visualization
const previewHtml = computed(() => {
    return templateHtml.value
        .replace(/\{\{\s*client_name\s*\}\}/g, '株式会社サンプル 御中')
        .replace(/\{\{\s*issue_date\s*\}\}/g, '2024-XX-XX')
        .replace(/\{\{\s*due_date\s*\}\}/g, '2024-XX-XX')
        .replace(/\{\{\s*total_amount\s*\}\}/g, '110,000');
});

// --- DRAG AND DROP VISUAL BUILDER ---
interface TemplateBlock {
    id: string;
    name: string;
    content: string;
}

const availableBlocks = ref<TemplateBlock[]>([
    { id: 'b1', name: '【ヘッダー】タイトル', content: '<h1 style="color: #1e3a8a; border-bottom: 2px solid #1e3a8a; padding-bottom: 10px; margin-top: 0;">御請求書</h1>' },
    { id: 'b2', name: '【宛名】取引先情報', content: '<div style="font-size: 1.2rem; margin-top: 30px;"><h2><span class="var-client_name" style="border-bottom: 1px dotted #ccc;">{{ client_name }}</span> 御中</h2></div>' },
    { id: 'b3', name: '【情報】日付・自社情報', content: '<div style="text-align: right; color: #666; margin-top: 10px;"><p>発行日: <span class="var-issue_date">{{ issue_date }}</span></p><p>支払期限: <span class="var-due_date">{{ due_date }}</span></p><br><p>自社株式会社<br>東京都渋谷区xxxxx<br>T-1234567890</p></div>' },
    { id: 'b4', name: '【金額】ご請求合計', content: '<div style="margin-top: 50px; background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center;"><p style="font-size: 1.1rem; margin: 0; color: #475569;">ご請求金額 (税込)</p><p style="font-size: 2.5rem; font-weight: bold; margin: 10px 0 0 0; color: #0f172a;">¥<span class="var-total_amount">{{ total_amount }}</span></p></div>' },
    { id: 'b5', name: '【明細】品目リスト', content: '<table style="width: 100%; margin-top: 40px; border-collapse: collapse;"><thead><tr style="background: #1e3a8a; color: white;"><th style="padding: 12px; text-align: left;">品目</th><th style="padding: 12px; text-align: right;">金額</th></tr></thead><tbody><tr><td style="padding: 12px; border-bottom: 1px solid #eee;">サービス基本料</td><td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">¥100,000</td></tr><tr><td style="padding: 12px; border-bottom: 1px solid #eee;">消費税 (10%)</td><td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">¥10,000</td></tr></tbody></table>' },
    { id: 'b6', name: '【備考】メッセージ', content: '<div style="margin-top: 40px; padding: 15px; border-left: 4px solid #1e3a8a; background: #f8fafc; color: #475569;"><p style="margin: 0; font-size: 0.9rem;">備考：お振込手数料は貴社にてご負担をお願い申し上げます。</p></div>' },
]);

const canvasBlocks = ref<TemplateBlock[]>([...availableBlocks.value]);
const draggedItemIndex = ref<number | null>(null);

const handleDragStart = (e: DragEvent, index: number) => {
    draggedItemIndex.value = index;
    if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', index.toString());
    }
};

const handleDragOver = (e: DragEvent, index: number) => {
    e.preventDefault();
    if (draggedItemIndex.value === null || draggedItemIndex.value === index) return;
    
    const items = [...canvasBlocks.value];
    const draggedItem = items[draggedItemIndex.value];
    
    items.splice(draggedItemIndex.value, 1);
    items.splice(index, 0, draggedItem);
    
    canvasBlocks.value = items;
    draggedItemIndex.value = index;
    
    updateFromCanvas();
};

const handleDragEnd = () => {
    draggedItemIndex.value = null;
};

const removeBlock = (index: number) => {
    canvasBlocks.value.splice(index, 1);
    updateFromCanvas();
};

const addBlock = (block: TemplateBlock) => {
    canvasBlocks.value.push({...block, id: 'b' + Date.now()});
    updateFromCanvas();
};

const updateFromCanvas = () => {
    let html = '<div style="font-family: sans-serif; padding: 40px; color: #333;">\n';
    canvasBlocks.value.forEach(b => {
        html += b.content + '\n';
    });
    html += '</div>';
    templateHtml.value = html;
};

</script>

<template>
    <div v-if="show" class="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 lg:p-12">
        <div class="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" @click="emit('close')"></div>
        
        <div class="bg-gray-50 rounded-xl shadow-2xl w-full max-w-[850px] h-full max-h-[90vh] relative z-10 flex flex-col overflow-hidden border border-gray-200">
            
            <!-- Header -->
            <div class="bg-white border-b border-gray-200 shrink-0">
                <div class="px-6 py-4 flex justify-between items-center bg-gray-50/50">
                    <div class="flex items-center gap-4">
                        <div class="bg-blue-100 p-2 rounded-lg text-blue-600">
                            <LayoutTemplate class="w-5 h-5" />
                        </div>
                        <div>
                            <h2 class="text-lg font-bold text-gray-900 leading-tight">テンプレート情報の確認・編集</h2>
                            <p class="text-xs text-gray-500 mt-0.5">AIが抽出したテンプレートのレイアウト微調整と名前変更を行います。</p>
                        </div>
                    </div>

                    <div class="flex items-center gap-3">
                        <button @click="emit('close')" class="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg transition-colors border border-gray-200">
                            キャンセル
                        </button>
                        <button @click="handleSave" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2 shadow-sm">
                            <Save class="w-4 h-4" /> ギャラリーに保存
                        </button>
                    </div>
                </div>
                
                <!-- Template Name Row -->
                <div class="px-6 py-3 border-t border-gray-100 flex items-center gap-4 bg-white">
                    <label class="text-sm font-bold text-gray-700 whitespace-nowrap">テンプレート名:</label>
                    <div class="relative flex-1 max-w-2xl">
                        <input 
                            v-model="templateName" 
                            type="text" 
                            placeholder="テンプレート名を入力してください"
                            class="w-full border-2 border-gray-200 rounded-xl px-4 py-2 text-base focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 font-bold transition-all outline-none" 
                        />
                        <div class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-300">
                            <FileText class="w-5 h-5" />
                        </div>
                    </div>
                </div>
            </div>

            <!-- Body Area - Stacked Vertical Layout -->
            <div class="flex-1 flex flex-col overflow-hidden">
                
                <!-- Top Pane: Editor -->
                <div class="h-1/2 flex flex-col border-b border-gray-200 shadow-sm z-10">
                    <div class="bg-slate-800 px-4 py-3 flex items-center justify-between shrink-0">
                        <span class="text-white font-bold text-xs flex items-center gap-2 tracking-wide uppercase"><Code class="w-4 h-4 text-slate-400" /> HTML Editor</span>
                        <div class="flex bg-slate-700 rounded p-0.5">
                            <button @click="activeTab = 'visual'" class="px-3 py-1 text-xs font-bold rounded transition-colors" :class="activeTab === 'visual' ? 'bg-slate-500 text-white' : 'text-slate-300 hover:text-white'">Visual Mock</button>
                            <button @click="activeTab = 'code'" class="px-3 py-1 text-xs font-bold rounded transition-colors" :class="activeTab === 'code' ? 'bg-slate-500 text-white' : 'text-slate-300 hover:text-white'">Source Code</button>
                        </div>
                    </div>

                    <div class="flex-1 relative bg-[#1e1e1e]">
                        <!-- Visual Builder UI -->
                        <div v-if="activeTab === 'visual'" class="absolute inset-0 flex bg-slate-50 overflow-hidden">
                            
                            <!-- Sidebar: Available Blocks -->
                            <div class="w-[240px] shrink-0 bg-white border-r border-gray-200 flex flex-col">
                                <div class="bg-gray-100 p-3 border-b border-gray-200 text-xs font-bold text-gray-700 uppercase tracking-wide flex items-center gap-2">
                                    <Columns class="w-4 h-4 text-gray-500" /> ブロックパーツ
                                </div>
                                <div class="flex-1 overflow-y-auto p-3 space-y-2">
                                    <div v-for="block in availableBlocks" :key="`avail-${block.id}`"
                                         class="p-2.5 bg-white border border-gray-200 rounded shadow-sm hover:border-blue-400 hover:shadow transition-colors group cursor-pointer"
                                         @click="addBlock(block)">
                                        <div class="flex items-center justify-between">
                                            <span class="text-xs font-bold text-gray-800">{{ block.name }}</span>
                                            <PlusCircle class="w-4 h-4 text-gray-400 group-hover:text-blue-500" />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <!-- Canvas: Active Blocks -->
                            <div class="flex-1 flex flex-col bg-slate-50">
                                <div class="bg-gray-100 p-3 border-b border-gray-200 text-xs font-bold text-gray-700 uppercase tracking-wide text-center">
                                    レイアウトキャンバス (ドラッグで並び替え)
                                </div>
                                <div class="flex-1 overflow-y-auto p-6">
                                    <div class="space-y-3 min-h-[500px] border-2 border-dashed border-gray-300 rounded-xl p-4 bg-white/50">
                                        <div v-for="(block, index) in canvasBlocks" :key="block.id"
                                             draggable="true"
                                             @dragstart="handleDragStart($event, index)"
                                             @dragover="handleDragOver($event, index)"
                                             @dragend="handleDragEnd"
                                             @drop.prevent=""
                                             class="group relative flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg shadow-sm cursor-move hover:ring-2 hover:ring-blue-400 hover:border-blue-400 transition-all"
                                             :class="draggedItemIndex === index ? 'opacity-40 scale-95' : 'opacity-100 scale-100'">
                                             
                                            <div class="text-gray-400 cursor-grab active:cursor-grabbing p-1">
                                                <GripVertical class="w-5 h-5" />
                                            </div>
                                            <div class="flex-1 font-bold text-sm text-gray-800">{{ block.name }}</div>
                                            
                                            <button @click="removeBlock(index)" class="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors" title="削除">
                                                <Trash2 class="w-4 h-4" />
                                            </button>
                                        </div>

                                        <div v-if="canvasBlocks.length === 0" class="h-32 flex items-center justify-center text-gray-400 text-sm font-medium border-2 border-dashed border-gray-200 rounded-lg">
                                            左からブロックを追加してください
                                        </div>
                                    </div>
                                </div>
                            </div>

                        </div>
                        <textarea v-else v-model="templateHtml" class="absolute inset-0 w-full h-full bg-transparent text-gray-300 font-mono text-xs p-4 focus:outline-none resize-none" spellcheck="false"></textarea>
                    </div>
                </div>

                <!-- Bottom Pane: Live Preview -->
                <div class="h-1/2 flex flex-col bg-slate-100">
                    <div class="bg-white border-b border-gray-200 px-4 py-3 flex justify-between items-center shrink-0">
                        <span class="text-gray-700 font-bold text-xs flex items-center gap-2 tracking-wide uppercase"><FileImage class="w-4 h-4 text-gray-400" /> Live Preview</span>
                        <div class="text-[10px] text-gray-500 font-medium bg-gray-100 px-2 py-1 rounded">A4 Size Simulated</div>
                    </div>
                    
                    <!-- Preview Container with mock paper shadow and scale -->
                    <div class="flex-1 overflow-y-auto p-4 sm:p-8 flex justify-center items-start bg-gray-200/50">
                        <div class="bg-white shadow-md border border-gray-300 origin-top w-full max-w-[700px] min-h-[990px] p-8 mt-2 mb-8 transform scale-90 origin-top" v-html="previewHtml">
                        </div>
                    </div>
                </div>
            </div>
            
        </div>
    </div>
</template>
