<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '@/lib/api';
import { Plus, Edit, Trash2, Save, X, BookText } from 'lucide-vue-next';

interface JournalEntry {
  subject: string;
  debit: string;
  credit: string;
  tax_category: string;
  keywords: string[];
}

const entries = ref<JournalEntry[]>([]);
const isLoading = ref(true);
const isSaving = ref(false);
const error = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const showModal = ref(false);
const isEditing = ref(false);
const editingEntry = ref<JournalEntry>({
  subject: '', debit: '', credit: '未払金', tax_category: '課税仕入 10%', keywords: [],
});
const keywordsInput = ref('');

const TAX_CATEGORIES = ['課税仕入 10%', '課税仕入 8% (軽減)', '非課税', '不課税仕入'];

const mapToEntries = (map: Record<string, any>): JournalEntry[] =>
  Object.entries(map).map(([subject, v]) => ({
    subject,
    debit: v.debit ?? '',
    credit: v.credit ?? '',
    tax_category: v.tax_category ?? '',
    keywords: Array.isArray(v.keywords) ? v.keywords : [],
  }));

const entriesToMap = (list: JournalEntry[]): Record<string, any> =>
  Object.fromEntries(list.map(e => [e.subject, {
    debit: e.debit,
    credit: e.credit,
    tax_category: e.tax_category,
    keywords: e.keywords,
  }]));

const fetchJournalMap = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await api.get<Record<string, any>>('/system-settings/journal-map');
    entries.value = mapToEntries(res);
  } catch (e: any) {
    error.value = e.message ?? '取得に失敗しました';
  } finally {
    isLoading.value = false;
  }
};

const saveAll = async () => {
  isSaving.value = true;
  error.value = null;
  successMessage.value = null;
  try {
    await api.put('/system-settings/journal-map', { journal_map: entriesToMap(entries.value) });
    successMessage.value = '保存しました';
    setTimeout(() => { successMessage.value = null; }, 3000);
  } catch (e: any) {
    error.value = e.message ?? '保存に失敗しました';
  } finally {
    isSaving.value = false;
  }
};

const openNewModal = () => {
  editingEntry.value = { subject: '', debit: '', credit: '未払金', tax_category: '課税仕入 10%', keywords: [] };
  keywordsInput.value = '';
  isEditing.value = false;
  showModal.value = true;
};

const openEditModal = (entry: JournalEntry) => {
  editingEntry.value = { ...entry, keywords: [...entry.keywords] };
  keywordsInput.value = entry.keywords.join('、');
  isEditing.value = true;
  showModal.value = true;
};

const saveEntry = () => {
  const kws = keywordsInput.value
    .split(/[、,，\n]/)
    .map(s => s.trim())
    .filter(Boolean);
  editingEntry.value.keywords = kws;

  if (!editingEntry.value.subject.trim()) return;

  if (isEditing.value) {
    const idx = entries.value.findIndex(e => e.subject === editingEntry.value.subject);
    if (idx >= 0) entries.value[idx] = { ...editingEntry.value };
  } else {
    entries.value.push({ ...editingEntry.value });
  }
  showModal.value = false;
};

const deleteEntry = (subject: string) => {
  if (!confirm(`「${subject}」を削除します。この科目をキーワードルールに使用している税理士法人・法人の仕訳処理に影響が出る可能性があります。続けますか？`)) return;
  entries.value = entries.value.filter(e => e.subject !== subject);
};

onMounted(fetchJournalMap);
</script>

<template>
  <div class="p-6 md:p-8 max-w-6xl mx-auto">
    <div class="flex items-start justify-between mb-6 gap-4">
      <div>
        <h1 class="text-2xl font-bold text-slate-100 flex items-center gap-2">
          <BookText class="w-6 h-6 text-sky-400" />
          勘定科目マスター管理
        </h1>
        <p class="text-sm text-slate-400 mt-1">仕訳マッチングで使用する勘定科目マスターを管理します。</p>
      </div>
      <div class="flex gap-2 shrink-0">
        <button
          @click="openNewModal"
          class="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus :size="16" /> 科目追加
        </button>
        <button
          @click="saveAll"
          :disabled="isSaving"
          class="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Save :size="16" /> {{ isSaving ? '保存中...' : '保存する' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="bg-red-900/30 border border-red-700 text-red-300 rounded-xl p-4 mb-5 text-sm">
      {{ error }}
    </div>

    <Transition name="toast">
      <div
        v-if="successMessage"
        class="fixed top-5 right-5 z-50 bg-emerald-600 text-white px-5 py-3 rounded-xl shadow-lg text-sm font-medium"
      >
        {{ successMessage }}
      </div>
    </Transition>

    <div v-if="isLoading" class="space-y-3">
      <div v-for="i in 8" :key="i" class="h-14 bg-slate-800 rounded-xl animate-pulse" />
    </div>

    <div v-else class="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-700/50 border-b border-slate-700">
          <tr>
            <th class="text-left px-4 py-3 text-slate-300 font-semibold">科目名</th>
            <th class="text-left px-4 py-3 text-slate-300 font-semibold">借方</th>
            <th class="text-left px-4 py-3 text-slate-300 font-semibold">貸方</th>
            <th class="text-left px-4 py-3 text-slate-300 font-semibold">税区分</th>
            <th class="text-left px-4 py-3 text-slate-300 font-semibold">キーワード</th>
            <th class="px-4 py-3 text-right text-slate-300 font-semibold">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-700">
          <tr v-if="entries.length === 0">
            <td colspan="6" class="px-4 py-8 text-center text-slate-400">科目がありません</td>
          </tr>
          <tr v-for="entry in entries" :key="entry.subject" class="hover:bg-slate-700/30 transition-colors group">
            <td class="px-4 py-3 font-medium text-slate-100">{{ entry.subject }}</td>
            <td class="px-4 py-3 text-slate-300">{{ entry.debit }}</td>
            <td class="px-4 py-3 text-slate-300">{{ entry.credit }}</td>
            <td class="px-4 py-3">
              <span
                class="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium"
                :class="entry.tax_category === '非課税' ? 'bg-slate-700 text-slate-300' : 'bg-sky-900/40 text-sky-300'"
              >
                {{ entry.tax_category }}
              </span>
            </td>
            <td class="px-4 py-3 text-slate-400 text-xs max-w-xs">
              <span class="line-clamp-1">{{ entry.keywords.join('、') }}</span>
            </td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  @click="openEditModal(entry)"
                  class="p-1.5 text-slate-400 hover:text-sky-400 hover:bg-sky-900/30 rounded transition-colors"
                  title="編集"
                >
                  <Edit :size="15" />
                </button>
                <button
                  @click="deleteEntry(entry.subject)"
                  class="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-900/30 rounded transition-colors"
                  title="削除"
                >
                  <Trash2 :size="15" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Edit / New Modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="showModal = false" />
      <div class="bg-slate-800 rounded-xl shadow-xl w-full max-w-lg relative z-10 overflow-hidden border border-slate-700">
        <div class="px-6 py-4 border-b border-slate-700 flex items-center justify-between bg-slate-900/50">
          <h2 class="text-base font-bold text-slate-100">
            {{ isEditing ? '勘定科目を編集' : '勘定科目を追加' }}
          </h2>
          <button @click="showModal = false" class="text-slate-400 hover:text-slate-200 transition-colors p-1">
            <X :size="18" />
          </button>
        </div>

        <div class="p-6 space-y-4">
          <div>
            <label class="block text-xs font-bold text-slate-300 mb-1.5">科目名</label>
            <input
              v-model="editingEntry.subject"
              type="text"
              :disabled="isEditing"
              placeholder="例: 旅費交通費"
              class="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none disabled:opacity-50"
            />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-bold text-slate-300 mb-1.5">借方</label>
              <input
                v-model="editingEntry.debit"
                type="text"
                placeholder="例: 旅費交通費"
                class="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none"
              />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-300 mb-1.5">貸方</label>
              <input
                v-model="editingEntry.credit"
                type="text"
                placeholder="例: 未払金"
                class="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none"
              />
            </div>
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-300 mb-1.5">税区分</label>
            <select
              v-model="editingEntry.tax_category"
              class="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none"
            >
              <option v-for="tc in TAX_CATEGORIES" :key="tc" :value="tc">{{ tc }}</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-300 mb-1.5">
              キーワード <span class="text-slate-500 font-normal">（読点・カンマ・改行区切り）</span>
            </label>
            <textarea
              v-model="keywordsInput"
              rows="3"
              placeholder="例: タクシー、電車、バス、交通"
              class="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none resize-none"
            />
          </div>
        </div>

        <div class="px-6 py-4 border-t border-slate-700 bg-slate-900/30 flex justify-end gap-3">
          <button @click="showModal = false" class="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-700 rounded-lg transition-colors">
            キャンセル
          </button>
          <button
            @click="saveEntry"
            :disabled="!editingEntry.subject.trim()"
            class="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Save :size="15" /> 確定
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
