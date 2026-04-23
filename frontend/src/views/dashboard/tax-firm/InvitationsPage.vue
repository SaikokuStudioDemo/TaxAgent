<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/lib/api'

const baseUrl = import.meta.env.VITE_APP_BASE_URL || 'http://localhost:5173'

// ── 発行フォーム ──────────────────────────────────────────────────────────────
const invitedEmail = ref('')
const isCreating = ref(false)
const createError = ref<string | null>(null)
const newToken = ref<string | null>(null)
const newUrl = ref<string | null>(null)
const copyNewLabel = ref('コピー')

// ── 一覧 ──────────────────────────────────────────────────────────────────────
const invitations = ref<any[]>([])
const isLoading = ref(true)
const listError = ref<string | null>(null)
const copyLabels = ref<Record<string, string>>({})

const buildUrl = (token: string) => `${baseUrl}/register/corporate?token=${token}`

const getDisplayStatus = (item: any) => {
  if (item.status === 'accepted') return { label: '使用済み', cls: 'text-gray-500 bg-gray-100' }
  if (item.status === 'pending' && new Date(item.expires_at) <= new Date()) {
    return { label: '期限切れ', cls: 'text-red-600 bg-red-50' }
  }
  return { label: '未使用', cls: 'text-blue-600 bg-blue-50' }
}

const isPending = (item: any) =>
  item.status === 'pending' && new Date(item.expires_at) > new Date()

const fetchInvitations = async () => {
  isLoading.value = true
  listError.value = null
  try {
    invitations.value = await api.get('/invitations')
  } catch {
    listError.value = '招待リンク一覧の取得に失敗しました'
  } finally {
    isLoading.value = false
  }
}

const createInvitation = async () => {
  isCreating.value = true
  createError.value = null
  newToken.value = null
  newUrl.value = null
  try {
    const body: Record<string, string> = {}
    if (invitedEmail.value.trim()) body.invited_email = invitedEmail.value.trim()
    const data = await api.post('/invitations', body)
    newToken.value = data.token
    newUrl.value = buildUrl(data.token)
    invitedEmail.value = ''
    await fetchInvitations()
  } catch {
    createError.value = '招待リンクの発行に失敗しました'
  } finally {
    isCreating.value = false
  }
}

const copyNewUrl = async () => {
  if (!newUrl.value) return
  await navigator.clipboard.writeText(newUrl.value)
  copyNewLabel.value = 'コピーしました！'
  setTimeout(() => { copyNewLabel.value = 'コピー' }, 2000)
}

const copyRowUrl = async (id: string, token: string) => {
  await navigator.clipboard.writeText(buildUrl(token))
  copyLabels.value = { ...copyLabels.value, [id]: 'コピーしました！' }
  setTimeout(() => {
    copyLabels.value = { ...copyLabels.value, [id]: 'URLをコピー' }
  }, 2000)
}

const formatDate = (val: string | null) => {
  if (!val) return '—'
  return new Date(val).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  })
}

onMounted(fetchInvitations)
</script>

<template>
  <div class="p-8 max-w-4xl">
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-slate-900 mb-1">招待リンク管理</h1>
      <p class="text-slate-500 text-sm">顧客法人への招待リンクを発行・管理します。</p>
    </div>

    <!-- 発行フォーム -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
      <h2 class="text-base font-bold text-slate-800 mb-4">招待リンクを発行する</h2>

      <div class="flex items-end gap-3">
        <div class="flex-1">
          <label class="block text-sm font-medium text-slate-700 mb-1">
            招待先メールアドレス
            <span class="text-slate-400 font-normal ml-1">（任意）</span>
          </label>
          <input
            v-model="invitedEmail"
            type="email"
            placeholder="client@example.com"
            class="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <button
          @click="createInvitation"
          :disabled="isCreating"
          class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-300 text-white font-bold text-sm rounded-lg transition-colors whitespace-nowrap"
        >
          {{ isCreating ? '発行中...' : '招待リンクを発行する' }}
        </button>
      </div>

      <div v-if="createError" class="mt-3 text-red-600 text-sm">{{ createError }}</div>

      <!-- 発行直後の表示 -->
      <div v-if="newUrl" class="mt-4 bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-3">
        <p class="text-sm font-medium text-indigo-800 mb-2">招待URLが発行されました</p>
        <div class="flex items-center gap-2">
          <code class="flex-1 text-xs bg-white border border-indigo-200 rounded px-3 py-2 text-slate-700 break-all">{{ newUrl }}</code>
          <button
            @click="copyNewUrl"
            class="shrink-0 px-3 py-2 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-lg transition-colors"
          >
            {{ copyNewLabel }}
          </button>
        </div>
      </div>
    </section>

    <!-- 一覧テーブル -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-200">
        <h2 class="text-base font-bold text-slate-800">発行済み招待リンク一覧</h2>
      </div>

      <div v-if="isLoading" class="p-6 text-slate-400 text-sm">読み込み中...</div>
      <div v-else-if="listError" class="p-6 text-red-600 text-sm">{{ listError }}</div>
      <div v-else-if="invitations.length === 0" class="p-6 text-slate-400 text-sm text-center">
        まだ招待リンクが発行されていません
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 border-b border-slate-200">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">招待先メール</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">ステータス</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">有効期限</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">発行日時</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="inv in invitations" :key="inv.id" class="hover:bg-slate-50 transition-colors">
              <td class="px-4 py-3 text-slate-700">
                {{ inv.invited_email || '招待先未指定' }}
              </td>
              <td class="px-4 py-3">
                <span
                  :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', getDisplayStatus(inv).cls]"
                >
                  {{ getDisplayStatus(inv).label }}
                </span>
              </td>
              <td class="px-4 py-3 text-slate-600">{{ formatDate(inv.expires_at) }}</td>
              <td class="px-4 py-3 text-slate-600">{{ formatDate(inv.created_at) }}</td>
              <td class="px-4 py-3">
                <button
                  v-if="isPending(inv)"
                  @click="copyRowUrl(inv.id, inv.token)"
                  class="px-3 py-1.5 text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-lg transition-colors"
                >
                  {{ copyLabels[inv.id] || 'URLをコピー' }}
                </button>
                <span v-else class="text-slate-300 text-xs">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
