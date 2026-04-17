<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { FileText, Plus, Edit2, Trash2, Eye } from 'lucide-vue-next';
import { api } from '@/lib/api';
import { useAuth } from '@/composables/useAuth';

const { isAccountingOrAbove } = useAuth();

interface Template {
  id: string;
  name: string;
  description: string;
  thumbnail: string;
  is_active: boolean;
  is_default: boolean;
  template_type: string;
}

const templates = ref<Template[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);
const showForm = ref(false);
const editingId = ref<string | null>(null);
const isSaving = ref(false);
const previewHtml = ref('');
const showPreview = ref(false);

const form = ref({
  name: '',
  description: '',
  html: '',
  thumbnail: 'bg-blue-50 border-blue-200',
  is_default: false,
  template_type: 'invoice',
});

const fetchTemplates = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await api.get<Template[]>('/invoices/templates?template_type=invoice');
    templates.value = data;
  } catch (e: any) {
    error.value = e.message ?? '取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

const handleSave = async () => {
  isSaving.value = true;
  error.value = null;
  try {
    if (editingId.value) {
      await api.put(`/invoices/templates/${editingId.value}`, form.value);
    } else {
      await api.post('/invoices/templates', form.value);
    }
    resetForm();
    await fetchTemplates();
  } catch (e: any) {
    error.value = e.message;
  } finally {
    isSaving.value = false;
  }
};

const handleEdit = async (t: Template) => {
  const detail = await api.get<any>(`/invoices/templates/${t.id}`);
  editingId.value = t.id;
  form.value = {
    name: detail.name,
    description: detail.description,
    html: detail.html || '',
    thumbnail: detail.thumbnail,
    is_default: detail.is_default,
    template_type: 'invoice',
  };
  showForm.value = true;
};

const handleDelete = async (t: Template) => {
  if (!confirm(`「${t.name}」を削除しますか？`)) return;
  try {
    await api.delete(`/invoices/templates/${t.id}`);
    await fetchTemplates();
  } catch (e: any) {
    error.value = e.message;
  }
};

const handlePreview = async (t: Template) => {
  const detail = await api.get<any>(`/invoices/templates/${t.id}`);
  previewHtml.value = detail.html || '';
  showPreview.value = true;
};

const resetForm = () => {
  showForm.value = false;
  editingId.value = null;
  form.value = { name: '', description: '', html: '', thumbnail: 'bg-blue-50 border-blue-200', is_default: false, template_type: 'invoice' };
};

onMounted(fetchTemplates);
</script>

<template>
  <div class="p-6 max-w-4xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <FileText class="text-indigo-600" :size="22" />
        <div>
          <h1 class="text-xl font-bold text-slate-800">請求書テンプレート</h1>
          <p class="text-sm text-slate-500">請求書の HTML テンプレートを管理します</p>
        </div>
      </div>
      <button v-if="isAccountingOrAbove" @click="showForm = true"
        class="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors">
        <Plus :size="15" /> 新規作成
      </button>
    </div>

    <div v-if="error" class="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{{ error }}</div>

    <!-- テンプレート一覧 -->
    <div v-if="isLoading" class="space-y-3">
      <div v-for="i in 3" :key="i" class="h-20 bg-slate-100 rounded-xl animate-pulse" />
    </div>
    <div v-else-if="templates.length === 0"
      class="text-center py-16 text-slate-400 bg-white rounded-2xl border border-slate-200">
      <FileText :size="40" class="mx-auto mb-3 opacity-30" />
      <p class="text-sm">テンプレートがありません。「新規作成」から追加してください。</p>
    </div>
    <div v-else class="space-y-3">
      <div v-for="t in templates" :key="t.id"
        class="bg-white rounded-xl border border-slate-200 p-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div :class="['w-10 h-10 rounded-lg border-2 shrink-0', t.thumbnail]" />
          <div>
            <p class="font-semibold text-slate-800">{{ t.name }}
              <span v-if="t.is_default" class="ml-2 text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">デフォルト</span>
            </p>
            <p class="text-xs text-slate-500">{{ t.description }}</p>
          </div>
        </div>
        <div class="flex gap-1">
          <button @click="handlePreview(t)" class="p-2 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors" title="プレビュー">
            <Eye :size="15" />
          </button>
          <button v-if="isAccountingOrAbove" @click="handleEdit(t)" class="p-2 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors">
            <Edit2 :size="15" />
          </button>
          <button v-if="isAccountingOrAbove && !t.is_default" @click="handleDelete(t)" class="p-2 hover:bg-red-50 rounded-lg text-red-400 transition-colors">
            <Trash2 :size="15" />
          </button>
        </div>
      </div>
    </div>

    <!-- 作成・編集フォーム -->
    <Teleport to="body">
      <div v-if="showForm" class="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
          <h2 class="text-lg font-bold mb-4">{{ editingId ? 'テンプレートを編集' : 'テンプレートを作成' }}</h2>
          <div class="space-y-4">
            <div>
              <label class="text-sm font-medium text-slate-700 block mb-1">テンプレート名</label>
              <input v-model="form.name" type="text" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
            </div>
            <div>
              <label class="text-sm font-medium text-slate-700 block mb-1">説明</label>
              <input v-model="form.description" type="text" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
            </div>
            <div>
              <label class="text-sm font-medium text-slate-700 block mb-1">HTML テンプレート</label>
              <textarea v-model="form.html" rows="10" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-indigo-500 outline-none" />
            </div>
            <div class="flex items-center gap-2">
              <input id="is_default" v-model="form.is_default" type="checkbox" class="accent-indigo-600" />
              <label for="is_default" class="text-sm text-slate-700">デフォルトとして設定する</label>
            </div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button @click="resetForm" class="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">キャンセル</button>
            <button @click="handleSave" :disabled="isSaving"
              class="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">
              {{ isSaving ? '保存中...' : '保存する' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- プレビューモーダル -->
    <Teleport to="body">
      <div v-if="showPreview" class="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        @click.self="showPreview = false">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-auto p-6">
          <div class="flex justify-between items-center mb-4">
            <h2 class="font-bold text-slate-800">HTMLプレビュー</h2>
            <button @click="showPreview = false" class="text-slate-400 hover:text-slate-700 text-xl">×</button>
          </div>
          <div v-html="previewHtml" class="border border-slate-200 rounded-lg p-4 overflow-auto" />
        </div>
      </div>
    </Teleport>
  </div>
</template>
