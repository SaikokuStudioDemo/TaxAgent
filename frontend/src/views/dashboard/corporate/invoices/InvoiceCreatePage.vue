<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { ChevronLeft, Plus, CheckCircle, Save, Send, FileText, Loader2, Building2, AlertCircle as AlertCircleIcon, Trash2, FileImage, X, AlertCircle, GripHorizontal, Pencil, Mail, ShieldCheck, FolderKanban } from 'lucide-vue-next';
import { useRouter, useRoute } from 'vue-router';
import ClientFormModal from '@/components/invoices/ClientFormModal.vue';
import TemplateEditorModal from '@/components/invoices/TemplateEditorModal.vue';
import ApprovalStepper from '@/components/approvals/ApprovalStepper.vue';
import { useCompanyProfiles } from '@/composables/useCompanyProfiles';
import { useBankAccounts } from '@/composables/useBankAccounts';
import { useProjects } from '@/composables/useProjects';
import { api } from '@/lib/api';
import { formatNumber as formatCurrency } from '@/lib/utils/formatters';

const router = useRouter();
const route = useRoute();
const editingInvoiceId = ref<string | null>((route.query.id as string) || null);
const previewIframe = ref<HTMLIFrameElement | null>(null);

// --- UI STATE ---
const isModalOpen = ref(false);
const isTemplateEditorOpen = ref(false);
const showSuccessPopup = ref(false);
const showDraftSuccessPopup = ref(false);
const isExtracting = ref(false);
const isSaving = ref(false);

// --- DATA STATE ---
interface InvoiceTemplate {
    id: string;
    name: string;
    description: string;
    thumbnail: string;
    isActive: boolean;
    html: string;
}

interface LineItem {
    id: number;
    description: string;
    quantity: number;
    unitPrice: number;
    taxRate: number;
}

// ⑥ モックデータを削除。テンプレートは API から動的取得する。
const templates = ref<InvoiceTemplate[]>([]);

const selectedTemplateId = ref('');
const templateHtml = ref('');
const templateName = ref('default_invoice_template.html');
const latestExtractedHtml = ref('');
const latestExtractedName = ref('');
const templateVariables = ref([
    { key: 'client_name', label: '取引先名', value: '株式会社クライアント 御中' },
    { key: 'issue_date', label: '発行日', value: '2024-10-24' },
    { key: 'due_date', label: 'お支払期限', value: '2024-11-30' },
    { key: 'total_amount', label: 'ご請求金額', value: '110,000' }
]);

const invoiceNumber = ref(`INV-${new Date().getFullYear()}${String(new Date().getMonth() + 1).padStart(2, '0')}-001`);
const issueDate = ref('2024-10-24');
const dueDate = ref('2024-11-30');
const items = ref<LineItem[]>([
    { id: 1, description: '', quantity: 1, unitPrice: 0, taxRate: 0.10 }
]);
const note = ref('');
const activeClientId = ref('');
const availableClients = ref<{id: string, name: string, contactPerson: string, email?: string, details?: string}[]>([
    { id: 'C-1001', name: '株式会社Aoyama Systems', contactPerson: '田中 健太', email: 'alpha@aoyama.co.jp', details: '株式会社Aoyama Systems 御中\n担当：田中 健太 様\n東京都港区北青山...\n03-0000-0000' },
    { id: 'C-1002', name: 'BlueOcean Inc.', contactPerson: 'David Smith', email: 'billing@blueocean.co.jp', details: 'BlueOcean Inc.\nAttn: David Smith\n1-2-3 Minato-ku, Tokyo\n03-1234-5678' },
    { id: 'C-1003', name: '山口会計事務所', contactPerson: '山口 太郎', email: 'billing@yamaguchi-cpa.jp', details: '山口会計事務所 御中\n代表：山口 太郎 様\n東京都千代田区麹町...\n03-9999-9999' }
]);
const templateToDelete = ref<InvoiceTemplate | null>(null);

// --- COMPOSABLES ---
const { profiles: senderProfiles, fetchProfiles, formatProfileForTextarea } = useCompanyProfiles();
const { accounts: bankAccounts, fetchBankAccounts } = useBankAccounts();
const { projects, fetchProjects } = useProjects();
const activeSenderProfile = ref('');
const activeBankAccountId = ref('');
const activeProjectId = ref('');
const approvalMode = ref<'department' | 'project'>('department');

watch(approvalMode, (mode) => {
    if (mode === 'department') activeProjectId.value = '';
});

// 請求元プロファイルが変わったら紐づく口座を再取得してデフォルトを選択
watch(activeSenderProfile, async (profileId) => {
    if (!profileId) return;
    await fetchBankAccounts({ profileId });
    const defaultAccount = bankAccounts.value.find(a => a.is_default) || bankAccounts.value[0];
    activeBankAccountId.value = defaultAccount?.id ?? '';
});

// --- COMPUTED ---
const subtotal = computed(() => items.value.reduce((sum, item) => sum + (item.quantity * item.unitPrice), 0));
const taxAmount = computed(() => items.value.reduce((sum, item) => sum + (item.quantity * item.unitPrice * item.taxRate), 0));
const totalAmount = computed(() => subtotal.value + taxAmount.value);

const recipientEmail = ref('');

const canSubmit = computed(() =>
  totalAmount.value > 0 &&
  activeClientId.value !== '' &&
  recipientEmail.value.includes('@')
);

const senderInfo = computed(() => {
    const profile = senderProfiles.value.find((p: any) => p.id === activeSenderProfile.value);
    return profile ? formatProfileForTextarea(profile) : '';
});

const bankAccountOptions = computed(() =>
    bankAccounts.value.map(a => ({
        id: a.id,
        label: `${a.bank_name} ${a.branch_name} ${a.account_type === 'ordinary' ? '普通' : '当座'} ${a.account_number} (${a.account_holder})`,
        is_default: a.is_default,
    }))
);

const clientDisplayName = computed(() => {
    const text = templateVariables.value[0]?.value || '';
    return text.split('\n')[0] || '未入力';
});

// Variable Extraction logic for dynamic form
const detectedVariables = computed(() => {
    if (!templateHtml.value) return [];
    const matches = templateHtml.value.matchAll(/\{\{\s*(\w+)\s*\}\}/g);
    const keys = new Set<string>();
    for (const match of matches) {
        keys.add(match[1]);
    }
    return Array.from(keys);
});

const renderedPreviewHtml = computed(() => {
    if (!templateHtml.value) return '';
    
    let html = templateHtml.value;
    
    // 1. Basic Fields
    html = html.replace(/\{\{\s*invoice_number\s*\}\}/g, invoiceNumber.value || 'INV-000000');
    html = html.replace(/\{\{\s*issue_date\s*\}\}/g, issueDate.value || 'YYYY/MM/DD');
    html = html.replace(/\{\{\s*due_date\s*\}\}/g, dueDate.value || 'YYYY/MM/DD');
    
    // 2. Client Info
    const clientText = templateVariables.value[0]?.value || '';
    const clientLines = clientText.split('\n');
    let clientName = clientLines[0] || '取引先名';
    // Remove ' 御中' if it already exists to prevent duplication
    clientName = clientName.replace(/\s*御中\s*$/, '');
    html = html.replace(/\{\{\s*client_name\s*\}\}/g, clientName + ' 御中');
    html = html.replace(/\{\{\s*client_details\s*\}\}/g, clientLines.slice(1).join('<br>') || '');
    
    // 3. Sender Info
    const senderInfoText = senderInfo.value;
    const senderLines = senderInfoText.split('\n');
    html = html.replace(/\{\{\s*sender_name\s*\}\}/g, senderLines[0] || '');
    html = html.replace(/\{\{\s*sender_details\s*\}\}/g, senderLines.slice(1).join('<br>') || '');
    
    // 4. Amounts
    html = html.replace(/\{\{\s*subtotal\s*\}\}/g, formatCurrency(subtotal.value));
    html = html.replace(/\{\{\s*tax_amount\s*\}\}/g, formatCurrency(taxAmount.value));
    html = html.replace(/\{\{\s*total_amount\s*\}\}/g, formatCurrency(totalAmount.value));
    
    // 5. Item List
    let itemsHtml = '';
    items.value.forEach(item => {
        itemsHtml += `
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 16px; font-weight: 500;">${item.description || '名称未設定'}</td>
                <td style="padding: 16px; text-align: right;">${item.quantity}</td>
                <td style="padding: 16px; text-align: right;">¥${formatCurrency(item.unitPrice)}</td>
                <td style="padding: 16px; text-align: right; font-weight: 600;">¥${formatCurrency(item.quantity * item.unitPrice)}</td>
            </tr>
        `;
    });
    html = html.replace(/\{\{\s*item_list\s*\}\}/g, itemsHtml);
    
    // 6. Notes
    html = html.replace(/\{\{\s*note\s*\}\}/g, note.value.replace(/\n/g, '<br>') || '');
    
    return html;
});

// --- METHODS ---
const selectTemplate = (id: string) => {
    selectedTemplateId.value = id;
    const template = templates.value.find(t => t.id === id);
    if (template) {
        templateHtml.value = template.html;
    } else {
        templateHtml.value = '';
    }
};

const confirmDeleteTemplate = (templ: InvoiceTemplate) => {
    templateToDelete.value = templ;
};

const executeDeleteTemplate = async () => {
    if (!templateToDelete.value) return;
    try {
        await api.delete(`/invoices/templates/${templateToDelete.value.id}`);
        templates.value = templates.value.filter(t => t.id !== templateToDelete.value?.id);
        if (selectedTemplateId.value === templateToDelete.value.id) {
            if (templates.value.length > 0) {
                selectTemplate(templates.value[0].id);
            } else {
                selectedTemplateId.value = '';
                templateHtml.value = '';
            }
        }
    } catch (error) {
        console.error('Failed to delete template:', error);
        alert('テンプレートの削除に失敗しました。');
    } finally {
        templateToDelete.value = null;
    }
};

const saveTemplateName = async (templ: InvoiceTemplate) => {
    if (!templ.name.trim()) templ.name = '名称未設定';
    try {
        await api.patch(`/invoices/templates/${templ.id}`, { name: templ.name });
    } catch (error) {
        console.error('Failed to update template name:', error);
        alert('テンプレート名の保存に失敗しました。');
    }
};

const addItem = () => {
    items.value.push({ id: Date.now(), description: '', quantity: 1, unitPrice: 0, taxRate: 0.10 });
};

const removeItem = (id: number) => {
    if (items.value.length > 1) {
        items.value = items.value.filter(item => item.id !== id);
    }
};

const sortTemplates = () => {
    const savedOrder = JSON.parse(localStorage.getItem('invoice_template_order') || 'null');
    if (savedOrder && Array.isArray(savedOrder)) {
        templates.value.sort((a, b) => {
            let indexA = savedOrder.indexOf(a.id);
            let indexB = savedOrder.indexOf(b.id);
            if (indexA === -1) indexA = -1; // newly added items go to the front
            if (indexB === -1) indexB = -1;
            return indexA - indexB;
        });
    }
};

const draggedIndex = ref<number | null>(null);
const scrollContainer = ref<any>(null);
let scrollIntervalId: ReturnType<typeof setInterval> | null = null;

const clearScroll = () => {
    if (scrollIntervalId) {
        clearInterval(scrollIntervalId);
        scrollIntervalId = null;
    }
};

const onContainerDragOver = (e: DragEvent) => {
    e.preventDefault();
    const container = scrollContainer.value?.$el || scrollContainer.value;
    if (!container) return;
    
    const rect = container.getBoundingClientRect();
    const edgeSize = 100;
    
    if (e.clientX < rect.left + edgeSize) {
        if (!scrollIntervalId) {
            scrollIntervalId = setInterval(() => container.scrollBy({ left: -20 }), 16);
        }
    } else if (e.clientX > rect.right - edgeSize) {
        if (!scrollIntervalId) {
            scrollIntervalId = setInterval(() => container.scrollBy({ left: 20 }), 16);
        }
    } else {
        clearScroll();
    }
};

const onDragStart = (e: DragEvent, index: number) => {
    draggedIndex.value = index;
    if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', index.toString());
    }
};

const onDragEnter = (index: number) => {
    if (draggedIndex.value !== null && draggedIndex.value !== index) {
        const item = templates.value.splice(draggedIndex.value, 1)[0];
        templates.value.splice(index, 0, item);
        draggedIndex.value = index;
    }
};

const onDragOver = (e: DragEvent) => {
    e.preventDefault(); 
};

const onDrop = (e: DragEvent) => {
    e.preventDefault();
    localStorage.setItem('invoice_template_order', JSON.stringify(templates.value.map(t => t.id)));
    draggedIndex.value = null;
    clearScroll();
};

const onDragEnd = () => {
    draggedIndex.value = null;
    localStorage.setItem('invoice_template_order', JSON.stringify(templates.value.map(t => t.id)));
    clearScroll();
};

const fetchTemplates = async () => {
    try {
        // ⑥ モックデータを排除し API から invoice テンプレートのみ取得
        const dbTemplates = await api.get<any[]>('/invoices/templates?template_type=invoice');
        if (dbTemplates && Array.isArray(dbTemplates)) {
            templates.value = dbTemplates.map((t: any) => ({
                id: t.id,
                name: t.name,
                description: t.description || '',
                thumbnail: t.thumbnail || 'bg-emerald-50 border-emerald-200',
                isActive: t.is_active !== undefined ? t.is_active : true,
                html: t.html || '',
            }));

            sortTemplates();

            // 編集モードでなければ先頭をデフォルト選択
            if (!editingInvoiceId.value && templates.value.length > 0) {
                selectTemplate(templates.value[0].id);
            }
        }
    } catch (error) {
        console.error('Failed to fetch templates:', error);
    }
};

const loadInvoiceData = async (id: string) => {
    try {
        const invoice = await api.get<any>(`/invoices/${id}`);
        if (invoice) {
            invoiceNumber.value = invoice.invoice_number;
            issueDate.value = invoice.issue_date;
            dueDate.value = invoice.due_date;
            activeClientId.value = invoice.client_id || '';
            note.value = invoice.note || '';
            
            if (invoice.line_items && Array.isArray(invoice.line_items)) {
                items.value = invoice.line_items.map((li: any, idx: number) => ({
                    id: idx + 1,
                    description: li.description,
                    quantity: 1, 
                    unitPrice: li.amount,
                    taxRate: li.tax_rate
                }));
            }
            
            if (invoice.sender_profile_id) {
                activeSenderProfile.value = invoice.sender_profile_id;
            }

            handleClientSelection();
        }
    } catch (error) {
        console.error('Failed to load invoice for editing:', error);
    }
};

onMounted(async () => {
    fetchTemplates();
    fetchProjects();
    await fetchProfiles();
    // Set default sender profile
    const defaultProfile = senderProfiles.value.find((p: any) => p.is_default) || senderProfiles.value[0];
    if (defaultProfile) activeSenderProfile.value = defaultProfile.id;

    // 請求元プロファイルに紐づく口座を取得
    if (activeSenderProfile.value) {
        await fetchBankAccounts({ profileId: activeSenderProfile.value });
        const defaultAccount = bankAccounts.value.find(a => a.is_default) || bankAccounts.value[0];
        if (defaultAccount) activeBankAccountId.value = defaultAccount.id;
    }

    if (editingInvoiceId.value) {
        loadInvoiceData(editingInvoiceId.value);
    }
});

const editingModeTemplateId = ref<string | null>(null);

const openTemplateEditor = (templ: InvoiceTemplate) => {
    editingModeTemplateId.value = templ.id;
    latestExtractedName.value = templ.name;
    latestExtractedHtml.value = templ.html;
    isTemplateEditorOpen.value = true;
};

const iframeDoc = computed(() => `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>html,body{margin:0;padding:0;background:white;}img,table{max-width:100%;height:auto;}</style>
</head>
<body>
<div id="r">${renderedPreviewHtml.value}</div>
<script>
window.addEventListener('load',function(){
  var h=document.getElementById('r').scrollHeight;
  window.parent.postMessage({type:'resize-iframe',height:h},'*');
});
<\/script>
</body>
</html>`);

const handleIframeMessage = (event: MessageEvent) => {
    if (event.data.type === 'resize-iframe' && previewIframe.value) {
        previewIframe.value.style.height = (event.data.height + 40) + 'px';
    }
};

onMounted(() => { window.addEventListener('message', handleIframeMessage); });
onUnmounted(() => { window.removeEventListener('message', handleIframeMessage); });


const applyTemplate = async (e: Event) => {
    const target = e.target as HTMLInputElement;
    if (target.files && target.files.length > 0) {
        const file = target.files[0];
        templateName.value = file.name;
        isExtracting.value = true;
        editingModeTemplateId.value = null; // Reset edit mode
        try {
            const result = await api.post<{ template_name: string; html: string; variables: string[] }>(
                '/invoices/templates/generate',
                { filename: file.name }
            );
            latestExtractedName.value = result.template_name || file.name.replace(/\.[^/.]+$/, '');
            latestExtractedHtml.value = result.html;
            isExtracting.value = false;
            isTemplateEditorOpen.value = true;
        } catch (error: any) {
            console.error('AI Template Generation Error:', error);
            isExtracting.value = false;
            alert('AIによるテンプレート生成に失敗しました。\n' + (error?.message || ''));
        } finally {
            target.value = '';
        }
    }
};

const handleTemplateSave = async (payload: { name: string, html: string }) => {
    try {
        if (editingModeTemplateId.value) {
            // Edit existing
            const updatedTemplate = await api.patch<any>(`/invoices/templates/${editingModeTemplateId.value}`, {
                name: payload.name,
                html: payload.html
            });
            await fetchTemplates();
            if (updatedTemplate && updatedTemplate.id) {
                selectedTemplateId.value = updatedTemplate.id;
                templateHtml.value = updatedTemplate.html;
            }
        } else {
            // Create new
            const savedTemplate = await api.post<any>('/invoices/templates', {
                name: payload.name,
                description: 'AI生成テンプレート',
                html: payload.html,
                thumbnail: 'bg-emerald-50 border-emerald-200',
                is_active: true
            });
            await fetchTemplates();
            if (savedTemplate && savedTemplate.id) {
                selectedTemplateId.value = savedTemplate.id;
                templateHtml.value = payload.html;
            }
        }
    } catch (error) {
        console.error('Failed to save template:', error);
        alert('テンプレートの保存に失敗しました。');
    } finally {
        isTemplateEditorOpen.value = false;
        editingModeTemplateId.value = null;
    }
};

const goBack = () => {
    router.push('/dashboard/corporate/invoices/list');
};

const buildPayload = () => {
    const clientText = templateVariables.value[0]?.value || '';
    const clientName = clientText.split('\n')[0].replace(' 御中', '') || '未設定';
    return {
        document_type: 'issued' as const,
        invoice_number: invoiceNumber.value,
        client_id: activeClientId.value || undefined,
        client_name: clientName,
        recipient_email: recipientEmail.value,
        issue_date: issueDate.value,
        due_date: dueDate.value,
        subtotal: subtotal.value,
        tax_amount: taxAmount.value,
        total_amount: totalAmount.value,
        line_items: items.value.map(item => ({
            description: item.description || '名称未設定',
            category: '',
            amount: item.quantity * item.unitPrice,
            tax_rate: Math.round(item.taxRate * 100)
        })),
        template_id: selectedTemplateId.value || undefined,
        bank_account_id: activeBankAccountId.value || undefined,
        project_id: activeProjectId.value || undefined,
    };
};

const saveDraft = async () => {
    isSaving.value = true;
    try {
        const payload = buildPayload();
        if (editingInvoiceId.value) {
            await api.patch(`/invoices/${editingInvoiceId.value}`, payload);
        } else {
            await api.post('/invoices', payload);
        }
        showDraftSuccessPopup.value = true;
    } catch (error) {
        console.error('Failed to save draft:', error);
        alert('下書き保存に失敗しました。');
    } finally {
        isSaving.value = false;
    }
};

const handleDraftSuccessConfirm = () => {
    showDraftSuccessPopup.value = false;
    router.push('/dashboard/corporate/invoices/list');
};

const isApprovalRequired = ref(false);

const handleApprovalRequirement = (required: boolean) => {
    isApprovalRequired.value = required;
};

const submitInvoice = async () => {
    isSaving.value = true;
    try {
        const payload = {
            ...buildPayload(),
            approval_status: isApprovalRequired.value ? 'pending_approval' : 'draft',
        };
        if (editingInvoiceId.value) {
            await api.patch(`/invoices/${editingInvoiceId.value}`, payload);
        } else {
            await api.post('/invoices', payload);
        }
        
        showSuccessPopup.value = true;
    } catch (error) {
        console.error('Failed to submit invoice:', error);
        alert('操作に失敗しました。');
    } finally {
        isSaving.value = false;
    }
};

function handleSuccessConfirm() {
    showSuccessPopup.value = false;
    router.push('/dashboard/corporate/invoices/list');
}

const handleClientSave = (newClient: any) => {
    availableClients.value.unshift({
        id: newClient.id,
        name: newClient.name,
        contactPerson: newClient.contact_person || '',
        details: `${newClient.name} 御中\n担当：${newClient.contact_person || ''} 様\n${newClient.address || ''}\n${newClient.phone || ''}`
    });
    activeClientId.value = newClient.id;
    handleClientSelection();
    isModalOpen.value = false;
};

function handleClientSelection() {
    if (!activeClientId.value) {
        if (templateVariables.value.length > 0) templateVariables.value[0].value = '';
        recipientEmail.value = '';
        return;
    }
    const selected = availableClients.value.find(c => c.id === activeClientId.value);
    if (selected) {
        if (selected.details && templateVariables.value.length > 0) {
            templateVariables.value[0].value = selected.details;
        }
        if (selected.email) {
            recipientEmail.value = selected.email;
        }
    }
}
</script>

<template>
  <Transition name="fade-page" appear>
    <div class="relative h-full overflow-hidden flex flex-col bg-slate-50">
      
      <!-- Header -->
      <header class="bg-white border-b border-gray-200 px-8 py-5 flex items-center justify-between shrink-0 z-10 sticky top-0 shadow-sm">
        <div class="flex items-center gap-4">
          <button @click="goBack" class="p-2 hover:bg-gray-100 rounded-lg transition-colors text-gray-500">
            <ChevronLeft class="w-5 h-5" />
          </button>
          <div>
            <h1 class="text-xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
               <span v-if="editingInvoiceId" class="text-blue-600">下書きを編集</span>
               <span v-else>請求書発行</span>
            </h1>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="hidden md:flex bg-blue-50 text-blue-700 px-3 py-1.5 rounded-lg text-sm font-bold items-center gap-2 border border-blue-100">
              <span class="relative flex h-2 w-2">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
              </span>
              編集中
          </div>
        </div>
      </header>


      <!-- Main Content (Scrollable) -->
      <div class="flex-1 overflow-y-auto bg-gray-50/50 p-8">
          <div class="max-w-[1400px] mx-auto space-y-8">
          
              <!-- TEMPLATE GALLERY -->
              <div>
                  <div class="flex items-center justify-between mb-4">
                      <h2 class="text-xl font-bold text-gray-900">インボイス・テンプレートを選択</h2>
                      <label class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm flex items-center shadow-sm cursor-pointer">
                          <Plus class="w-4 h-4 mr-2" />テンプレート登録
                          <input type="file" accept=".pdf, .xlsx, .xls, .doc, .docx" @change="applyTemplate" class="hidden" />
                      </label>
                  </div>
                  
                  <TransitionGroup name="drag-list" tag="div" ref="scrollContainer" @dragover="onContainerDragOver" @dragleave="clearScroll" @drop="clearScroll" class="flex gap-4 overflow-x-auto pb-6 pt-2 relative -ml-1 pl-1 scroll-smooth">
                      <div v-if="isExtracting" key="extracting-indicator" class="w-[220px] shrink-0 border-2 border-dashed border-blue-400 rounded-xl bg-blue-50/50 flex flex-col items-center justify-center p-6 min-h-[280px]">
                           <Loader2 class="w-8 h-8 text-blue-500 animate-spin mb-3" />
                           <p class="font-bold text-sm text-blue-800 text-center leading-tight break-all">AIが「{{ templateName }}」を<br>解析中です...</p>
                           <p class="text-[10px] text-blue-600 mt-2 text-center">レイアウトを抽出して<br>フォームブロックを生成</p>
                      </div>

                      <!-- ⑥ テンプレートが0件の場合のメッセージ -->
                      <div v-if="templates.length === 0"
                           class="w-[220px] shrink-0 rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 flex flex-col items-center justify-center p-6 text-center">
                        <p class="text-sm text-slate-400">テンプレートがありません。</p>
                        <p class="text-xs text-slate-400 mt-1">テンプレート管理から追加してください。</p>
                      </div>

                      <div v-for="(templ, index) in templates" :key="templ.id"
                           draggable="true"
                           @dragstart="onDragStart($event, index)"
                           @dragenter.prevent="onDragEnter(index)"
                           @dragover.prevent="onDragOver"
                           @drop="onDrop($event)"
                           @dragend="onDragEnd"
                           @click="selectTemplate(templ.id)"
                           class="w-[200px] sm:w-[220px] shrink-0 rounded-xl cursor-grab active:cursor-grabbing transition-all relative flex flex-col h-full border-2"
                           :class="[
                                selectedTemplateId === templ.id && draggedIndex !== index ? 'border-blue-600 shadow-xl z-10 bg-white' : 'border-transparent hover:border-gray-200 hover:shadow-sm bg-white',
                                draggedIndex === index ? 'opacity-30 scale-95 border-dashed border-gray-400 z-30' : ''
                           ]">
                          <div class="h-[180px] rounded-t-lg bg-gray-50 p-4 w-full flex flex-col gap-2 border-b border-gray-100 relative overflow-hidden group">
                              <div class="absolute top-2 left-2 p-1 text-gray-300 group-hover:text-gray-500 transition-colors z-10" title="ドラッグして並び替え">
                                  <GripHorizontal class="w-4 h-4" />
                              </div>
                              <div class="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all z-10">
                                  <button v-if="!templ.id.startsWith('T-0')" @click.stop="openTemplateEditor(templ)" class="p-1.5 bg-white shadow-sm border border-gray-200 text-gray-400 hover:text-blue-500 hover:border-blue-200 hover:bg-blue-50 rounded-full transition-all" title="テンプレートを編集">
                                      <Pencil class="w-4 h-4" />
                                  </button>
                                  <button v-if="!templ.id.startsWith('T-0')" @click.stop="confirmDeleteTemplate(templ)" class="p-1.5 bg-white shadow-sm border border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200 hover:bg-red-50 rounded-full transition-all" title="テンプレートを削除">
                                      <X class="w-4 h-4" />
                                  </button>
                              </div>
                                                            
                              <div class="w-16 h-3 bg-gray-300 rounded mb-4" :class="templ.id.startsWith('T-0') ? 'bg-blue-400' : 'bg-slate-600'"></div>
                              <div class="w-full h-1.5 bg-gray-200 rounded"></div>
                              <div class="w-3/4 h-1.5 bg-gray-200 rounded"></div>
                              <div class="flex justify-end mt-4"><div class="w-20 h-10 bg-gray-200 rounded flex flex-col gap-1 items-end pt-1 pr-1"><div class="w-8 h-1 bg-gray-300 rounded"></div><div class="w-12 h-1 bg-gray-300 rounded"></div><div class="w-12 h-1 bg-blue-300 rounded"></div></div></div>
                              <div class="w-full h-8 bg-gray-100 border border-gray-200 rounded mt-4"></div>
                              <div v-if="selectedTemplateId === templ.id" class="absolute inset-0 border-4 border-blue-600/10 rounded-t-xl pointer-events-none"></div>
                          </div>
                          <div class="p-3 bg-white rounded-b-xl flex-1 flex flex-col gap-1">
                              <div class="flex items-start justify-between gap-2">
                                  <input 
                                      v-if="selectedTemplateId === templ.id && !templ.id.startsWith('T-0')" 
                                      v-model="templ.name" 
                                      @blur="saveTemplateName(templ)"
                                      @keyup.enter="($event.target as any).blur()"
                                      class="font-bold text-sm text-blue-700 leading-tight w-full bg-blue-50/50 border border-blue-200 rounded px-1 -ml-1 focus:ring-1 focus:ring-blue-500 focus:outline-none" 
                                      @click.stop 
                                      title="名前を編集"
                                  />
                                  <span v-else class="font-bold text-sm text-gray-900 leading-tight break-all">{{ templ.name }}</span>
                                  <CheckCircle v-if="selectedTemplateId === templ.id" class="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                              </div>
                              <p class="text-[10px] text-gray-500 leading-tight opacity-80 overflow-hidden line-clamp-2">{{ templ.description }}</p>
                          </div>
                      </div>
                  </TransitionGroup>
              </div>

               <!-- DYNAMIC FORM -->
               <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden" v-if="!isExtracting">
                   <div class="px-6 py-4 border-b border-gray-100 bg-slate-50 flex items-center gap-2">
                       <FileText class="w-5 h-5 text-blue-600" />
                       <h2 class="font-bold text-gray-900 text-lg">請求書情報入力</h2>
                   </div>
                   <div class="p-8 space-y-8">
                       <!-- Header Section (Number, Dates) -->
                       <div v-if="detectedVariables.some(v => ['invoice_number', 'issue_date', 'due_date'].includes(v))" class="grid grid-cols-1 md:grid-cols-3 gap-6">
                           <div v-if="detectedVariables.includes('invoice_number')">
                               <label class="block text-xs font-bold text-gray-700 mb-2">請求書番号</label>
                               <input v-model="invoiceNumber" type="text" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-blue-500 focus:border-blue-500 font-mono" />
                           </div>
                           <div v-if="detectedVariables.includes('issue_date')">
                               <label class="block text-xs font-bold text-gray-700 mb-2">発行日</label>
                               <input v-model="issueDate" type="date" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-blue-500 focus:border-blue-500" />
                           </div>
                           <div v-if="detectedVariables.includes('due_date')">
                               <label class="block text-xs font-bold text-gray-700 mb-2">支払期日</label>
                               <input v-model="dueDate" type="date" class="w-full border border-gray-300 rounded-lg p-2.5 text-sm focus:ring-blue-500 focus:border-blue-500" />
                           </div>
                       </div>

                       <!-- Client & Sender Info Section -->
                       <div v-if="detectedVariables.some(v => ['client_name', 'client_details', 'sender_name', 'sender_details'].includes(v))" class="grid grid-cols-1 md:grid-cols-2 gap-6 pb-4">
                           <div v-if="detectedVariables.includes('client_name') || detectedVariables.includes('client_details')">
                               <label class="block text-xs font-bold text-gray-700 mb-2">請求先情報</label>
                               <div class="border border-gray-200 rounded-lg bg-gray-50 flex flex-col group hover:border-blue-300 transition-colors relative overflow-hidden">
                                   <div class="p-5 flex-1 relative">
                                       <div class="mb-3 relative">
                                           <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                               <Building2 class="h-4 w-4 text-gray-400" />
                                           </div>
                                           <select v-model="activeClientId" @change="handleClientSelection" class="block w-full pl-10 pr-10 py-2 text-sm border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md bg-white shadow-sm">
                                               <option value="">取引先を選択してください</option>
                                               <option v-for="client in availableClients" :key="client.id" :value="client.id">{{ client.name }}</option>
                                           </select>
                                       </div>
                                       <textarea v-model="templateVariables[0].value" class="w-full h-24 bg-transparent border-0 resize-none focus:ring-0 p-0 text-sm leading-relaxed" placeholder="株式会社クライアント 御中\n担当：佐藤 健太 様\n東京都港区六本木...\n03-0000-0000"></textarea>
                                   </div>
                                   <div class="bg-white border-t border-gray-200 px-4 py-2 flex justify-center shrink-0 transition-colors">
                                       <button @click="isModalOpen = true" class="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors flex items-center justify-center gap-1 py-1 px-2 hover:bg-blue-50 rounded w-full">
                                           <Plus class="w-3.5 h-3.5" /> 新規取引先を追加
                                       </button>
                                   </div>
                               </div>
                               <!-- 送付先メールアドレス -->
                               <div v-if="detectedVariables.includes('client_name')" class="mt-4 border-t border-gray-100 pt-4">
                                 <label class="block text-xs font-bold text-gray-700 mb-2 flex items-center gap-1.5">
                                   <Mail class="w-3.5 h-3.5 text-gray-400" />
                                   送付先メールアドレス
                                   <span class="text-red-500">*</span>
                                 </label>
                                 <div class="relative">
                                   <input
                                     type="email"
                                     v-model="recipientEmail"
                                     :placeholder="activeClientId ? 'メールアドレスを入力' : '取引先を選択するとメールアドレスが自動入力されます'"
                                     :disabled="!activeClientId"
                                     class="w-full border rounded-lg px-3 py-2 text-sm transition-all"
                                     :class="activeClientId
                                       ? 'border-gray-300 bg-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500'
                                       : 'border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed'"
                                   />
                                   <span v-if="recipientEmail && recipientEmail.includes('@')" class="absolute right-3 top-1/2 -translate-y-1/2 text-emerald-500">
                                     <CheckCircle class="w-4 h-4" />
                                   </span>
                                 </div>
                                 <p v-if="activeClientId && !recipientEmail" class="text-xs text-amber-600 mt-1 flex items-center gap-1">
                                   <AlertCircle class="w-3 h-3" />
                                   送付先メールアドレスを入力してください
                                 </p>
                               </div>
                           </div>
                           <div v-if="detectedVariables.includes('sender_name') || detectedVariables.includes('sender_details')" class="space-y-4">
                               <div>
                                   <label class="block text-xs font-bold text-gray-700 mb-2">請求元情報</label>
                                   <div class="border border-gray-200 rounded-lg bg-gray-50 flex flex-col relative group overflow-hidden">
                                       <div class="p-5 flex-1 relative">
                                           <div class="mb-3">
                                               <select v-model="activeSenderProfile" class="block w-full py-1.5 pl-3 pr-10 text-sm border-gray-300 focus:outline-none focus:ring-amber-500 focus:border-amber-500 rounded-md bg-white shadow-sm text-gray-700 font-medium">
                                                   <option v-for="profile in senderProfiles" :key="(profile as any).id" :value="(profile as any).id">自社プロファイル: {{ (profile as any).profile_name || (profile as any).company_name }}</option>
                                               </select>
                                           </div>
                                           <textarea :value="senderInfo" class="w-full h-24 bg-transparent border-0 resize-none focus:ring-0 p-0 text-gray-600 text-sm leading-relaxed outline-none" readonly></textarea>
                                       </div>
                                       <div class="bg-white border-t border-gray-200 px-4 py-2 flex justify-center shrink-0">
                                           <router-link to="/dashboard/corporate/settings/company" class="text-xs font-bold text-gray-500 hover:text-gray-700 transition-colors flex items-center justify-center gap-1 py-1 px-2 hover:bg-gray-50 rounded w-full">自社マスター設定を開く</router-link>
                                       </div>
                                   </div>
                               </div>
                               <!-- 振込先口座 -->
                               <div>
                                   <label class="block text-xs font-bold text-gray-700 mb-2">振込先口座</label>
                                   <select v-model="activeBankAccountId" class="block w-full py-2 pl-3 pr-10 text-sm border border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 rounded-lg bg-white shadow-sm text-gray-700">
                                       <option value="">口座を選択してください</option>
                                       <option v-for="opt in bankAccountOptions" :key="opt.id" :value="opt.id">
                                           {{ opt.label }}{{ opt.is_default ? ' ★' : '' }}
                                       </option>
                                   </select>
                               </div>
                           </div>
                       </div>
                   </div>
               </div>
               
               <!-- ITEMS -->
               <div class="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden" v-if="!isExtracting && detectedVariables.includes('item_list')">
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
                                   <input v-model="item.description" type="text" placeholder="品目名を入力" class="w-full bg-transparent border-0 border-b border-transparent hover:border-gray-300 focus:border-blue-400 pb-0.5 p-0 text-sm font-medium text-gray-900 focus:ring-0 placeholder-gray-400 transition-colors outline-none">
                               </div>
                               <div class="col-span-2">
                                   <input v-model="item.quantity" type="number" class="w-full bg-transparent border-0 p-0 text-sm text-right focus:ring-0">
                               </div>
                               <div class="col-span-2">
                                   <input v-model="item.unitPrice" type="number" class="w-full bg-transparent border-0 p-0 text-sm text-right font-medium focus:ring-0">
                               </div>
                               <div class="col-span-1">
                                   <select v-model="item.taxRate" class="w-full bg-transparent border-0 p-0 text-sm text-right focus:ring-0 appearance-none bg-no-repeat bg-right pr-4">
                                       <option :value="0.10">10%</option>
                                       <option :value="0.08">8%</option>
                                       <option :value="0">0%</option>
                                   </select>
                               </div>
                               <div class="col-span-2 flex items-center justify-end gap-3 font-bold text-gray-900">
                                   ¥{{ formatCurrency(item.quantity * item.unitPrice) }}
                                   <button @click="removeItem(item.id)" class="text-gray-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100 p-1"><Trash2 class="w-4 h-4" /></button>
                               </div>
                           </div>
                       </div>
                       <button @click="addItem" class="mt-4 text-blue-600 hover:text-blue-700 font-bold text-sm flex items-center transition-colors px-6"><Plus class="w-4 h-4 mr-1" /> 行を追加</button>
                       <div class="px-6 py-4 bg-slate-50 border-t border-gray-200 mt-4 flex justify-end">
                           <div class="w-72 space-y-2 text-sm">
                               <div class="flex justify-between text-gray-600"><span>小計</span><span>¥{{ formatCurrency(subtotal) }}</span></div>
                               <div class="flex justify-between text-gray-600"><span>消費税</span><span>¥{{ formatCurrency(taxAmount) }}</span></div>
                               <div class="flex justify-between font-bold text-gray-900 border-t border-gray-200 pt-3 mt-3 text-lg"><span>合計金額</span><span>¥{{ formatCurrency(totalAmount) }}</span></div>
                           </div>
                       </div>
                   </div>
                   <!-- Note (only if used in template) -->
                   <div v-if="detectedVariables.includes('note')" class="p-8 border-t border-gray-100 bg-white">
                       <label class="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">備考・メモ</label>
                       <textarea v-model="note" rows="3" class="w-full border border-gray-200 rounded-lg p-3 text-sm focus:ring-blue-500 focus:border-blue-500 bg-gray-50/50 resize-none"></textarea>
                   </div>
               </div>
              
              <!-- APPROVAL MODE TOGGLE -->
              <div class="flex items-center gap-3 px-1">
                <div class="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
                  <button
                    @click="approvalMode = 'department'"
                    class="px-3 py-1 text-xs font-bold rounded-md transition-all"
                    :class="approvalMode === 'department' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  >部署ルール</button>
                  <button
                    @click="approvalMode = 'project'"
                    class="px-3 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1"
                    :class="approvalMode === 'project' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  >
                    <FolderKanban class="w-3 h-3" />
                    プロジェクトルール
                  </button>
                </div>
                <select
                  v-if="approvalMode === 'project'"
                  v-model="activeProjectId"
                  class="flex-1 py-1.5 pl-3 pr-8 text-xs border border-indigo-200 focus:outline-none focus:ring-1 focus:ring-indigo-400 rounded-lg bg-white text-gray-700"
                >
                  <option value="">プロジェクトを選択...</option>
                  <option v-for="proj in projects" :key="proj.id" :value="proj.id">{{ proj.name }}</option>
                </select>
              </div>

              <!-- APPROVAL PREVIEW -->
              <ApprovalStepper
                  document-type="issued_invoice"
                  mode="preview"
                  :amount="totalAmount"
                  @update:requires-approval="handleApprovalRequirement"
                  :payload="{ client_id: activeClientId, ...(approvalMode === 'project' && activeProjectId ? { project_id: activeProjectId } : {}) }"
              />
              
              <!-- PREVIEW -->
              <div class="space-y-6 pt-4">
                  <div class="flex items-center justify-between">
                      <div class="flex items-center gap-2">
                          <FileImage class="w-6 h-6 text-blue-600" />
                          <h3 class="text-xl font-bold text-gray-900">プレビュー反映</h3>
                      </div>
                      <div class="flex items-center gap-2 px-3 py-1.5 bg-green-50 text-green-700 rounded-full text-xs font-bold border border-green-100">
                          <CheckCircle class="w-3.5 h-3.5" />
                          リアルタイム同期中
                      </div>
                  </div>
                  <div class="bg-white rounded-2xl shadow-xl border border-gray-200">
                      <div class="bg-gray-100/50 p-12">
                          <div class="bg-white shadow-2xl mx-auto w-full max-w-[800px]">
                              <iframe
                                  ref="previewIframe"
                                  :srcdoc="iframeDoc"
                                  class="w-full border-none"
                                  style="min-height: 800px; display: block;"
                              ></iframe>
                          </div>
                      </div>
                  </div>
              </div>

          </div>
      </div>

      <!-- Footer Info Bar (Moved above the action bar) -->
      <div class="bg-slate-100 border-t border-gray-200 px-8 py-2.5 flex items-center justify-between shrink-0 text-[10px] font-bold text-gray-400 uppercase tracking-widest sticky bottom-[88px] z-20">
          <div class="flex items-center gap-4">
              <span>Status: Draft Mode</span>
              <span class="w-1 h-1 rounded-full bg-gray-300"></span>
              <span>Template: {{ templates.find(t => t.id === selectedTemplateId)?.name }}</span>
          </div>
          <div class="flex items-center gap-1">
              <AlertCircleIcon class="w-3 h-3" />
              <span>{{ isApprovalRequired ? '承認フローが完了後に自動送付されます' : '金額・取引先・送付先が揃ったら送付できます' }}</span>
          </div>
      </div>

      <!-- Action Bottom Bar (Strict Bottom Fix) -->
      <div class="sticky bottom-0 left-0 right-0 z-30 bg-white border-t border-gray-200 px-8 py-4 shadow-[0_-4px_10px_rgba(0,0,0,0.05)] shrink-0">
          <div class="max-w-[1400px] mx-auto w-full flex items-center justify-between gap-4">
              <div class="flex items-center gap-4 lg:gap-8 min-w-0">
                  <div class="flex flex-col shrink-0">
                      <span class="text-[10px] text-gray-500 font-bold uppercase tracking-widest mb-0.5">お支払い合計 (税込)</span>
                      <span class="text-3xl font-black text-gray-900 tracking-tight">¥{{ formatCurrency(totalAmount) }}</span>
                  </div>
                  <div class="h-10 w-px bg-gray-200 shrink-0 hidden sm:block"></div>
                  <div class="flex flex-col min-w-0">
                      <span class="text-[10px] text-gray-500 font-bold uppercase tracking-widest mb-0.5">宛先</span>
                      <span class="text-sm font-bold text-gray-700 truncate block">{{ clientDisplayName }}</span>
                  </div>
              </div>
              <div class="flex items-center gap-2 lg:gap-4 shrink-0">
                  <button @click="saveDraft" :disabled="isSaving" class="px-4 lg:px-6 py-3 rounded-xl font-bold text-sm text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-all flex items-center gap-2 shadow-sm whitespace-nowrap">
                      <Save v-if="!isSaving" class="w-4 h-4" />
                      <Loader2 v-else class="w-4 h-4 animate-spin" />
                      <span class="hidden sm:inline">{{ editingInvoiceId ? '修正を保存' : '下書き保存' }}</span>
                      <span class="sm:hidden">下書き</span>
                  </button>
                  <!-- 承認不要 かつ 送付可能 -->
                  <button
                    v-if="canSubmit && !isApprovalRequired"
                    @click="submitInvoice"
                    :disabled="isSaving"
                    class="px-5 lg:px-8 py-3 rounded-xl font-bold text-sm text-white bg-blue-600 hover:bg-blue-700 transition-all shadow-md flex items-center gap-2 whitespace-nowrap"
                  >
                    <Send v-if="!isSaving" class="w-4 h-4" />
                    <Loader2 v-else class="w-4 h-4 animate-spin" />
                    この内容で送付する
                  </button>

                  <!-- 承認必要 かつ 送付可能 -->
                  <button
                    v-else-if="canSubmit && isApprovalRequired"
                    @click="submitInvoice"
                    :disabled="isSaving"
                    class="px-5 lg:px-8 py-3 rounded-xl font-bold text-sm text-white bg-purple-600 hover:bg-purple-700 transition-all shadow-md flex items-center gap-2 whitespace-nowrap"
                  >
                    <ShieldCheck v-if="!isSaving" class="w-4 h-4" />
                    <Loader2 v-else class="w-4 h-4 animate-spin" />
                    承認申請する
                  </button>

                  <!-- 未入力（グレーアウト） -->
                  <button
                    v-else
                    disabled
                    class="px-5 lg:px-8 py-3 rounded-xl font-bold text-sm text-white bg-gray-300 cursor-not-allowed flex items-center gap-2 whitespace-nowrap"
                  >
                    <Send class="w-4 h-4" />
                    <span>{{ !activeClientId ? '取引先を選択してください' : !recipientEmail ? '送付先を入力してください' : '金額を入力してください' }}</span>
                  </button>
              </div>
          </div>
      </div>

      <!-- Modals -->
      <ClientFormModal :show="isModalOpen" @close="isModalOpen = false" @save="handleClientSave" />
      
      <TemplateEditorModal 
          :show="isTemplateEditorOpen" 
          :initial-name="latestExtractedName"
          :initial-html="latestExtractedHtml"
          @close="isTemplateEditorOpen = false" 
          @save="handleTemplateSave"
      />

      <!-- Success Popups -->
      <div v-if="showSuccessPopup" class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-gray-900/60 backdrop-blur-sm transition-opacity">
          <div class="bg-white rounded-3xl p-10 max-w-sm w-full text-center shadow-2xl transform transition-all scale-100 border border-gray-100">
              <div class="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                  <CheckCircle class="w-10 h-10 text-green-600" />
              </div>
              <h3 class="text-2xl font-black text-gray-900 mb-2">{{ isApprovalRequired ? '承認申請完了' : '請求書発行完了' }}</h3>
              <p class="text-gray-500 text-sm mb-8 leading-relaxed">
                {{ isApprovalRequired ? 'ワークフローが開始されました。承認されると自動的に送信されます。' : '請求書が正常に作成され、クライアントへ送信されました。' }}
              </p>
              <button @click="handleSuccessConfirm" class="w-full py-4 bg-gray-900 text-white rounded-2xl font-bold hover:bg-gray-800 transition-colors shadow-lg">一覧へ戻る</button>
          </div>
      </div>

      <div v-if="showDraftSuccessPopup" class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-gray-900/40 backdrop-blur-sm">
          <div class="bg-white rounded-3xl p-8 max-w-sm w-full text-center shadow-2xl border border-gray-100">
              <div class="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <Save class="w-8 h-8 text-blue-600" />
              </div>
              <h3 class="text-xl font-bold text-gray-900 mb-2">下書き保存完了</h3>
              <p class="text-gray-500 text-sm mb-6">下書きとして保存しました。一覧からいつでも再開できます。</p>
              <button @click="handleDraftSuccessConfirm" class="w-full py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-colors">確認</button>
          </div>
      </div>

      <!-- Delete Confirmation -->
      <div v-if="templateToDelete" class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-gray-900/40 backdrop-blur-sm">
          <div class="bg-white rounded-3xl p-8 max-w-sm w-full text-center shadow-2xl border border-gray-100">
              <div class="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <AlertCircle class="w-8 h-8 text-red-600" />
              </div>
              <h3 class="text-xl font-bold text-gray-900 mb-2">テンプレートの削除</h3>
              <p class="text-gray-500 text-sm mb-6">「{{ templateToDelete.name }}」を削除してもよろしいですか？この操作は取り消せません。</p>
              <div class="flex gap-3">
                  <button @click="templateToDelete = null" class="flex-1 py-3 bg-gray-100 text-gray-600 rounded-xl font-bold hover:bg-gray-200 transition-colors">キャンセル</button>
                  <button @click="executeDeleteTemplate" class="flex-1 py-3 bg-red-600 text-white rounded-xl font-bold hover:bg-red-700 transition-colors">削除する</button>
              </div>
          </div>
      </div>

    </div>
  </Transition>
</template>


<style scoped>
.drag-list-move,
.drag-list-enter-active,
.drag-list-leave-active {
  transition: all 0.4s ease;
}

.drag-list-enter-from,
.drag-list-leave-to {
  opacity: 0;
  transform: scale(0.8) translateY(20px);
}

.drag-list-leave-active {
  position: absolute;
}

::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #e2e8f0;
  border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
  background: #cbd5e1;
}

.fade-page-enter-active, .fade-page-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.fade-page-enter-from { opacity: 0; transform: translateY(10px); }
.fade-page-leave-to { opacity: 0; transform: translateY(-10px); }
</style>
