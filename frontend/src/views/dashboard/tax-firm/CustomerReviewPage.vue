<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/lib/api'
import { useAuth } from '@/composables/useAuth'

const route = useRoute()
const { currentUser } = useAuth()
const corporateId = route.params.id as string

// ── 期間フィルター ─────────────────────────────────────────────────────────────
const now = new Date()
const defaultPeriod = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
const selectedPeriod = ref(defaultPeriod)

const periodOptions = computed(() => {
  const opts: string[] = []
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    opts.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }
  return opts
})

// ── サマリー ──────────────────────────────────────────────────────────────────
const summary = ref<any>(null)
const isSummaryLoading = ref(true)

const fetchSummary = async () => {
  isSummaryLoading.value = true
  try {
    summary.value = await api.get(`/tax-firm/reviews/${corporateId}/summary`)
  } catch {
    summary.value = null
  } finally {
    isSummaryLoading.value = false
  }
}

// ── 書類一覧 ──────────────────────────────────────────────────────────────────
const documents = ref<any[]>([])
const isDocsLoading = ref(true)

const fetchDocuments = async () => {
  isDocsLoading.value = true
  try {
    documents.value = await api.get(
      `/tax-firm/reviews/${corporateId}/documents?fiscal_period=${selectedPeriod.value}`
    )
  } catch {
    documents.value = []
  } finally {
    isDocsLoading.value = false
  }
}

watch(selectedPeriod, fetchDocuments)

// ── コメント ──────────────────────────────────────────────────────────────────
const comments = ref<any[]>([])
const isCommentsLoading = ref(true)
const newComment = ref('')
const newCommentPeriod = ref(defaultPeriod)
const isPostingComment = ref(false)
const commentError = ref<string | null>(null)
const editingId = ref<string | null>(null)
const editingText = ref('')
const isSavingEdit = ref(false)

const myUid = computed(() => currentUser.value?.uid ?? '')

const fetchComments = async () => {
  isCommentsLoading.value = true
  try {
    comments.value = await api.get(`/tax-firm/reviews/${corporateId}/comments`)
  } catch {
    comments.value = []
  } finally {
    isCommentsLoading.value = false
  }
}

const postComment = async () => {
  if (!newComment.value.trim()) return
  commentError.value = null
  isPostingComment.value = true
  try {
    await api.post(`/tax-firm/reviews/${corporateId}/comments`, {
      comment: newComment.value.trim(),
      fiscal_period: newCommentPeriod.value,
    })
    newComment.value = ''
    await fetchComments()
  } catch {
    commentError.value = 'コメントの投稿に失敗しました'
  } finally {
    isPostingComment.value = false
  }
}

const startEdit = (comment: any) => {
  editingId.value = comment.id
  editingText.value = comment.comment
}

const cancelEdit = () => {
  editingId.value = null
  editingText.value = ''
}

const saveEdit = async (commentId: string) => {
  if (!editingText.value.trim()) return
  isSavingEdit.value = true
  try {
    await api.put(`/tax-firm/reviews/${corporateId}/comments/${commentId}`, {
      comment: editingText.value.trim(),
    })
    editingId.value = null
    await fetchComments()
  } catch {
    commentError.value = 'コメントの更新に失敗しました'
  } finally {
    isSavingEdit.value = false
  }
}

const deleteComment = async (commentId: string) => {
  if (!confirm('このコメントを削除しますか？')) return
  try {
    await api.delete(`/tax-firm/reviews/${corporateId}/comments/${commentId}`)
    await fetchComments()
  } catch {
    commentError.value = 'コメントの削除に失敗しました'
  }
}

const formatDate = (val: string | null) => {
  if (!val) return '—'
  return new Date(val).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

const docTypeLabel = (type: string) => type === 'receipt' ? '領収書' : '請求書'

onMounted(async () => {
  await Promise.all([fetchSummary(), fetchDocuments(), fetchComments()])
})
</script>

<template>
  <div class="p-8 max-w-5xl">
    <!-- ヘッダー -->
    <div class="mb-6">
      <button @click="$router.back()" class="text-sm text-slate-500 hover:text-slate-700 mb-2 flex items-center gap-1">
        ← 顧客一覧に戻る
      </button>
      <h1 class="text-2xl font-bold text-slate-900">
        {{ summary?.corporate_name || '読込中...' }}
        <span class="text-base font-normal text-slate-400 ml-2">レビュー</span>
      </h1>
    </div>

    <!-- ① サマリーカード -->
    <div v-if="!isSummaryLoading && summary" class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-white rounded-xl border border-slate-200 p-5 text-center shadow-sm">
        <p class="text-xs text-slate-500 mb-1">未承認書類</p>
        <p class="text-3xl font-bold text-amber-600">
          {{ (summary.pending_receipts_count ?? 0) + (summary.pending_invoices_count ?? 0) }}
          <span class="text-base font-normal text-slate-400">件</span>
        </p>
      </div>
      <div class="bg-white rounded-xl border border-slate-200 p-5 text-center shadow-sm">
        <p class="text-xs text-slate-500 mb-1">未消込</p>
        <p class="text-3xl font-bold text-indigo-600">
          {{ summary.unreconciled_count ?? 0 }}
          <span class="text-base font-normal text-slate-400">件</span>
        </p>
      </div>
      <div class="bg-white rounded-xl border border-slate-200 p-5 text-center shadow-sm">
        <p class="text-xs text-slate-500 mb-1">アラート</p>
        <p class="text-3xl font-bold text-red-500">
          {{ summary.recent_alerts?.length ?? 0 }}
          <span class="text-base font-normal text-slate-400">件</span>
        </p>
      </div>
    </div>

    <!-- ② 期間フィルター -->
    <div class="flex items-center gap-3 mb-4">
      <label class="text-sm font-medium text-slate-700">対象期間：</label>
      <select
        v-model="selectedPeriod"
        class="px-3 py-1.5 text-sm border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <option v-for="p in periodOptions" :key="p" :value="p">{{ p }}</option>
      </select>
    </div>

    <!-- ③ 書類一覧 -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden mb-6">
      <div class="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
        <h2 class="text-base font-bold text-slate-800">承認済み書類一覧</h2>
        <span class="text-xs text-slate-400">{{ selectedPeriod }}</span>
      </div>

      <div v-if="isDocsLoading" class="p-6 text-slate-400 text-sm">読み込み中...</div>
      <div v-else-if="documents.length === 0" class="p-6 text-slate-400 text-sm text-center">
        対象期間に承認済み書類はありません
      </div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 border-b border-slate-200">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">種別</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">日付</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">金額</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">取引先</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">ステータス</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="doc in documents" :key="doc.id" class="hover:bg-slate-50 transition-colors">
              <td class="px-4 py-3">
                <span :class="[
                  'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                  doc.type === 'receipt' ? 'bg-blue-50 text-blue-700' : 'bg-purple-50 text-purple-700'
                ]">
                  {{ docTypeLabel(doc.type) }}
                </span>
              </td>
              <td class="px-4 py-3 text-slate-600">{{ doc.date || '—' }}</td>
              <td class="px-4 py-3 text-slate-900 text-right font-medium">
                ¥{{ (doc.amount ?? 0).toLocaleString() }}
              </td>
              <td class="px-4 py-3 text-slate-600">{{ doc.vendor || '—' }}</td>
              <td class="px-4 py-3">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700">
                  承認済み
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ④ コメントセクション -->
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <h2 class="text-base font-bold text-slate-800 mb-4">税理士コメント</h2>

      <!-- コメント一覧 -->
      <div v-if="isCommentsLoading" class="text-slate-400 text-sm mb-4">読み込み中...</div>
      <div v-else-if="comments.length === 0" class="text-slate-400 text-sm mb-4">
        まだコメントがありません
      </div>
      <div v-else class="space-y-3 mb-6">
        <div
          v-for="c in comments"
          :key="c.id"
          class="border border-slate-200 rounded-lg p-4"
        >
          <div v-if="editingId === c.id">
            <textarea
              v-model="editingText"
              rows="3"
              class="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 mb-2"
            />
            <div class="flex gap-2">
              <button
                @click="saveEdit(c.id)"
                :disabled="isSavingEdit"
                class="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-lg transition-colors disabled:bg-slate-300"
              >
                {{ isSavingEdit ? '保存中...' : '保存' }}
              </button>
              <button @click="cancelEdit" class="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700">
                キャンセル
              </button>
            </div>
          </div>
          <div v-else>
            <div class="flex items-start justify-between gap-2">
              <p class="text-sm text-slate-800 whitespace-pre-wrap flex-1">{{ c.comment }}</p>
              <div v-if="c.created_by === myUid" class="flex gap-2 shrink-0">
                <button
                  @click="startEdit(c)"
                  class="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  編集
                </button>
                <button
                  @click="deleteComment(c.id)"
                  class="text-xs text-red-500 hover:text-red-700 font-medium"
                >
                  削除
                </button>
              </div>
            </div>
            <div class="mt-2 flex items-center gap-2 text-xs text-slate-400">
              <span class="bg-slate-100 px-2 py-0.5 rounded font-mono">{{ c.fiscal_period }}</span>
              <span>{{ formatDate(c.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- コメント入力フォーム -->
      <div class="border-t border-slate-200 pt-4">
        <h3 class="text-sm font-semibold text-slate-700 mb-3">コメントを投稿する</h3>
        <div class="flex items-center gap-2 mb-2">
          <label class="text-xs text-slate-500">対象期間：</label>
          <select
            v-model="newCommentPeriod"
            class="px-2 py-1 text-xs border border-slate-300 rounded outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option v-for="p in periodOptions" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <textarea
          v-model="newComment"
          rows="3"
          placeholder="コメントを入力してください..."
          class="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 mb-2"
        />
        <div v-if="commentError" class="text-red-600 text-xs mb-2">{{ commentError }}</div>
        <button
          @click="postComment"
          :disabled="isPostingComment || !newComment.trim()"
          class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-300 text-white font-bold text-sm rounded-lg transition-colors"
        >
          {{ isPostingComment ? '投稿中...' : 'コメントを投稿する' }}
        </button>
      </div>
    </section>
  </div>
</template>
