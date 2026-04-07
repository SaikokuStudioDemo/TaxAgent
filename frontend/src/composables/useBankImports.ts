import { ref } from 'vue'
import { api } from '@/lib/api'

export interface BankImportFile {
  id: string
  source_type: 'bank' | 'card'
  account_name: string
  file_name: string
  row_count: number
  status: 'completed' | 'error'
  imported_at: string
}

export function useBankImports() {
  const importFiles = ref<BankImportFile[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const fetchImportFiles = async () => {
    isLoading.value = true
    error.value = null
    try {
      importFiles.value = await api.get<BankImportFile[]>('/bank-import-files')
    } catch (e: any) {
      error.value = e.message
    } finally {
      isLoading.value = false
    }
  }

  const deleteImportFile = async (fileId: string): Promise<boolean> => {
    try {
      await api.delete(`/bank-import-files/${fileId}`)
      await fetchImportFiles()
      return true
    } catch {
      return false
    }
  }

  return {
    importFiles,
    isLoading,
    error,
    fetchImportFiles,
    deleteImportFile,
  }
}
