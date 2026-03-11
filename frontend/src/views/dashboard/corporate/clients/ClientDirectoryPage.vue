<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Plus, Search, Filter, Building2, User, MapPin, Mail, Phone, Edit2, Trash2 } from 'lucide-vue-next';
import ClientFormModal from '@/components/invoices/ClientFormModal.vue';
import { useClients } from '@/composables/useClients';

// Template-compatible Client shape (adds display-only fields)
interface ClientDisplay {
  id: string;
  name: string;
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

// --- COMPOSABLE ---
const { clients: apiClients, fetchClients, createClient, updateClient, deleteClient } = useClients();

const mapToDisplay = (c: any): ClientDisplay => ({
  id: c.id ?? c._id,
  name: c.name,
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

const mockClients = computed(() => apiClients.value.map(mapToDisplay));

onMounted(fetchClients);

// --- STATE ---
const searchQuery = ref('');
const isModalOpen = ref(false);
const editingClient = ref<ClientDisplay | null>(null);

// --- COMPUTED ---
const filteredClients = computed(() => {
  if (!searchQuery.value) return mockClients.value;
  const q = searchQuery.value.toLowerCase();
  return mockClients.value.filter(c =>
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

const handleSave = async (clientData: any) => {
  const payload = {
    name: clientData.name,
    registration_number: clientData.companyRegistrationNumber,
    department: clientData.department,
    contact_person: clientData.contactPerson,
    email: clientData.email,
    phone: clientData.phone,
    postal_code: clientData.postalCode,
    address: clientData.address,
    payment_terms: clientData.paymentTerms,
    internal_notes: clientData.internalNotes,
  };
  if (editingClient.value?.id) {
    await updateClient(editingClient.value.id, payload);
  } else {
    await createClient(payload as any);
  }
  isModalOpen.value = false;
};

const handleDelete = async (id: string, name: string) => {
  if (confirm(`本当に「${name}」を削除してもよろしいですか？\n※この操作は取り消せません。`)) {
    await deleteClient(id);
  }
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
      
      <!-- Data Table -->
      <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse min-w-[1000px]">
            <thead>
              <tr class="bg-slate-50 border-b border-slate-200">
                <th class="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider w-80">取引先 (会社名)</th>
                <th class="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider w-56">担当者・連絡先</th>
                <th class="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">所在地</th>
                <th class="px-6 py-4 text-center text-xs font-bold text-slate-500 uppercase tracking-wider w-24">操作</th>
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
                    <div class="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center shrink-0 mt-0.5">
                      <Building2 class="text-indigo-500" :size="20" />
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
                  <div class="flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button 
                      @click="openEditModal(client)"
                      class="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                      title="編集"
                    >
                      <Edit2 :size="18" />
                    </button>
                    <button 
                      @click="handleDelete(client.id, client.name)"
                      class="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="削除"
                    >
                      <Trash2 :size="18" />
                    </button>
                  </div>
                </td>
              </tr>
              
              <!-- Empty State -->
              <tr v-if="filteredClients.length === 0">
                <td colspan="4" class="px-6 py-16 text-center text-slate-500">
                  <div class="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Building2 class="text-slate-400" :size="32" />
                  </div>
                  <p class="text-lg font-bold text-slate-700 mb-1">取引先が見つかりません</p>
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

    <!-- Unified Form Modal -->
    <ClientFormModal 
      :show="isModalOpen" 
      :editData="editingClient"
      @close="isModalOpen = false"
      @save="handleSave"
    />
  </div>
</template>
