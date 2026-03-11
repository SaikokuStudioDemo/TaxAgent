<script setup lang="ts">
import { ref } from 'vue';
import { Plus, Users, FolderKanban, Edit2, Trash2, Building2 } from 'lucide-vue-next';

interface Group {
  id: string;
  name: string;
  groupLeaderName: string;
  memberCount: number;
}

interface Department {
  id: string;
  name: string;
  managerName: string;
  memberCount: number;
  groups?: Group[];
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

const departments = ref<Department[]>([
  { id: 'dept-1', name: '経営陣', managerName: '山田 太郎 (CEO)', memberCount: 3 },
  { 
    id: 'dept-2', 
    name: '営業部', 
    managerName: '佐藤 花子', 
    memberCount: 12,
    groups: [
      { id: 'grp-2-1', name: '営業1課', groupLeaderName: '田中 健一', memberCount: 5 },
      { id: 'grp-2-2', name: '営業2課', groupLeaderName: '伊藤 美咲', memberCount: 6 }
    ]
  },
  { 
    id: 'dept-3', 
    name: 'システム開発部', 
    managerName: '鈴木 一郎', 
    memberCount: 8,
    groups: [
      { id: 'grp-3-1', name: 'フロントエンドチーム', groupLeaderName: '渡辺 翔太', memberCount: 4 },
      { id: 'grp-3-2', name: 'バックエンドチーム', groupLeaderName: '小林 さくら', memberCount: 3 }
    ]
  }
]);

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
        <p class="text-sm text-gray-600">部門を作成し、その部門の「直属の部門長」を指定します。</p>
        <button class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors">
          <Plus :size="16" />
          新規部門を作成
        </button>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-500">
              <th class="py-3 px-4 w-5/12">部門・チーム名</th>
              <th class="py-3 px-4 w-1/3">責任者 (Manager / Leader)</th>
              <th class="py-3 px-4 text-center">所属人数</th>
              <th class="py-3 px-4 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <template v-for="dept in departments" :key="dept.id">
              <tr class="hover:bg-gray-50 transition-colors bg-white">
                <td class="py-3 px-4 font-bold text-gray-900 border-l-4 border-blue-500 flex items-center gap-2">
                  <Building2 :size="16" class="text-blue-500" />
                  {{ dept.name }}
                </td>
                <td class="py-3 px-4">
                  <div class="flex items-center gap-2">
                    <div class="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold shadow-sm">
                      {{ dept.managerName.charAt(0) }}
                    </div>
                    <span class="text-sm font-medium text-gray-800">{{ dept.managerName }} <span class="text-xs text-gray-500 font-normal border border-gray-200 rounded px-1 ml-1 bg-white">部長</span></span>
                  </div>
                </td>
                <td class="py-3 px-4 text-center text-sm font-medium text-gray-700">{{ dept.memberCount }} 名</td>
                <td class="py-3 px-4 text-right space-x-2">
                  <button class="text-gray-400 hover:text-blue-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Edit2 :size="14" /></button>
                  <button class="text-gray-400 hover:text-red-600 p-1 bg-white rounded shadow-sm border border-gray-100"><Trash2 :size="14" /></button>
                </td>
              </tr>
              <!-- Sub Groups -->
              <tr v-for="group in dept.groups" :key="group.id" class="hover:bg-gray-100 transition-colors bg-gray-50/50">
                <td class="py-2.5 px-4 text-sm text-gray-700 pl-10 flex items-center gap-2">
                  <div class="w-1.5 h-1.5 rounded-full bg-indigo-400"></div>
                  {{ group.name }}
                </td>
                <td class="py-2.5 px-4">
                  <div class="flex items-center gap-2">
                    <div class="w-5 h-5 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center text-[10px] font-bold">
                      {{ group.groupLeaderName.charAt(0) }}
                    </div>
                    <span class="text-sm text-gray-600">{{ group.groupLeaderName }} <span class="text-xs text-gray-400 font-normal ml-1">係長</span></span>
                  </div>
                </td>
                <td class="py-2.5 px-4 text-center text-sm text-gray-500">{{ group.memberCount }} 名</td>
                <td class="py-2.5 px-4 text-right space-x-2">
                  <button class="text-gray-400 hover:text-indigo-600 p-1"><Edit2 :size="14" /></button>
                  <button class="text-gray-400 hover:text-red-600 p-1"><Trash2 :size="14" /></button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Projects Tab -->
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
