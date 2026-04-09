<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Plus, Search, Filter, Building2, User, MapPin, Mail, Phone, Edit2, Trash2, CreditCard, X, Tags, Trash } from 'lucide-vue-next';
import ClientFormModal from '@/components/invoices/ClientFormModal.vue';
import BankAccountSection from '@/components/shared/BankAccountSection.vue';
import { useClients, type Client } from '@/composables/useClients';
import { useMatchingPatterns, sourceLabel } from '@/composables/useMatchingPatterns';

// Template-compatible Client shape (adds display-only fields)
interface ClientDisplay {
  id: string;
  name: string;
  client_category?: 'company' | 'individual';
  companyRegistrationNumber: string;
  department: string;
  contactPerson: string;
  email: string;
  phone: string;
  postalCode: string;
  address: string;
  paymentTerms: string;
  internalNotes: string;
}

// --- 法人判定（client_category未設定時のフォールバック） ---
const CORP_KEYWORDS = ['株式会社', '有限会社', '合同会社', '合名会社', '合資会社', '一般社団法人', '公益社団法人', '一般財団法人', '公益財団法人'];
const isCompany = (c: ClientDisplay) =>
  c.client_category ? c.client_category === 'company' : CORP_KEYWORDS.some(k => c.name.includes(k));

// --- COMPOSABLE ---
const { clients: apiClients, fetchClients, deleteClient } = useClients();
const { patterns: matchingPatterns, isLoading: isPatternsLoading, fetchPatterns, addPattern, removePattern } = useMatchingPatterns();

const mapToDisplay = (c: any): ClientDisplay => ({
  id: c.id ?? c._id,
  name: c.name,
  client_category: c.client_category ?? undefined,
  companyRegistrationNumber: c.registration_number ?? '',
  department: c.department ?? '',
  contactPerson: c.contact_person ?? '',
  email: c.email ?? '',
  phone: c.phone ?? '',
  postalCode: c.postal_code ?? '',
  address: c.address ?? '',
  paymentTerms: c.payment_terms ?? '都度払い',
  internalNotes: c.internal_notes ?? '',
});

const displayClients = computed(() => apiClients.value.map(mapToDisplay));

onMounted(fetchClients);

// --- STATE ---
const activeTab = ref<'company' | 'individual'>('company');
const searchQuery = ref('');
const isModalOpen = ref(false);
const editingClient = ref<ClientDisplay | null>(null);
const bankClient = ref<ClientDisplay | null>(null);
const patternModalClient = ref<ClientDisplay | null>(null);
const newPatternInput = ref('');
const isAddingPattern = ref(false);

// --- COMPUTED ---
const companyCount = computed(() => displayClients.value.filter(c => isCompany(c)).length);
const individualCount = computed(() => displayClients.value.filter(c => !isCompany(c)).length);

const filteredClients = computed(() => {
  let list = displayClients.value.filter(c =>
    activeTab.value === 'company' ? isCompany(c) : !isCompany(c)
  );
  if (!searchQuery.value) return list;
  const q = searchQuery.value.toLowerCase();
  return list.filter(c =>
    c.name.toLowerCase().includes(q) ||
    c.contactPerson.toLowerCase().includes(q) ||
    c.email.toLowerCase().includes(q) ||
    c.id.toLowerCase().includes(q)
  );
});

// --- METHODS ---
const openNewModal = () => {
  editingClient.value = null;
  isModalOpen.value = true;
};

const openEditModal = (client: ClientDisplay) => {
  editingClient.value = { ...client };
  isModalOpen.value = true;
};

const handleSaved = () => {
  fetchClients();
};

const handleDelete = async (id: string, name: string) => {
  if (confirm(`本当に「${name}」を削除してもよろしいですか？\n※この操作は取り消せません。`)) {
    await deleteClient(id);
  }
};

const openBankModal = (client: ClientDisplay) => {
  bankClient.value = client;
};

const openBankNamesModal = async (client: ClientDisplay) => {
  patternModalClient.value = client;
  newPatternInput.value = '';
  await fetchPatterns(client.id);
};

const handleAddPattern = async () => {
  if (!patternModalClient.value || !newPatternInput.value.trim()) return;
  isAddingPattern.value = true;
  const created = await addPattern(patternModalClient.value.id, newPatternInput.value.trim(), 'manual');
  if (created) {
    newPatternInput.value = '';
  }
  isAddingPattern.value = false;
};

const handleRemovePattern = async (patternId: string) => {
  await removePattern(patternId);
};
</script>

<template>
  <div class="h-full flex flex-col bg-slate-50">
    <!-- Header -->
    <header class="bg-white border-b border-slate-200 px-8 py-6 shrink-0 z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 tracking-tight">取引先管理</h1>
        <p class="text-sm text-slate-500 mt-1">請求先として利用する企業や個人のマスターデータを管理します</p>
      </div>
      <button 
        @click="openNewModal"
        class="bg-indigo-600 text-white px-5 py-2.5 rounded-lg hover:bg-indigo-700 transition-colors font-bold flex items-center shadow-sm"
      >
        <Plus class="w-4 h-4 mr-2" /> 新規取引先を追加
      </button>
    </header>

    <!-- Toolbar -->
    <div class="px-8 py-4 bg-white border-b border-slate-200 flex items-center justify-between shrink-0">
      <div class="relative w-full max-w-sm">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <input 
          v-model="searchQuery" 
          type="text" 
          placeholder="会社名、担当者名、メールアドレスで検索..." 
          class="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all" 
        />
      </div>
      <button class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
        <Filter class="w-4 h-4" /> 絞り込み
      </button>
    </div>

    <!-- Main Content -->
    <main class="flex-1 overflow-x-hidden overflow-y-auto p-8">

      <!-- Tabs -->
      <div class="flex bg-gray-200/50 p-1.5 rounded-xl mb-6 shadow-inner border border-gray-200/50">
        <button
          @click="activeTab = 'company'"
          class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'company' ? 'bg-white text-blue-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <Building2 class="w-4 h-4" />
          法人 <span class="text-[10px] px-1.5 py-0.5 rounded-full ml-1" :class="activeTab === 'company' ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'">{{ companyCount }}</span>
        </button>
        <button
          @click="activeTab = 'individual'"
          class="flex-1 px-6 py-2.5 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
          :class="activeTab === 'individual' ? 'bg-white text-indigo-700 shadow-sm ring-1 ring-gray-900/5' : 'text-gray-600 hover:text-gray-900'"
        >
          <User class="w-4 h-4" />
          個人 <span class="text-[10px] px-1.5 py-0.5 rounded-full ml-1" :class="activeTab === 'individual' ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-200 text-gray-600'">{{ individualCount }}</span>
        </button>
      </div>

      <!-- Data Table -->
      <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse min-w-[1000px]">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200">
                <th class="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider w-80">{{ activeTab === 'company' ? '取引先（法人）' : '取引先（個人）' }}</th>
                <th class="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider w-56">担当者・連絡先</th>
                <th class="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">所在地</th>
                <th class="px-6 py-4 text-center text-xs font-bold text-slate-500 uppercase tracking-wider w-36">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr 
                v-for="client in filteredClients" 
                :key="client.id"
                class="hover:bg-indigo-50/30 transition-colors group"
              >
                <!-- Company Name -->
                <td class="px-6 py-4 align-top">
                  <div class="flex items-start gap-3">
                    <div class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                      :class="activeTab === 'company' ? 'bg-blue-50 border border-blue-100' : 'bg-indigo-50 border border-indigo-100'">
                      <Building2 v-if="activeTab === 'company'" class="text-blue-500" :size="20" />
                      <User v-else class="text-indigo-500" :size="20" />
                    </div>
                    <div>
                      <div class="font-bold text-slate-900 text-[15px] mb-1">{{ client.name }}</div>
                      <div class="text-xs text-slate-500 font-mono mb-1">ID: {{ client.id }}</div>
                      <div v-if="client.companyRegistrationNumber" class="text-xs text-slate-400">
                        登録番号: {{ client.companyRegistrationNumber }}
                      </div>
                    </div>
                  </div>
                </td>
                
                <!-- Contact Info -->
                <td class="px-6 py-4 align-top">
                  <div class="space-y-2">
                    <div v-if="client.contactPerson" class="flex items-center gap-2 text-sm text-slate-700 font-medium">
                      <User :size="14" class="text-slate-400" />
                      {{ client.department }} {{ client.contactPerson }}
                    </div>
                    <div v-if="client.email" class="flex items-center gap-2 text-sm text-slate-600">
                      <Mail :size="14" class="text-slate-400" />
                      {{ client.email }}
                    </div>
                    <div v-if="client.phone" class="flex items-center gap-2 text-sm text-slate-600">
                      <Phone :size="14" class="text-slate-400" />
                      {{ client.phone }}
                    </div>
                    <div class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200 mt-1">
                      {{ client.paymentTerms }}
                    </div>
                  </div>
                </td>
                
                <!-- Address & Notes -->
                <td class="px-6 py-4 align-top">
                  <div class="flex items-start gap-2 text-sm text-slate-600 mb-3">
                    <MapPin :size="14" class="text-slate-400 mt-0.5 shrink-0" />
                    <div>
                      <div>〒{{ client.postalCode }}</div>
                      <div class="leading-relaxed">{{ client.address }}</div>
                    </div>
                  </div>
                  <div v-if="client.internalNotes" class="bg-amber-50 border border-amber-100 rounded-md p-2 text-xs text-amber-800 flex gap-2">
                    <FileText :size="12" class="mt-0.5 shrink-0" />
                    <span class="line-clamp-2">{{ client.internalNotes }}</span>
                  </div>
                </td>

                <!-- Actions -->
                <td class="px-6 py-4 align-top text-center">
                  <div class="flex items-center justify-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      @click="openBankNamesModal(client)"
                      class="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-colors"
                      title="銀行表示名"
                    >
                      <Tags :size="16" />
                    </button>
                    <button
                      @click="openBankModal(client)"
                      class="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                      title="振込先口座"
                    >
                      <CreditCard :size="16" />
                    </button>
                    <button
                      @click="openEditModal(client)"
                      class="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                      title="編集"
                    >
                      <Edit2 :size="16" />
                    </button>
                    <button
                      @click="handleDelete(client.id, client.name)"
                      class="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="削除"
                    >
                      <Trash2 :size="16" />
                    </button>
                  </div>
                </td>
              </tr>
              
              <!-- Empty State -->
              <tr v-if="filteredClients.length === 0">
                <td colspan="4" class="px-6 py-16 text-center text-slate-500">
                  <div class="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Building2 v-if="activeTab === 'company'" class="text-slate-400" :size="32" />
                    <User v-else class="text-slate-400" :size="32" />
                  </div>
                  <p class="text-lg font-bold text-slate-700 mb-1">{{ activeTab === 'company' ? '法人取引先' : '個人取引先' }}が見つかりません</p>
                  <p class="text-sm">検索条件を変更するか、新しい取引先を登録してください。</p>
                  <button @click="openNewModal" class="mt-6 text-indigo-600 font-bold hover:underline">
                    + 新規取引先を追加する
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </main>

    <!-- Client Form Modal -->
    <ClientFormModal
      :show="isModalOpen"
      :editData="editingClient"
      @close="isModalOpen = false"
      @saved="handleSaved"
    />

    <!-- Matching Patterns Modal -->
    <Teleport to="body">
      <div v-if="patternModalClient" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" @click="patternModalClient = null"></div>
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg relative z-10 flex flex-col max-h-[85vh] overflow-hidden">
          <!-- Header -->
          <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 shrink-0">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 bg-violet-100 text-violet-600 rounded-xl flex items-center justify-center shrink-0">
                <Tags :size="18" />
              </div>
              <div>
                <p class="text-xs text-slate-500 font-medium">マッチングパターン</p>
                <h2 class="text-base font-bold text-slate-800 leading-tight">{{ patternModalClient.name }}</h2>
              </div>
            </div>
            <button @click="patternModalClient = null" class="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors">
              <X :size="20" />
            </button>
          </div>
          <!-- Body -->
          <div class="p-6 overflow-y-auto flex-1 space-y-5">
            <p class="text-sm text-slate-500">
              銀行振込明細の「摘要」欄に表示される名称パターンを登録します。<br>
              登録されたパターンは自動消込の名称マッチングで使用されます。
            </p>

            <!-- ローディング -->
            <div v-if="isPatternsLoading" class="text-center py-4 text-sm text-slate-400">読み込み中...</div>

            <!-- 登録済みパターン一覧 -->
            <div v-else-if="matchingPatterns.length" class="space-y-2">
              <p class="text-xs font-bold text-slate-500 uppercase tracking-wider">登録済みパターン ({{ matchingPatterns.length }}件)</p>
              <div
                v-for="entry in matchingPatterns"
                :key="entry.id"
                class="flex items-center justify-between px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg group"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <span class="font-mono text-sm text-slate-800 truncate">{{ entry.pattern }}</span>
                  <span
                    :class="{
                      'bg-violet-100 text-violet-700': entry.source === 'ai_suggest',
                      'bg-blue-100 text-blue-700': entry.source === 'manual_match',
                      'bg-slate-200 text-slate-600': entry.source === 'manual',
                    }"
                    class="text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0"
                  >{{ sourceLabel(entry.source) }}</span>
                  <span v-if="entry.used_count > 0" class="text-[10px] text-slate-400 shrink-0">
                    {{ entry.used_count }}回使用
                  </span>
                </div>
                <button
                  @click="handleRemovePattern(entry.id)"
                  class="p-1 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-all rounded"
                >
                  <Trash :size="14" />
                </button>
              </div>
            </div>
            <p v-else class="text-sm text-slate-400 italic">まだパターンが登録されていません</p>

            <!-- 追加フォーム -->
            <div class="pt-3 border-t border-slate-100">
              <p class="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">パターンを追加</p>
              <div class="flex gap-2">
                <input
                  v-model="newPatternInput"
                  type="text"
                  placeholder="例: タナカ ハナコ、(カ)タナカ商事"
                  class="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 outline-none"
                  @keyup.enter="handleAddPattern"
                />
                <button
                  @click="handleAddPattern"
                  :disabled="!newPatternInput.trim() || isAddingPattern"
                  class="px-4 py-2 bg-violet-600 text-white text-sm font-bold rounded-lg hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  追加
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Bank Account Modal -->
    <Teleport to="body">
      <div v-if="bankClient" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" @click="bankClient = null"></div>
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg relative z-10 flex flex-col max-h-[85vh] overflow-hidden">
          <!-- Header -->
          <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50 shrink-0">
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 bg-indigo-100 text-indigo-600 rounded-xl flex items-center justify-center shrink-0">
                <CreditCard :size="18" />
              </div>
              <div>
                <p class="text-xs text-slate-500 font-medium">振込先口座</p>
                <h2 class="text-base font-bold text-slate-800 leading-tight">{{ bankClient.name }}</h2>
              </div>
            </div>
            <button @click="bankClient = null" class="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors">
              <X :size="20" />
            </button>
          </div>
          <!-- Body -->
          <div class="p-6 overflow-y-auto flex-1">
            <BankAccountSection owner-type="client" :client-id="bankClient.id" />
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
