<script setup lang="ts">
import { ref, computed } from 'vue';
import { ChevronLeft, Plus, CheckCircle, Save, Send, FileText, Loader2, Building2, AlertCircle, Trash2, FileImage, X } from 'lucide-vue-next';
import { useRouter } from 'vue-router';
import ClientFormModal from '@/components/invoices/ClientFormModal.vue';
import TemplateEditorModal from '@/components/invoices/TemplateEditorModal.vue';
import { useCompanyProfiles } from '@/composables/useCompanyProfiles';

const router = useRouter();

// --- STATE ---
const isModalOpen = ref(false);
const isTemplateEditorOpen = ref(false);
const latestExtractedHtml = ref('');
const latestExtractedName = ref('');
const invoiceType = ref<'single' | 'recurring'>('single');

// --- TEMPLATE GALLERY ---
interface InvoiceTemplate {
    id: string;
    name: string;
    description: string;
    thumbnail: string; // CSS class for mock preview
    isActive: boolean;
}

const templates = ref<InvoiceTemplate[]>([
    { id: 'T-001', name: '請求書A', description: '標準的でプロフェッショナルなレイアウト', thumbnail: 'bg-blue-50 border-blue-200', isActive: true },
    { id: 'T-002', name: '請求書B', description: 'シンプルでミニマルなデザイン', thumbnail: 'bg-gray-50 border-gray-200', isActive: false },
    { id: 'T-003', name: '請求書C', description: '内訳が豊富な詳細フォーマット', thumbnail: 'bg-slate-50 border-slate-200', isActive: false },
    { id: 'T-004', name: '請求書D', description: 'モダンでスタイリッシュな外観', thumbnail: 'bg-purple-50 border-purple-200', isActive: false },
]);

const selectedTemplateId = ref('T-001');

// --- TEMPLATE STATE ---
const isTemplateUploaded = ref(true); // Default to true since T-001 is selected
const isExtracting = ref(false); 
const templateName = ref('default_invoice_template.html');
const templateHtml = ref(`
<div style="font-family: sans-serif; padding: 40px; color: #333;">
    <h1 style="color: #1e3a8a; border-bottom: 2px solid #1e3a8a; padding-bottom: 10px;">御請求書</h1>
    <div style="margin-top: 30px; display: flex; justify-content: space-between;">
        <div style="font-size: 1.2rem;">
            <h2><span class="var-client_name" style="border-bottom: 1px dotted #ccc;">{{ client_name }}</span> 御中</h2>
        </div>
        <div style="text-align: right; color: #666;">
            <p>発行日: <span class="var-issue_date">{{ issue_date }}</span></p>
            <p>支払期限: <span class="var-due_date">{{ due_date }}</span></p>
            <br>
            <p>自社株式会社<br>東京都渋谷区xxxxx<br>T-1234567890</p>
        </div>
    </div>
    <div style="margin-top: 50px; background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center;">
        <p style="font-size: 1.1rem; margin: 0; color: #475569;">ご請求金額 (税込)</p>
        <p style="font-size: 2.5rem; font-weight: bold; margin: 10px 0 0 0; color: #0f172a;">¥<span class="var-total_amount">{{ total_amount }}</span></p>
    </div>
    <table style="width: 100%; margin-top: 40px; border-collapse: collapse;">
        <thead>
            <tr style="background: #1e3a8a; color: white;">
                <th style="padding: 12px; text-align: left;">品目</th>
                <th style="padding: 12px; text-align: right;">金額</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">サービス基本料</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">¥100,000</td>
            </tr>
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">消費税 (10%)</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">¥10,000</td>
            </tr>
        </tbody>
    </table>
</div>`); 

const selectTemplate = (id: string) => {
    selectedTemplateId.value = id;
    if (id === 'T-001') {
        isTemplateUploaded.value = true;
    } else {
        isTemplateUploaded.value = false;
        templateHtml.value = '';
    }
};

// --- TEMPLATE DELETION ---
const templateToDelete = ref<InvoiceTemplate | null>(null);

const confirmDeleteTemplate = (templ: InvoiceTemplate) => {
    templateToDelete.value = templ;
};

const executeDeleteTemplate = () => {
    if (!templateToDelete.value) return;
    
    // Remove from array
    templates.value = templates.value.filter(t => t.id !== templateToDelete.value?.id);
    
    // Fallback selection if the deleted one was selected
    if (selectedTemplateId.value === templateToDelete.value.id) {
        if (templates.value.length > 0) {
            selectTemplate(templates.value[0].id);
        } else {
            selectedTemplateId.value = '';
            isTemplateUploaded.value = false;
            templateHtml.value = '';
        }
    }
    
    templateToDelete.value = null;
};

const showCodeEditor = ref(false); 

const templateVariables = ref([
    { key: 'client_name', label: '取引先名', value: '株式会社クライアント 御中' },
    { key: 'issue_date', label: '発行日', value: '2024-10-24' },
    { key: 'due_date', label: 'お支払期限', value: '2024-11-30' },
    { key: 'total_amount', label: 'ご請求金額', value: '110,000' }
]);

// --- INVOICE DATA ---
const invoiceNumber = ref(`INV-${new Date().getFullYear()}${String(new Date().getMonth() + 1).padStart(2, '0')}-001`);
const issueDate = ref('2024-10-24');
const dueDate = ref('2024-11-30');

// --- ITEMS & TOTALS ---
interface LineItem {
    id: number;
    description: string;
    quantity: number;
    unitPrice: number;
    taxRate: number; // e.g. 0.10 for 10%
}

const items = ref<LineItem[]>([
    { id: 1, description: '', quantity: 1, unitPrice: 0, taxRate: 0.10 }
]);

const note = ref('');

// --- COMPUTED ---
const subtotal = computed(() => {
    return items.value.reduce((sum, item) => sum + (item.quantity * item.unitPrice), 0);
});

const taxAmount = computed(() => {
    return items.value.reduce((sum, item) => sum + (item.quantity * item.unitPrice * item.taxRate), 0);
});

const totalAmount = computed(() => subtotal.value + taxAmount.value);

// --- METHODS ---
const addItem = () => {
    items.value.push({
        id: Date.now(),
        description: '',
        quantity: 1,
        unitPrice: 0,
        taxRate: 0.10
    });
};

const removeItem = (id: number) => {
    if (items.value.length > 1) {
        items.value = items.value.filter(item => item.id !== id);
    }
};

const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('ja-JP').format(amount);
};

const applyTemplate = (e: Event) => {
    // Simulate reading an uploaded PDF/Excel file and AI converting it to HTML
    const target = e.target as HTMLInputElement;
    if (target.files && target.files.length > 0) {
        const file = target.files[0];
        templateName.value = file.name;
        isExtracting.value = true;
        
        // Trigger AI Upload Flow (simulated)
        const newTemplateId = `T-${Date.now()}`;
        templates.value.unshift({
            id: newTemplateId,
            name: file.name,
            description: 'AI生成テンプレート',
            thumbnail: 'bg-emerald-50 border-emerald-200',
            isActive: true
        });
        selectTemplate(newTemplateId); // Select the newly uploaded template

        setTimeout(() => {
            isExtracting.value = false;
            latestExtractedName.value = file.name;
            
            // Mock template data (The "AI generated" HTML result)
            latestExtractedHtml.value = `
<div style="font-family: sans-serif; padding: 40px; color: #333;">
    <h1 style="color: #1e3a8a; border-bottom: 2px solid #1e3a8a; padding-bottom: 10px;">御請求書</h1>
    <div style="margin-top: 30px; display: flex; justify-content: space-between;">
        <div style="font-size: 1.2rem;">
            <h2><span class="var-client_name" style="border-bottom: 1px dotted #ccc;">{{ client_name }}</span> 御中</h2>
        </div>
        <div style="text-align: right; color: #666;">
            <p>発行日: <span class="var-issue_date">{{ issue_date }}</span></p>
            <p>支払期限: <span class="var-due_date">{{ due_date }}</span></p>
            <br>
            <p>自社株式会社<br>東京都渋谷区xxxxx<br>T-1234567890</p>
        </div>
    </div>
    <div style="margin-top: 50px; background: #f8fafc; padding: 20px; border-radius: 8px; text-align: center;">
        <p style="font-size: 1.1rem; margin: 0; color: #475569;">ご請求金額 (税込)</p>
        <p style="font-size: 2.5rem; font-weight: bold; margin: 10px 0 0 0; color: #0f172a;">¥<span class="var-total_amount">{{ total_amount }}</span></p>
    </div>
    <table style="width: 100%; margin-top: 40px; border-collapse: collapse;">
        <thead>
            <tr style="background: #1e3a8a; color: white;">
                <th style="padding: 12px; text-align: left;">品目</th>
                <th style="padding: 12px; text-align: right;">金額</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">サービス基本料</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">¥100,000</td>
            </tr>
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #eee;">消費税 (10%)</td>
                <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">¥10,000</td>
            </tr>
        </tbody>
    </table>
</div>`;
            isTemplateEditorOpen.value = true;
        }, 2000);
    }
};

const handleTemplateSave = (payload: { name: string, html: string }) => {
    isTemplateEditorOpen.value = false;
    
    // Create new template entry
    const newTemplateId = `T-${Date.now()}`;
    templates.value.unshift({
        id: newTemplateId,
        name: payload.name,
        description: 'ユーザー登録テンプレート',
        thumbnail: 'bg-emerald-50 border-emerald-200',
        isActive: true
    });
    
    // For this mock, inject html to the preview directly
    templateHtml.value = payload.html;
    selectedTemplateId.value = newTemplateId;
    isTemplateUploaded.value = true;
};

const goBack = () => {
    router.push('/dashboard/corporate/invoices/list');
};
// State for sender info
const { profiles: senderProfiles, formatProfileForTextarea } = useCompanyProfiles();

// Set the active profile to the default one if available, otherwise just use the first
const defaultProfile = senderProfiles.value.find(p => p.isDefault) || senderProfiles.value[0];
const activeSenderProfile = ref(defaultProfile ? defaultProfile.id : '');

const senderInfo = computed(() => {
    const profile = senderProfiles.value.find(p => p.id === activeSenderProfile.value);
    return profile ? formatProfileForTextarea(profile) : '';
});

// Mock data for Client dropdown
const activeClientId = ref('');
const availableClients = ref([
    { id: 'C-1001', name: '株式会社Aoyama Systems', contactPerson: '田中 健太' },
    { id: 'C-1002', name: 'BlueOcean Inc.', contactPerson: 'David Smith' },
    { id: 'C-1003', name: '山口会計事務所', contactPerson: '山口 太郎' }
]);

const handleClientSelection = () => {
    if (!activeClientId.value) {
        templateVariables.value[0].value = '';
        return;
    }
    // Simulate fetching full details
    const selected = availableClients.value.find(c => c.id === activeClientId.value);
    if (selected) {
        templateVariables.value[0].value = `${selected.name} 御中\n担当: ${selected.contactPerson} 様\n〒100-0000\n東京都...`;
    }
};

const handleClientSave = (clientData: any) => {
    // Add to available clients list
    availableClients.value.push(clientData);
    activeClientId.value = clientData.id;
    
    // Auto-fill the client textarea preview with the saved client info
    templateVariables.value[0].value = `${clientData.name} 御中\n担当: ${clientData.contactPerson} 様\n〒${clientData.postalCode}\n${clientData.address}\nTEL: ${clientData.phone}`;
    isModalOpen.value = false;
};

</script>

<template>
  <div class="h-full flex flex-col bg-slate-50">
    <!-- Header -->
    <header class="bg-white border-b border-gray-200 px-8 py-5 flex items-center justify-between shrink-0 z-10 sticky top-0 shadow-sm">
      <div class="flex items-center gap-4">
        <button @click="goBack" class="p-2 hover:bg-gray-100 rounded-lg transition-colors text-gray-500">
          <ChevronLeft class="w-5 h-5" />
        </button>
        <div>
          <h1 class="text-xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
             請求書発行
          </h1>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <div class="bg-blue-50 text-blue-700 px-3 py-1.5 rounded-lg text-sm font-bold flex items-center gap-2 mr-4 border border-blue-100">
            <span class="relative flex h-2 w-2">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            編集中
        </div>
        <button class="bg-white border border-gray-300 text-gray-700 px-5 py-2.5 rounded-lg hover:bg-gray-50 transition-colors font-medium text-sm flex items-center shadow-sm">
            <Save class="w-4 h-4 mr-2" />下書き保存
        </button>
        <button class="bg-blue-600 text-white px-6 py-2.5 rounded-lg hover:bg-blue-700 transition-colors font-bold text-sm flex items-center shadow-sm shadow-blue-600/20">
            <Send class="w-4 h-4 mr-2" />発行・送付する
        </button>
      </div>
    </header>

    <!-- Main Content -->
    <div class="flex-1 overflow-y-auto bg-gray-50/50 p-8">
      <div class="max-w-[1400px] mx-auto grid grid-cols-12 gap-8">
        
        <!-- Left Side: Invoice Editor -->
        <div class="col-span-12 xl:col-span-8 space-y-8">
            
            <!-- TEMPLATE GALLERY -->
            <div>
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-xl font-bold text-gray-900">インボイス・テンプレートを選択</h2>
                    
                    <label class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm flex items-center shadow-sm cursor-pointer">
                        <Plus class="w-4 h-4 mr-2" />テンプレート登録
                        <input type="file" accept=".pdf, .xlsx, .xls, .doc, .docx" @change="applyTemplate" class="hidden" />
                    </label>
                </div>
                
                <div class="flex gap-4 overflow-x-auto pb-4 -mx-2 px-2 snap-x">
                    <!-- Loading state representing a template being scanned by AI -->
                    <div v-if="isExtracting" class="w-[220px] shrink-0 border-2 border-dashed border-blue-400 rounded-xl bg-blue-50/50 flex flex-col items-center justify-center p-6 min-h-[280px]">
                         <Loader2 class="w-8 h-8 text-blue-500 animate-spin mb-3" />
                         <p class="font-bold text-sm text-blue-800 text-center leading-tight">AIが「{{ templateName }}」を<br>解析中です...</p>
                         <p class="text-[10px] text-blue-600 mt-2 text-center">レイアウトを抽出して<br>フォームブロックを生成</p>
                    </div>

                    <div v-for="templ in templates" :key="templ.id" 
                         @click="selectTemplate(templ.id)"
                         class="w-[220px] shrink-0 rounded-xl cursor-pointer transition-all snap-start relative flex flex-col"
                         :class="selectedTemplateId === templ.id ? 'ring-2 ring-blue-600 shadow-md transform -translate-y-1' : 'border border-gray-200 hover:border-gray-300 hover:shadow-sm bg-white'">
                        
                        <!-- Miniature Preview Mockup inside Card -->
                        <div class="h-[200px] rounded-t-xl bg-gray-50 p-4 w-full flex flex-col gap-2 border-b border-gray-100 relative overflow-hidden group">
                            
                            <!-- Delete Button -->
                            <button v-if="templ.id !== 'T-001'" @click.stop="confirmDeleteTemplate(templ)" class="absolute top-2 right-2 p-1.5 bg-white shadow-sm border border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200 hover:bg-red-50 rounded-full opacity-0 group-hover:opacity-100 transition-all z-10" title="テンプレートを削除">
                                <X class="w-4 h-4" />
                            </button>

                            <div class="w-16 h-3 bg-gray-300 rounded mb-4" :class="templ.id === 'T-001' ? 'bg-blue-500' : templ.id === 'T-002' ? 'bg-gray-800' : 'bg-slate-600'"></div>
                            <div class="w-full h-1.5 bg-gray-200 rounded"></div>
                            <div class="w-3/4 h-1.5 bg-gray-200 rounded"></div>
                            <div class="flex justify-end mt-4"><div class="w-20 h-10 bg-gray-200 rounded flex flex-col gap-1 items-end pt-1 pr-1"><div class="w-8 h-1 bg-gray-300 rounded"></div><div class="w-12 h-1 bg-gray-300 rounded"></div><div class="w-12 h-1 bg-blue-300 rounded"></div></div></div>
                            <div class="w-full h-8 bg-gray-100 border border-gray-200 rounded mt-4"></div>
                            
                            <!-- Selection Overlay styling -->
                            <div v-if="selectedTemplateId === templ.id" class="absolute inset-0 border-4 border-blue-600/10 rounded-t-xl pointer-events-none"></div>
                        </div>

                        <!-- Card Info -->
                        <div class="p-3 bg-white rounded-b-xl flex-1 flex flex-col justify-between">
                            <div class="flex items-center justify-between mb-1">
                                <span class="font-bold text-sm text-gray-900">{{ templ.name }}</span>
                                <CheckCircle v-if="selectedTemplateId === templ.id" class="w-4 h-4 text-blue-600" />
                            </div>
                            <p class="text-[10px] text-gray-500 leading-tight">{{ templ.description }}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- INVOICE INFO INPUT FORM -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden" v-if="!isExtracting">
                
                <!-- Accordion style header -->
                <div class="px-6 py-4 border-b border-gray-100 bg-slate-50 flex items-center gap-2">
                    <FileText class="w-5 h-5 text-blue-600" />
                    <h2 class="font-bold text-gray-900 text-lg">請求書情報入力</h2>
                </div>

                <div class="p-8 space-y-8">
                    
                    <!-- Row 1: Key Dates & IDs -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-2">請求書番号</label>
                            <input v-model="invoiceNumber" type="text" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-blue-500 focus:border-blue-500 font-mono" />
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-2">発行日</label>
                            <input v-model="issueDate" type="date" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-blue-500 focus:border-blue-500" />
                        </div>
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-2">支払期日</label>
                            <input v-model="dueDate" type="date" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-blue-500 focus:border-blue-500" />
                        </div>
                    </div>

                    <!-- Row 2: Client & Sender Info Layout -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 pb-4">
                        <!-- Client Info Section -->
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-2">請求先情報</label>
                            
                            <div class="border border-gray-200 rounded-lg bg-gray-50 flex flex-col group hover:border-blue-300 transition-colors relative overflow-hidden">
                                <!-- Internal Content -->
                                <div class="p-5 flex-1 relative">
                                    <!-- Smart Dropdown Header -->
                                    <div class="mb-3 relative">
                                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                            <Building2 class="h-4 w-4 text-gray-400" />
                                        </div>
                                        <select 
                                            v-model="activeClientId" 
                                            @change="handleClientSelection"
                                            class="block w-full pl-10 pr-10 py-2 text-sm border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md bg-white shadow-sm"
                                        >
                                            <option value="">取引先を選択してください</option>
                                            <option v-for="client in availableClients" :key="client.id" :value="client.id">
                                                {{ client.name }}
                                            </option>
                                        </select>
                                    </div>

                                    <textarea 
                                        v-model="templateVariables[0].value" 
                                        class="w-full h-24 bg-transparent border-0 resize-none focus:ring-0 p-0 text-sm leading-relaxed" 
                                        placeholder="株式会社クライアント 御中\n担当：佐藤 健太 様\n東京都港区六本木...\n03-0000-0000"
                                    ></textarea>
                                </div>

                                <!-- Bottom Action Bar -->
                                <div class="bg-white border-t border-gray-200 px-4 py-2 flex justify-center shrink-0 transition-colors">
                                    <button @click="isModalOpen = true" class="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors flex items-center justify-center gap-1 py-1 px-2 hover:bg-blue-50 rounded w-full">
                                        <Plus class="w-3.5 h-3.5" /> 新規取引先を追加
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Sender Info Section -->
                        <div>
                            <label class="block text-xs font-bold text-gray-700 mb-2">請求元情報</label>
                            
                            <div class="border border-gray-200 rounded-lg bg-gray-50 flex flex-col relative group overflow-hidden">
                                <div class="p-5 flex-1 relative">
                                    <!-- Multi-Sender Switcher -->
                                    <div class="mb-3">
                                        <select 
                                            v-model="activeSenderProfile" 
                                            class="block w-full py-1.5 pl-3 pr-10 text-sm border-gray-300 focus:outline-none focus:ring-amber-500 focus:border-amber-500 rounded-md bg-white shadow-sm text-gray-700 font-medium"
                                        >
                                            <option v-for="profile in senderProfiles" :key="profile.id" :value="profile.id">
                                                自社プロファイル: {{ profile.name }}
                                            </option>
                                        </select>
                                    </div>

                                    <textarea 
                                        :value="senderInfo"
                                        class="w-full h-24 bg-transparent border-0 resize-none focus:ring-0 p-0 text-gray-600 text-sm leading-relaxed outline-none" 
                                        readonly
                                    ></textarea>
                                </div>

                                <!-- Bottom Action Bar (Optional, for consistency or editing profiles in the future) -->
                                <div class="bg-white border-t border-gray-200 px-4 py-2 flex justify-center shrink-0">
                                    <router-link to="/dashboard/corporate/settings/company" class="text-xs font-bold text-gray-500 hover:text-gray-700 transition-colors flex items-center justify-center gap-1 py-1 px-2 hover:bg-gray-50 rounded w-full">
                                        自社マスター設定を開く
                                    </router-link>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                </div>
            </div>
            
            <!-- Items Data Table (Standard functionality kept alongside dynamic template) -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden" v-if="!isExtracting">
                <div class="px-6 py-4 border-b border-gray-100 bg-slate-50 flex items-center gap-2">
                    <h3 class="font-bold text-gray-900 text-lg">品目リスト</h3>
                </div>
                <div class="p-0">
                    <div class="mb-4 grid grid-cols-12 gap-4 px-6 border-b border-gray-200 pb-3">
                        <div class="col-span-5 text-xs font-bold text-gray-500 uppercase tracking-wider">品目名</div>
                        <div class="col-span-2 text-xs font-bold text-gray-500 uppercase tracking-wider text-right">数量</div>
                        <div class="col-span-2 text-xs font-bold text-gray-500 uppercase tracking-wider text-right">単価</div>
                        <div class="col-span-1 text-xs font-bold text-gray-500 uppercase tracking-wider text-right">税率</div>
                        <div class="col-span-2 text-xs font-bold text-gray-500 uppercase tracking-wider text-right pr-4">金額</div>
                    </div>
                    
                    <div class="space-y-0 text-sm bg-white border-b border-gray-200">
                        <div v-for="item in items" :key="item.id" class="grid grid-cols-12 gap-4 items-center group py-4 px-6 border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors">
                            <div class="col-span-5">
                                <input v-model="item.description" type="text" placeholder="例: Webサイト制作・デザイン費用" class="w-full bg-transparent border-0 p-0 text-sm font-medium text-gray-900 focus:ring-0 placeholder-gray-300">
                            </div>
                            <div class="col-span-2">
                                <input v-model="item.quantity" type="number" min="1" class="w-full bg-transparent border-0 p-0 text-sm text-right focus:ring-0">
                            </div>
                            <div class="col-span-2">
                                <input v-model="item.unitPrice" type="number" class="w-full bg-transparent border-0 p-0 text-sm text-right font-medium focus:ring-0">
                            </div>
                            <div class="col-span-1">
                                <select v-model="item.taxRate" class="w-full bg-transparent border-0 p-0 text-sm text-right focus:ring-0 appearance-none bg-no-repeat bg-right pr-4" style="background-image: url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 20 20\'%3E%3Cpath stroke=\'%236b7280\' stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'1.5\' d=\'m6 8 4 4 4-4\'/%3E%3Csvg%3E'); background-size: 1.5em 1.5em;">
                                    <option :value="0.10">10%</option>
                                    <option :value="0.08">8%</option>
                                    <option :value="0">0%</option>
                                </select>
                            </div>
                            <div class="col-span-2 flex items-center justify-end gap-3 font-bold text-gray-900">
                                ¥{{ formatCurrency(item.quantity * item.unitPrice) }}
                                <button @click="removeItem(item.id)" class="text-gray-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100 p-1" title="行を削除">
                                    <Trash2 class="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <button @click="addItem" class="mt-4 text-blue-600 hover:text-blue-700 font-bold text-sm flex items-center transition-colors px-6">
                        <Plus class="w-4 h-4 mr-1" /> 行を追加
                    </button>

                    <!-- Alert for more than 5 items -->
                    <div v-if="items.length > 5" class="mx-6 mt-4 mb-2 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-3 text-blue-800">
                        <AlertCircle class="w-5 h-5 shrink-0 text-blue-600 mt-0.5" />
                        <div class="text-sm">
                            <p class="font-bold">品目数が5行を超えています</p>
                            <p class="text-blue-700 mt-0.5">自動的に「内訳明細書（別紙）」が作成され、請求書本紙には「合計金額および一式」の合算のみが記載されます。</p>
                        </div>
                    </div>

                    <!-- Totals -->
                    <div class="px-6 py-4 bg-slate-50 border-t border-gray-200 mt-4 flex justify-end">
                        <div class="w-72 space-y-2 text-sm">
                            <div class="flex justify-between text-gray-600">
                                <span>小計</span>
                                <span>¥{{ formatCurrency(subtotal) }}</span>
                            </div>
                            <div class="flex justify-between text-gray-600">
                                <span>消費税</span>
                                <span>¥{{ formatCurrency(taxAmount) }}</span>
                            </div>
                            <div class="flex justify-between font-bold text-gray-900 border-t border-gray-200 pt-3 mt-3 text-lg">
                                <span>合計金額</span>
                                <span>¥{{ formatCurrency(totalAmount) }}</span>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Notes -->
                <div class="p-8 border-t border-gray-100 bg-white">
                    <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">備考・メモ</label>
                    <textarea v-model="note" rows="3" placeholder="振込先情報等は設定から自動挿入されます。特記事項があれば入力してください。" class="w-full border border-gray-200 rounded-lg p-3 text-sm focus:ring-blue-500 focus:border-blue-500 bg-gray-50/50 resize-none"></textarea>
                </div>
            </div>
        </div>

        <!-- Right Side: Preview & Totals -->
        <div class="col-span-12 xl:col-span-4 space-y-6">
            
            <!-- Realtime Preview -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden sticky top-24" v-if="selectedTemplateId && !isExtracting">
                <div class="bg-slate-800 px-6 py-4 flex items-center justify-between border-b" :class="invoiceType === 'recurring' ? 'border-b-purple-500' : 'border-b-blue-500'">
                     <h3 class="text-white font-bold text-sm tracking-wider flex items-center gap-2"><FileImage class="w-4 h-4 text-slate-300" /> プレビュー</h3>
                     
                     <div class="flex bg-slate-700 rounded p-0.5">
                        <button @click="showCodeEditor = false" class="px-3 py-1 text-xs font-bold rounded transition-colors" :class="!showCodeEditor ? 'bg-slate-500 text-white' : 'text-slate-300 hover:text-white'">Visual</button>
                        <button @click="showCodeEditor = true" class="px-3 py-1 text-xs font-bold rounded transition-colors" :class="showCodeEditor ? 'bg-slate-500 text-white' : 'text-slate-300 hover:text-white'">Code</button>
                     </div>
                </div>
                
                <div class="relative min-h-[400px]">
                    <!-- Placeholder when no template is uploaded -->
                    <div v-if="!isTemplateUploaded && !isExtracting" class="absolute inset-0 flex items-center justify-center bg-slate-50 border-t border-slate-200 p-8 text-center text-sm text-gray-400">
                        左側のパネルで既存の請求書ファイル（PDF/Excel等）をアップロードすると、AIが解析した結果のプレビューがここに表示されます。
                    </div>
                    
                    <!-- Loading state -->
                    <div v-if="isExtracting" class="absolute inset-0 flex flex-col items-center justify-center bg-slate-800 border-t border-slate-700 p-8 text-center text-sm text-blue-400">
                        <Loader2 class="w-10 h-10 animate-spin mb-4 text-blue-500" />
                        <p class="font-bold tracking-widest uppercase mb-1">Generating Template</p>
                        <p class="text-xs text-blue-400/60 font-mono">Compiling HTML structures from visual layout...</p>
                    </div>

                    <!-- Code Editor Mode -->
                    <div v-else-if="showCodeEditor" class="absolute inset-0 bg-[#1e1e1e] p-4 overflow-y-auto">
                        <textarea v-model="templateHtml" class="w-full h-full min-h-[400px] bg-transparent text-gray-300 font-mono text-xs focus:outline-none resize-none" spellcheck="false"></textarea>
                    </div>

                    <!-- Visual HTML Render Mode -->
                    <div v-else class="absolute inset-0 bg-white p-4 overflow-y-auto shadow-inner border border-gray-200 m-4 rounded scale-[0.6] origin-top-left w-[166%] h-[166%]" v-html="templateHtml.replace(/\{\{\s*client_name\s*\}\}/g, templateVariables[0].value.split('\n')[0]).replace(/\{\{\s*issue_date\s*\}\}/g, issueDate).replace(/\{\{\s*due_date\s*\}\}/g, dueDate).replace(/\{\{\s*total_amount\s*\}\}/g, formatCurrency(totalAmount))">
                    </div>
                </div>

                <div class="p-6 space-y-4 bg-gray-50 border-t border-gray-200">
                    <p class="text-[11px] text-gray-500 text-center leading-relaxed">
                        ※ Code（コード）ビューで直接HTMLを修正し、Visual（プレビュー）ビューで即座に確認できます。<br>
                    </p>
                </div>
            </div>
        </div>
      </div>
    </div>
  </div>
  
  <ClientFormModal 
      :show="isModalOpen" 
      @close="isModalOpen = false"
      @save="handleClientSave"
  />

  <TemplateEditorModal
      :show="isTemplateEditorOpen"
      :initial-name="latestExtractedName"
      :initial-html="latestExtractedHtml"
      @close="isTemplateEditorOpen = false"
      @save="handleTemplateSave"
  />

  <!-- Template Deletion Confirmation Modal -->
  <div v-if="templateToDelete" class="fixed inset-0 z-[110] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="templateToDelete = null"></div>
      <div class="bg-white rounded-xl shadow-xl border border-gray-200 overflow-hidden w-full max-w-sm relative z-10 p-6 text-center animate-in fade-in zoom-in-95 duration-200">
          <div class="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertCircle class="w-6 h-6 text-red-600" />
          </div>
          <h3 class="text-lg font-bold text-gray-900 mb-2">テンプレートの削除</h3>
          <p class="text-sm text-gray-500 mb-6 font-medium">
              「{{ templateToDelete.name }}」を本当に削除しますか？<br>この操作は取り消せません。
          </p>
          <div class="flex items-center gap-3">
              <button @click="templateToDelete = null" class="flex-1 px-4 py-2 border border-gray-300 text-gray-700 bg-white hover:bg-gray-50 rounded-lg text-sm font-bold transition-colors">
                  キャンセル
              </button>
              <button @click="executeDeleteTemplate" class="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-bold transition-colors shadow-sm shadow-red-600/20 flex justify-center items-center gap-2">
                  <Trash2 class="w-4 h-4" /> 削除する
              </button>
          </div>
      </div>
  </div>

</template>
```
