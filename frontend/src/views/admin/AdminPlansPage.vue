<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Pencil, X, Plus, Trash2 } from 'lucide-vue-next'
import { api } from '@/lib/api'
import { formatCurrency } from '@/lib/utils/formatters'

const plans = ref<any[]>([])
const isLoading = ref(true)
const isSaving = ref(false)
const error = ref<string | null>(null)
const successMsg = ref<string | null>(null)

const editingPlan = ref<any | null>(null)
const showModal = ref(false)

const fetchPlans = async () => {
  isLoading.value = true
  error.value = null
  try {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
    const res = await fetch(`${apiUrl}/system-settings/plans`)
    plans.value = await res.json()
  } catch {
    error.value = 'プランの取得に失敗しました'
  } finally {
    isLoading.value = false
  }
}

const openEdit = (plan: any) => {
  editingPlan.value = JSON.parse(JSON.stringify(plan))
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
  editingPlan.value = null
}

const addFeature = () => {
  editingPlan.value.features.push('')
}

const removeFeature = (idx: number) => {
  editingPlan.value.features.splice(idx, 1)
}

const savePlans = async () => {
  if (!editingPlan.value) return
  isSaving.value = false
  error.value = null

  const updated = plans.value.map((p) =>
    p.id === editingPlan.value.id ? { ...editingPlan.value } : p
  )

  isSaving.value = true
  try {
    await api.put('/system-settings/plans', { plans: updated })
    plans.value = updated
    successMsg.value = 'プランを保存しました'
    closeModal()
    setTimeout(() => { successMsg.value = null }, 3000)
  } catch (e: any) {
    error.value = e.message || '保存に失敗しました'
  } finally {
    isSaving.value = false
  }
}

const displayLimit = (val: number | undefined) =>
  val === undefined ? '—' : val === -1 ? '無制限' : String(val)

onMounted(fetchPlans)
</script>

<template>
  <div class="p-8">
    <div class="mb-8 flex justify-between items-start">
      <div>
        <h1 class="text-2xl font-bold text-slate-900 mb-1">プラン管理</h1>
        <p class="text-slate-500 text-sm">税理士法人向けプランの価格・機能を管理します。</p>
      </div>
    </div>

    <div v-if="successMsg" class="mb-4 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg px-4 py-3 text-sm">
      {{ successMsg }}
    </div>
    <div v-if="error" class="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
      {{ error }}
    </div>

    <div v-if="isLoading" class="text-slate-400 text-sm">読み込み中...</div>

    <div v-else class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-slate-50 border-b border-slate-200">
          <tr>
            <th class="text-left px-6 py-3 font-semibold text-slate-600">プラン名</th>
            <th class="text-right px-6 py-3 font-semibold text-slate-600">月額（税抜）</th>
            <th class="text-right px-6 py-3 font-semibold text-slate-600">配下法人数</th>
            <th class="text-right px-6 py-3 font-semibold text-slate-600">ユーザー数/社</th>
            <th class="text-center px-6 py-3 font-semibold text-slate-600">有効</th>
            <th class="px-6 py-3"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="plan in plans"
            :key="plan.id"
            class="border-b border-slate-100 hover:bg-slate-50/50 transition-colors"
          >
            <td class="px-6 py-4 font-medium text-slate-900">{{ plan.name }}</td>
            <td class="px-6 py-4 text-right text-slate-700">{{ formatCurrency(plan.price) }}</td>
            <td class="px-6 py-4 text-right text-slate-700">{{ displayLimit(plan.max_client_corporates) }}</td>
            <td class="px-6 py-4 text-right text-slate-700">{{ displayLimit(plan.max_users_per_corporate) }}</td>
            <td class="px-6 py-4 text-center">
              <span
                class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold"
                :class="plan.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'"
              >
                {{ plan.is_active ? '有効' : '無効' }}
              </span>
            </td>
            <td class="px-6 py-4 text-right">
              <button
                @click="openEdit(plan)"
                class="flex items-center gap-1 text-sky-600 hover:text-sky-800 font-medium text-sm transition-colors ml-auto"
              >
                <Pencil :size="14" /> 編集
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Edit Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
          <div class="flex justify-between items-center px-6 py-4 border-b border-slate-100">
            <h2 class="text-lg font-bold text-slate-900">プラン編集</h2>
            <button @click="closeModal" class="text-slate-400 hover:text-slate-700 transition-colors">
              <X :size="20" />
            </button>
          </div>

          <div v-if="editingPlan" class="px-6 py-5 space-y-4">
            <div>
              <label class="block text-sm font-medium text-slate-700 mb-1">プラン名</label>
              <input v-model="editingPlan.name" type="text" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
            </div>

            <div>
              <label class="block text-sm font-medium text-slate-700 mb-1">月額（税抜・円）</label>
              <input v-model.number="editingPlan.price" type="number" min="0" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">配下法人数（-1=無制限）</label>
                <input v-model.number="editingPlan.max_client_corporates" type="number" min="-1" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
              </div>
              <div>
                <label class="block text-sm font-medium text-slate-700 mb-1">ユーザー数/社（-1=無制限）</label>
                <input v-model.number="editingPlan.max_users_per_corporate" type="number" min="-1" class="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
              </div>
            </div>

            <div>
              <div class="flex justify-between items-center mb-2">
                <label class="block text-sm font-medium text-slate-700">機能一覧</label>
                <button @click="addFeature" class="flex items-center gap-1 text-xs text-sky-600 hover:text-sky-800 font-medium">
                  <Plus :size="12" /> 追加
                </button>
              </div>
              <div class="space-y-2">
                <div v-for="(_, idx) in editingPlan.features" :key="idx" class="flex items-center gap-2">
                  <input
                    v-model="editingPlan.features[idx]"
                    type="text"
                    class="flex-1 border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                  <button @click="removeFeature(idx)" class="text-red-400 hover:text-red-600 transition-colors">
                    <Trash2 :size="14" />
                  </button>
                </div>
              </div>
            </div>

            <div class="flex items-center gap-3">
              <label class="text-sm font-medium text-slate-700">有効</label>
              <button
                @click="editingPlan.is_active = !editingPlan.is_active"
                class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors"
                :class="editingPlan.is_active ? 'bg-emerald-500' : 'bg-slate-300'"
              >
                <span
                  class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform"
                  :class="editingPlan.is_active ? 'translate-x-6' : 'translate-x-1'"
                />
              </button>
            </div>
          </div>

          <div class="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
            <button @click="closeModal" class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 font-medium transition-colors">
              キャンセル
            </button>
            <button
              @click="savePlans"
              :disabled="isSaving"
              class="px-5 py-2 text-sm bg-sky-500 hover:bg-sky-400 disabled:bg-slate-300 text-white font-bold rounded-lg transition-colors"
            >
              {{ isSaving ? '保存中...' : '保存する' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
