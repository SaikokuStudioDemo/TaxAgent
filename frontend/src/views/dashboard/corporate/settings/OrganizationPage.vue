<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Users, FolderKanban, Edit2, Trash2, Building2, Check, X, Loader2, UserPlus } from 'lucide-vue-next';
import { useDepartments, type Department } from '@/composables/useDepartments';
import { useProjects, type Project } from '@/composables/useProjects';
import { useEmployees } from '@/composables/useEmployees';

const activeTab = ref<'departments' | 'projects'>('departments');

// ─── Departments ───
const {
  departments, isLoading, error: deptError,
  fetchDepartments, createDepartment, updateDepartment, deleteDepartment,
  createGroup, updateGroup, deleteGroup,
} = useDepartments();

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

onMounted(() => {
  fetchDepartments();
  fetchProjects();
  fetchEmployees();
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
  const ok = await updateDepartment(dept.id, name);
  if (ok) cancelEditDept();
  else errorMsg.value = deptError.value || '部門名の更新に失敗しました。';
};

const deleteDept = async (deptId: string) => {
  if (!confirm('この部門を削除してもよろしいですか？')) return;
  const ok = await deleteDepartment(deptId);
  if (!ok) errorMsg.value = deptError.value || '部門の削除に失敗しました。';
};

const addDepartment = async () => {
  const name = newDeptName.value.trim();
  if (!name) return;
  isAddingDept.value = true;
  const created = await createDepartment(name);
  isAddingDept.value = false;
  if (created) {
    newDeptName.value = '';
    showNewDeptForm.value = false;
  } else {
    errorMsg.value = deptError.value || '部門の作成に失敗しました。';
  }
};

// --- Group CRUD ---

const startEditGroup = (deptId: string, group: { id: string; name: string }) => {
  editingGroupKey.value = `${deptId}:${group.id}`;
  editingGroupName.value = group.name;
  editingDeptId.value = null;
};

const cancelEditGroup = () => {
  editingGroupKey.value = null;
  editingGroupName.value = '';
};

const saveGroup = async (dept: Department, group: { id: string; name: string }) => {
  const name = editingGroupName.value.trim();
  if (!name) return;
  const ok = await updateGroup(dept.id, group.id, name);
  if (ok) cancelEditGroup();
  else errorMsg.value = deptError.value || 'グループ名の更新に失敗しました。';
};

const handleDeleteGroup = async (dept: Department, groupId: string) => {
  if (!confirm('このグループを削除してもよろしいですか？')) return;
  const ok = await deleteGroup(dept.id, groupId);
  if (!ok) errorMsg.value = deptError.value || 'グループの削除に失敗しました。';
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
  const ok = await createGroup(dept.id, name);
  isAddingGroup.value = null;
  if (ok) {
    newGroupForms.value[dept.id] = '';
    showGroupFormFor.value = null;
  } else {
    errorMsg.value = deptError.value || 'グループの追加に失敗しました。';
  }
};

// ─── Projects ───
const {
  projects, isLoading: projLoading, error: projError,
  fetchProjects, createProject, updateProject, deleteProject,
} = useProjects();

const { employees, fetchEmployees } = useEmployees();

// Project modal state
const showProjModal = ref(false);
const editingProject = ref<Partial<Project> | null>(null);
const projForm = ref({ name: '', description: '' });
const projMembers = ref<{ user_id: string; name: string }[]>([]);
const isSavingProj = ref(false);

const openNewProjModal = () => {
  editingProject.value = null;
  projForm.value = { name: '', description: '' };
  projMembers.value = [];
  showProjModal.value = true;
};

const openEditProjModal = (proj: Project) => {
  editingProject.value = proj;
  projForm.value = { name: proj.name, description: proj.description || '' };
  projMembers.value = [...proj.members];
  showProjModal.value = true;
};

const closeProjModal = () => {
  showProjModal.value = false;
  editingProject.value = null;
};

const addMemberToProjForm = () => {
  projMembers.value.push({ user_id: '', name: '' });
};

const removeMemberFromProjForm = (index: number) => {
  projMembers.value.splice(index, 1);
};

const onMemberEmployeeChange = (index: number, userId: string) => {
  const emp = employees.value.find(e => e.id === userId);
  if (emp) {
    projMembers.value[index].user_id = userId;
    projMembers.value[index].name = emp.name;
  }
};

const saveProjModal = async () => {
  const name = projForm.value.name.trim();
  if (!name) return;
  isSavingProj.value = true;
  const payload = {
    name,
    description: projForm.value.description.trim() || null,
    members: projMembers.value.filter(m => m.user_id),
  };
  let ok = false;
  if (editingProject.value?.id) {
    ok = !!(await updateProject(editingProject.value.id, payload));
  } else {
    ok = !!(await createProject(payload));
  }
  isSavingProj.value = false;
  if (ok) closeProjModal();
  else errorMsg.value = projError.value || 'プロジェクトの保存に失敗しました。';
};

const handleDeleteProj = async (id: string, name: string) => {
  if (!confirm(`「${name}」を削除しますか？`)) return;
  const ok = await deleteProject(id);
  if (!ok) errorMsg.value = projError.value || 'プロジェクトの削除に失敗しました。';
};
</script>

<template>
  <div class="max-w-6xl mx-auto p-4 sm:p-8">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-2">
        <Building2 :size="24" class="text-blue-600" />
        部門・プロジェクト管理
      </h1>
      <p class="text-gray-500 mt-2">部門・プロジェクト編成を管理します。承認フローは「承認ルール」画面でプロジェクトごとに設定します。</p>
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
                  <button @click="handleDeleteGroup(dept, group.id)" class="text-gray-400 hover:text-red-600 p-1"><Trash2 :size="14" /></button>
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

    <!-- Projects Tab -->
    <div v-if="activeTab === 'projects'" class="space-y-4">
      <div class="flex justify-between items-center bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <p class="text-sm text-gray-600">プロジェクトを作成し、関わる責任者を登録します。承認フローは「承認ルール」画面でプロジェクトごとに別途設定します。</p>
        <button @click="openNewProjModal" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
          <Plus :size="16" />
          新規プロジェクトを作成
        </button>
      </div>

      <div v-if="projLoading" class="flex items-center justify-center py-12 text-indigo-500 gap-3">
        <Loader2 class="animate-spin" :size="32" />
        <span class="font-medium">読み込み中...</span>
      </div>

      <div v-else class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-500">
              <th class="py-3 px-4 w-5/12">プロジェクト名</th>
              <th class="py-3 px-4">責任者</th>
              <th class="py-3 px-4 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="proj in projects" :key="proj.id" class="hover:bg-gray-50 transition-colors">
              <td class="py-3 px-4 border-l-4 border-indigo-500">
                <div class="flex items-center gap-2">
                  <FolderKanban :size="16" class="text-indigo-500 shrink-0" />
                  <div>
                    <div class="font-bold text-gray-900">{{ proj.name }}</div>
                    <div v-if="proj.description" class="text-xs text-gray-400 mt-0.5">{{ proj.description }}</div>
                  </div>
                </div>
              </td>
              <td class="py-3 px-4">
                <div v-if="proj.members.length === 0" class="text-xs text-gray-400">責任者未設定</div>
                <div v-else class="flex flex-wrap gap-1">
                  <span v-for="m in proj.members" :key="m.user_id" class="inline-flex items-center bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded text-xs font-medium">
                    {{ m.name }}
                  </span>
                </div>
              </td>
              <td class="py-3 px-4 text-right space-x-2">
                <button @click="openEditProjModal(proj)" class="text-gray-400 hover:text-indigo-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Edit2 :size="14" /></button>
                <button @click="handleDeleteProj(proj.id, proj.name)" class="text-gray-400 hover:text-red-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Trash2 :size="14" /></button>
              </td>
            </tr>
            <tr v-if="!projLoading && projects.length === 0">
              <td colspan="3" class="py-12 text-center text-gray-500 text-sm">
                プロジェクトが登録されていません。「新規プロジェクトを作成」ボタンから追加してください。
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Project Modal -->
    <Teleport to="body">
      <div v-if="showProjModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-900/50" @click="closeProjModal"></div>
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg relative z-10 flex flex-col max-h-[85vh]">
          <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0">
            <h2 class="font-bold text-slate-800">{{ editingProject?.id ? 'プロジェクト編集' : '新規プロジェクト作成' }}</h2>
            <button @click="closeProjModal" class="p-1 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-100"><X :size="18" /></button>
          </div>
          <div class="p-6 overflow-y-auto flex-1 space-y-5">
            <!-- Name -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">プロジェクト名 <span class="text-red-500">*</span></label>
              <input v-model="projForm.name" type="text" placeholder="プロジェクト名を入力" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none" />
            </div>
            <!-- Description -->
            <div>
              <label class="block text-sm font-semibold text-gray-700 mb-1">説明（任意）</label>
              <input v-model="projForm.description" type="text" placeholder="プロジェクトの概要" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none" />
            </div>
            <!-- Members -->
            <div>
              <div class="flex items-center justify-between mb-2">
                <div>
                  <label class="block text-sm font-semibold text-gray-700">責任者</label>
                  <p class="text-xs text-gray-400 mt-0.5">承認フローは「承認ルール」画面で設定します</p>
                </div>
                <button @click="addMemberToProjForm" class="text-indigo-600 hover:text-indigo-800 text-xs font-medium flex items-center gap-1">
                  <UserPlus :size="14" /> 責任者を追加
                </button>
              </div>
              <div class="space-y-2">
                <div v-for="(member, idx) in projMembers" :key="idx" class="flex items-center gap-2 bg-indigo-50/50 border border-indigo-100 rounded-lg p-2">
                  <select
                    :value="member.user_id"
                    @change="onMemberEmployeeChange(idx, ($event.target as HTMLSelectElement).value)"
                    class="flex-1 bg-white border border-indigo-200 rounded px-2 py-1.5 text-sm focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">従業員を選択...</option>
                    <option v-for="emp in employees" :key="emp.id" :value="emp.id">{{ emp.name }}</option>
                  </select>
                  <button @click="removeMemberFromProjForm(idx)" class="text-gray-400 hover:text-red-500 p-1"><X :size="14" /></button>
                </div>
                <div v-if="projMembers.length === 0" class="text-xs text-gray-400 text-center py-3 border border-dashed border-gray-200 rounded-lg">
                  責任者が設定されていません
                </div>
              </div>
            </div>
          </div>
          <div class="px-6 py-4 border-t border-slate-100 flex justify-end gap-3 shrink-0">
            <button @click="closeProjModal" class="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">キャンセル</button>
            <button @click="saveProjModal" :disabled="!projForm.name.trim() || isSavingProj" class="px-6 py-2 text-sm font-bold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
              <Loader2 v-if="isSavingProj" :size="14" class="animate-spin" />
              保存する
            </button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>
