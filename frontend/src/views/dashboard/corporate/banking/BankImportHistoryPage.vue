<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Trash2, FileSpreadsheet, CreditCard, Banknote } from 'lucide-vue-next'
import { useBankImports } from '@/composables/useBankImports'

const { importFiles, isLoading, error, fetchImportFiles, deleteImportFile } = useBankImports()
const isDeleting = ref<string | null>(null)

onMounted(fetchImportFiles)

const handleDelete = async (fileId: string, fileName: string) => {
  if (!confirm(`「${fileName}」のデータを全件削除します。消込済みのデータも解除されます。よろしいですか？`)) return
  isDeleting.value = fileId
  await deleteImportFile(fileId)
  isDeleting.value = null
}

const formatDate = (iso: string) =>
  new Date(iso).toLocaleString('ja-JP', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
</script>

<template>
  <div class="space-y-6 h-full flex flex-col">
    <!-- Header -->
    <div class="shrink-0">
      <h1 class="text-2xl font-bold tracking-tight text-gray-900 border-b-2 border-primary pb-2 inline-block">インポート履歴</h1>
      <p class="text-sm text-gray-500 mt-2">取り込んだ銀行・カードデータの履歴です。ファイル単位で削除できます。</p>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="flex-1 flex items-center justify-center text-gray-400 text-sm">
      読み込み中...
    </div>

    <!-- Error -->
    <div v-else-if="error"
      class="flex-1 flex flex-col items-center justify-center bg-red-50 rounded-xl border border-red-200 py-12 gap-3">
      <p class="text-sm font-medium text-red-700">データの取得に失敗しました</p>
      <p class="text-xs text-red-500 max-w-sm text-center">{{ error }}</p>
      <button @click="fetchImportFiles"
        class="mt-2 text-sm px-4 py-2 bg-white border border-red-200 text-red-600 rounded-lg hover:bg-red-50 transition-colors">
        再試行
      </button>
    </div>

    <!-- Empty -->
    <div v-else-if="importFiles.length === 0"
      class="flex-1 flex flex-col items-center justify-center bg-white rounded-xl border border-gray-200 shadow-sm py-20">
      <FileSpreadsheet class="h-16 w-16 text-gray-200 mb-4" />
      <p class="text-base font-medium text-gray-500">インポート履歴がありません</p>
    </div>

    <!-- Table -->
    <div v-else class="flex-1 overflow-y-auto min-h-0">
      <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 border-b border-gray-200">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">インポート日時</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">ファイル名</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">種別</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">口座名</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">件数</th>
              <th class="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="f in importFiles" :key="f.id" class="hover:bg-gray-50 transition-colors">
              <td class="px-4 py-3 text-gray-600 whitespace-nowrap">{{ formatDate(f.imported_at) }}</td>
              <td class="px-4 py-3 text-gray-800 font-medium">
                <div class="flex items-center gap-2">
                  <FileSpreadsheet class="h-4 w-4 text-gray-400 shrink-0" />
                  <span class="truncate max-w-[200px]" :title="f.file_name">{{ f.file_name }}</span>
                </div>
              </td>
              <td class="px-4 py-3">
                <span v-if="f.source_type === 'bank'"
                  class="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                  <Banknote class="h-3 w-3" /> 銀行
                </span>
                <span v-else
                  class="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">
                  <CreditCard class="h-3 w-3" /> カード
                </span>
              </td>
              <td class="px-4 py-3 text-gray-600">{{ f.account_name }}</td>
              <td class="px-4 py-3 text-right text-gray-700 font-medium">{{ f.row_count.toLocaleString() }}件</td>
              <td class="px-4 py-3 text-center">
                <button
                  @click="handleDelete(f.id, f.file_name)"
                  :disabled="isDeleting === f.id"
                  class="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                  <Trash2 class="h-3.5 w-3.5" />
                  {{ isDeleting === f.id ? '削除中...' : '削除' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
