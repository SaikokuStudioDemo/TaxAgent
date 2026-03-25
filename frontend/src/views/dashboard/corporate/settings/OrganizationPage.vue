<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Users, FolderKanban, Edit2, Trash2, Building2, Check, X, Loader2 } from 'lucide-vue-next';
import { api } from '@/lib/api';

interface Group {
  id: string;
  name: string;
}

interface Department {
  id: string;
  name: string;
  groups: Group[];
}

interface SubProject {
  id: string;
  name: string;
  subPmName: string;
  status: 'active' | 'completed';
}

interface Project {
  id: string;
  name: string;
  pmName: string;
  status: 'active' | 'completed';
  subProjects?: SubProject[];
}

const activeTab = ref<'departments' | 'projects'>('departments');
const departments = ref<Department[]>([]);
const isLoading = ref(false);
const errorMsg = ref('');

// Editing state
const editingDeptId = ref<string | null>(null);
const editingDeptName = ref('');
const editingGroupKey = ref<string | null>(null); // "deptId:groupId"
const editingGroupName = ref('');

// New department form
const showNewDeptForm = ref(false);
const newDeptName = ref('');
const isAddingDept = ref(false);

// New group form: deptId -> name
const newGroupForms = ref<Record<string, string>>({});
const showGroupFormFor = ref<string | null>(null);
const isAddingGroup = ref<string | null>(null);

const fetchDepartments = async () => {
  isLoading.value = true;
  errorMsg.value = '';
  try {
    const data = await api.get<any[]>('/departments');
    departments.value = data.map((d: any) => ({
      id: d.id,
      name: d.name,
      groups: (d.groups || []).map((g: any) => ({ id: g.id, name: g.name })),
    }));
  } catch (e: any) {
    errorMsg.value = 'データの取得に失敗しました。';
    console.error(e);
  } finally {
    isLoading.value = false;
  }
};

onMounted(() => {
  fetchDepartments();
});

// --- Department CRUD ---

const startEditDept = (dept: Department) => {
  editingDeptId.value = dept.id;
  editingDeptName.value = dept.name;
  editingGroupKey.value = null;
};

const cancelEditDept = () => {
  editingDeptId.value = null;
  editingDeptName.value = '';
};

const saveDept = async (dept: Department) => {
  const name = editingDeptName.value.trim();
  if (!name) return;
  try {
    await api.patch(`/departments/${dept.id}`, { name });
    dept.name = name;
    cancelEditDept();
  } catch (e: any) {
    errorMsg.value = '部門名の更新に失敗しました。';
  }
};

const deleteDept = async (deptId: string) => {
  if (!confirm('この部門を削除してもよろしいですか？')) return;
  try {
    await api.delete(`/departments/${deptId}`);
    departments.value = departments.value.filter(d => d.id !== deptId);
  } catch (e: any) {
    errorMsg.value = '部門の削除に失敗しました。';
  }
};

const addDepartment = async () => {
  const name = newDeptName.value.trim();
  if (!name) return;
  isAddingDept.value = true;
  try {
    const created = await api.post<any>('/departments', { name });
    departments.value.push({ id: created.id, name: created.name, groups: created.groups || [] });
    newDeptName.value = '';
    showNewDeptForm.value = false;
  } catch (e: any) {
    errorMsg.value = '部門の作成に失敗しました。';
  } finally {
    isAddingDept.value = false;
  }
};

// --- Group CRUD ---

const startEditGroup = (deptId: string, group: Group) => {
  editingGroupKey.value = `${deptId}:${group.id}`;
  editingGroupName.value = group.name;
  editingDeptId.value = null;
};

const cancelEditGroup = () => {
  editingGroupKey.value = null;
  editingGroupName.value = '';
};

const saveGroup = async (dept: Department, group: Group) => {
  const name = editingGroupName.value.trim();
  if (!name) return;
  try {
    await api.patch(`/departments/${dept.id}/groups/${group.id}`, { name });
    group.name = name;
    cancelEditGroup();
  } catch (e: any) {
    errorMsg.value = 'グループ名の更新に失敗しました。';
  }
};

const deleteGroup = async (dept: Department, groupId: string) => {
  if (!confirm('このグループを削除してもよろしいですか？')) return;
  try {
    await api.delete(`/departments/${dept.id}/groups/${groupId}`);
    dept.groups = dept.groups.filter(g => g.id !== groupId);
  } catch (e: any) {
    errorMsg.value = 'グループの削除に失敗しました。';
  }
};

const toggleGroupForm = (deptId: string) => {
  if (showGroupFormFor.value === deptId) {
    showGroupFormFor.value = null;
  } else {
    showGroupFormFor.value = deptId;
    if (!newGroupForms.value[deptId]) newGroupForms.value[deptId] = '';
  }
};

const addGroup = async (dept: Department) => {
  const name = (newGroupForms.value[dept.id] || '').trim();
  if (!name) return;
  isAddingGroup.value = dept.id;
  try {
    const updated = await api.post<any>(`/departments/${dept.id}/groups`, { name });
    dept.groups = updated.groups || [];
    newGroupForms.value[dept.id] = '';
    showGroupFormFor.value = null;
  } catch (e: any) {
    errorMsg.value = 'グループの追加に失敗しました。';
  } finally {
    isAddingGroup.value = null;
  }
};

// --- Projects (mock data) ---
const projects = ref<Project[]>([
  {
    id: 'proj-1',
    name: '社内基幹システムリプレイス',
    pmName: '鈴木 一郎',
    status: 'active',
    subProjects: [
      { id: 'sub-1-1', name: '要件定義フェーズ', subPmName: '渡辺 翔太', status: 'completed' },
      { id: 'sub-1-2', name: '開発フェーズ', subPmName: '小林 さくら', status: 'active' }
    ]
  },
  { id: 'proj-2', name: '〇〇株式会社様 Webサイト制作', pmName: '高橋 健太', status: 'active' },
  { id: 'proj-3', name: '2025年 新卒採用プロジェクト', pmName: '佐藤 花子', status: 'completed' }
]);
</script>

<template>
  <div class="max-w-6xl mx-auto p-4 sm:p-8">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-2">
        <Building2 :size="24" class="text-blue-600" />
        部門・プロジェクト管理
      </h1>
      <p class="text-gray-500 mt-2">部門・プロジェクト編成 / 承認者設定。ここで設定した責任者が、承認ワークフローのルーティング先として自動的に使用されます。</p>
    </div>

    <!-- Error message -->
    <div v-if="errorMsg" class="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center justify-between">
      <span>{{ errorMsg }}</span>
      <button @click="errorMsg = ''" class="text-red-400 hover:text-red-600"><X :size="16" /></button>
    </div>

    <!-- Tabs -->
    <div class="flex border-b border-gray-200 mb-6">
      <button
        @click="activeTab = 'departments'"
        :class="['px-6 py-3 font-medium text-sm border-b-2 transition-colors', activeTab === 'departments' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300']">
        <div class="flex items-center gap-2">
          <Users :size="18" /> 部門 (Departments)
        </div>
      </button>
      <button
        @click="activeTab = 'projects'"
        :class="['px-6 py-3 font-medium text-sm border-b-2 transition-colors', activeTab === 'projects' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300']">
        <div class="flex items-center gap-2">
          <FolderKanban :size="18" /> プロジェクト (Projects)
        </div>
      </button>
    </div>

    <!-- Departments Tab -->
    <div v-if="activeTab === 'departments'" class="space-y-4">
      <div class="flex justify-between items-center bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <p class="text-sm text-gray-600">部門を作成し、グループ（課・チーム）を追加できます。</p>
        <button
          @click="showNewDeptForm = !showNewDeptForm"
          class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
          <Plus :size="16" />
          新規部門を作成
        </button>
      </div>

      <!-- New Department Form -->
      <div v-if="showNewDeptForm" class="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center gap-3">
        <input
          v-model="newDeptName"
          type="text"
          placeholder="部門名を入力..."
          @keydown.enter="addDepartment"
          @keydown.esc="showNewDeptForm = false; newDeptName = ''"
          class="flex-1 px-3 py-2 border border-blue-300 rounded-md focus:ring-2 focus:ring-blue-500 bg-white text-sm"
          autofocus
        />
        <button
          @click="addDepartment"
          :disabled="!newDeptName.trim() || isAddingDept"
          class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium flex items-center gap-1 disabled:opacity-50"
        >
          <Loader2 v-if="isAddingDept" :size="14" class="animate-spin" />
          <Check v-else :size="14" />
          追加
        </button>
        <button @click="showNewDeptForm = false; newDeptName = ''" class="text-gray-400 hover:text-gray-600 p-2">
          <X :size="16" />
        </button>
      </div>

      <!-- Loading -->
      <div v-if="isLoading" class="flex items-center justify-center py-12 text-indigo-500 gap-3">
        <Loader2 class="animate-spin" :size="32" />
        <span class="font-medium">読み込み中...</span>
      </div>

      <div v-else class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-500">
              <th class="py-3 px-4 w-7/12">部門・チーム名</th>
              <th class="py-3 px-4 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <template v-for="dept in departments" :key="dept.id">
              <!-- Department row -->
              <tr class="hover:bg-gray-50 transition-colors bg-white">
                <td class="py-3 px-4 font-bold text-gray-900 border-l-4 border-blue-500">
                  <div class="flex items-center gap-2">
                    <Building2 :size="16" class="text-blue-500 shrink-0" />
                    <!-- Editing mode -->
                    <template v-if="editingDeptId === dept.id">
                      <input
                        v-model="editingDeptName"
                        type="text"
                        @keydown.enter="saveDept(dept)"
                        @keydown.esc="cancelEditDept"
                        class="flex-1 px-2 py-1 border border-blue-400 rounded text-sm font-bold focus:ring-2 focus:ring-blue-500"
                        autofocus
                      />
                      <button @click="saveDept(dept)" class="text-blue-600 hover:text-blue-800 p-1"><Check :size="14" /></button>
                      <button @click="cancelEditDept" class="text-gray-400 hover:text-gray-600 p-1"><X :size="14" /></button>
                    </template>
                    <!-- Display mode -->
                    <span v-else>{{ dept.name }}</span>
                  </div>
                </td>
                <td class="py-3 px-4 text-right space-x-2">
                  <button
                    @click="toggleGroupForm(dept.id)"
                    class="text-gray-400 hover:text-emerald-600 p-1 bg-white rounded shadow-sm border border-gray-100 text-xs px-2"
                    title="グループを追加"
                  >
                    <Plus :size="14" class="inline" /> グループ追加
                  </button>
                  <button @click="startEditDept(dept)" class="text-gray-400 hover:text-blue-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Edit2 :size="14" /></button>
                  <button @click="deleteDept(dept.id)" class="text-gray-400 hover:text-red-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Trash2 :size="14" /></button>
                </td>
              </tr>

              <!-- New Group Form Row -->
              <tr v-if="showGroupFormFor === dept.id" class="bg-emerald-50">
                <td colspan="2" class="px-10 py-3">
                  <div class="flex items-center gap-3">
                    <input
                      v-model="newGroupForms[dept.id]"
                      type="text"
                      placeholder="グループ名を入力..."
                      @keydown.enter="addGroup(dept)"
                      @keydown.esc="showGroupFormFor = null"
                      class="flex-1 px-3 py-1.5 border border-emerald-300 rounded-md focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                      autofocus
                    />
                    <button
                      @click="addGroup(dept)"
                      :disabled="!newGroupForms[dept.id]?.trim() || isAddingGroup === dept.id"
                      class="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1 disabled:opacity-50"
                    >
                      <Loader2 v-if="isAddingGroup === dept.id" :size="12" class="animate-spin" />
                      <Check v-else :size="12" />
                      追加
                    </button>
                    <button @click="showGroupFormFor = null" class="text-gray-400 hover:text-gray-600 p-1"><X :size="14" /></button>
                  </div>
                </td>
              </tr>

              <!-- Group rows -->
              <tr v-for="group in dept.groups" :key="group.id" class="hover:bg-gray-100 transition-colors bg-gray-50/50">
                <td class="py-2.5 px-4 text-sm text-gray-700 pl-10">
                  <div class="flex items-center gap-2">
                    <div class="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0"></div>
                    <!-- Editing mode -->
                    <template v-if="editingGroupKey === `${dept.id}:${group.id}`">
                      <input
                        v-model="editingGroupName"
                        type="text"
                        @keydown.enter="saveGroup(dept, group)"
                        @keydown.esc="cancelEditGroup"
                        class="flex-1 px-2 py-1 border border-indigo-400 rounded text-sm focus:ring-2 focus:ring-indigo-500"
                        autofocus
                      />
                      <button @click="saveGroup(dept, group)" class="text-indigo-600 hover:text-indigo-800 p-1"><Check :size="14" /></button>
                      <button @click="cancelEditGroup" class="text-gray-400 hover:text-gray-600 p-1"><X :size="14" /></button>
                    </template>
                    <!-- Display mode -->
                    <span v-else>{{ group.name }}</span>
                  </div>
                </td>
                <td class="py-2.5 px-4 text-right space-x-2">
                  <button @click="startEditGroup(dept.id, group)" class="text-gray-400 hover:text-indigo-600 p-1"><Edit2 :size="14" /></button>
                  <button @click="deleteGroup(dept, group.id)" class="text-gray-400 hover:text-red-600 p-1"><Trash2 :size="14" /></button>
                </td>
              </tr>
            </template>

            <!-- Empty state -->
            <tr v-if="!isLoading && departments.length === 0">
              <td colspan="2" class="py-12 text-center text-gray-500 text-sm">
                部門が登録されていません。「新規部門を作成」ボタンから追加してください。
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Projects Tab (mock data, read-only) -->
    <div v-if="activeTab === 'projects'" class="space-y-4">
      <div class="flex justify-between items-center bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <p class="text-sm text-gray-600">プロジェクトを作成し、その「プロジェクトマネージャー (PM)」を指定します。</p>
        <button class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
          <Plus :size="16" />
          新規プロジェクトを作成
        </button>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-500">
              <th class="py-3 px-4 w-5/12">プロジェクト名</th>
              <th class="py-3 px-4 w-1/3">責任者 (PM / Leader)</th>
              <th class="py-3 px-4 text-center">ステータス</th>
              <th class="py-3 px-4 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <template v-for="proj in projects" :key="proj.id">
              <tr class="hover:bg-gray-50 transition-colors bg-white">
                <td class="py-3 px-4 font-bold text-gray-900 border-l-4 border-indigo-500 flex items-center gap-2">
                  <FolderKanban :size="16" class="text-indigo-500" />
                  {{ proj.name }}
                </td>
                <td class="py-3 px-4">
                  <div class="flex items-center gap-2">
                    <div class="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold shadow-sm">
                      {{ proj.pmName.charAt(0) }}
                    </div>
                    <span class="text-sm font-medium text-gray-800">{{ proj.pmName }} <span class="text-xs text-gray-500 font-normal border border-gray-200 rounded px-1 ml-1 bg-white">PM</span></span>
                  </div>
                </td>
                <td class="py-3 px-4 text-center">
                  <span v-if="proj.status === 'active'" class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                    進行中
                  </span>
                  <span v-else class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 border border-gray-200">
                    完了
                  </span>
                </td>
                <td class="py-3 px-4 text-right space-x-2">
                  <button class="text-gray-400 hover:text-indigo-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Edit2 :size="14" /></button>
                  <button class="text-gray-400 hover:text-red-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Trash2 :size="14" /></button>
                </td>
              </tr>
              <!-- Sub Projects -->
              <tr v-for="sub in proj.subProjects" :key="sub.id" class="hover:bg-gray-100 transition-colors bg-gray-50/50">
                <td class="py-2.5 px-4 text-sm text-gray-700 pl-10 flex items-center gap-2">
                  <div class="w-1.5 h-1.5 rounded-full bg-teal-400"></div>
                  {{ sub.name }}
                </td>
                <td class="py-2.5 px-4">
                  <div class="flex items-center gap-2">
                    <div class="w-5 h-5 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center text-[10px] font-bold">
                      {{ sub.subPmName.charAt(0) }}
                    </div>
                    <span class="text-sm text-gray-600">{{ sub.subPmName }} <span class="text-xs text-gray-400 font-normal ml-1">Sub-PM</span></span>
                  </div>
                </td>
                <td class="py-2.5 px-4 text-center">
                  <span v-if="sub.status === 'active'" class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium text-emerald-600">
                    進行中
                  </span>
                  <span v-else class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium text-gray-500">
                    完了
                  </span>
                </td>
                <td class="py-2.5 px-4 text-right space-x-2">
                  <button class="text-gray-400 hover:text-teal-600 p-1"><Edit2 :size="14" /></button>
                  <button class="text-gray-400 hover:text-red-600 p-1"><Trash2 :size="14" /></button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</template>
