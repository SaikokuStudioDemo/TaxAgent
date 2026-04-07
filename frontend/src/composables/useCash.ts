import { ref } from 'vue'
import { api } from '@/lib/api'

export interface CashAccount {
  id: string
  name: string
  initial_balance: number
  current_balance: number
  created_at: string
}

export interface CashTransaction {
  id: string
  cash_account_id: string
  transaction_date: string
  amount: number
  direction: 'income' | 'expense'
  description: string
  category: string
  fiscal_period: string
  source: 'manual' | 'bank_import'
  status: 'unmatched' | 'matched' | 'transferred'
  linked_bank_transaction_id?: string
  linked_document_id?: string
  linked_document_type?: 'receipt' | 'invoice'
  note?: string
  created_at: string
}

export interface CashMatch {
  id: string
  cash_transaction_id: string
  transaction_ids: string[]
  document_ids: string[]
  no_document_reason?: string
  manual_category?: string
  manual_description?: string
  manual_amount?: number
  matched_by: string
  fiscal_period: string
  matched_at: string
}

export interface CashSummary {
  total_income: number
  total_expense: number
  unmatched_count: number
  unmatched_amount: number
  matched_count: number
  current_balance: number
}

export function useCash() {
  const accounts = ref<CashAccount[]>([])
  const transactions = ref<CashTransaction[]>([])
  const cashMatches = ref<CashMatch[]>([])
  const cashSummary = ref<CashSummary | null>(null)
  const isLoading = ref(false)

  const fetchAccounts = async () => {
    isLoading.value = true
    try {
      accounts.value = await api.get<CashAccount[]>('/cash-accounts')
    } finally {
      isLoading.value = false
    }
  }

  const createAccount = async (payload: { name: string; initial_balance: number }) => {
    try {
      await api.post('/cash-accounts', payload)
      await fetchAccounts()
      return true
    } catch {
      return false
    }
  }

  const updateAccount = async (id: string, payload: Partial<CashAccount>) => {
    try {
      await api.patch(`/cash-accounts/${id}`, payload)
      await fetchAccounts()
      return true
    } catch {
      return false
    }
  }

  const fetchTransactions = async (params: {
    cash_account_id?: string
    fiscal_period?: string
    status?: string
  } = {}) => {
    isLoading.value = true
    try {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v)) as Record<string, string>
      ).toString()
      transactions.value = await api.get<CashTransaction[]>(
        `/cash-transactions${query ? '?' + query : ''}`
      )
    } finally {
      isLoading.value = false
    }
  }

  const createTransaction = async (
    payload: Omit<CashTransaction, 'id' | 'status' | 'created_at'>
  ) => {
    try {
      await api.post('/cash-transactions', payload)
      return true
    } catch {
      return false
    }
  }

  const updateTransaction = async (id: string, payload: Partial<CashTransaction>) => {
    try {
      await api.patch(`/cash-transactions/${id}`, payload)
      return true
    } catch {
      return false
    }
  }

  const deleteTransaction = async (id: string) => {
    try {
      await api.delete(`/cash-transactions/${id}`)
      return true
    } catch {
      return false
    }
  }

  const fetchCashMatches = async (params: { fiscal_period?: string } = {}) => {
    try {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v)) as Record<string, string>
      ).toString()
      cashMatches.value = await api.get<CashMatch[]>(
        `/matches?match_type=cash${query ? '&' + query : ''}`
      )
    } catch {
      cashMatches.value = []
    }
  }

  const createCashMatch = async (payload: {
    cash_transaction_id: string
    document_ids: string[]
    transaction_ids: string[]
    no_document_reason?: string
    manual_category?: string
    manual_description?: string
    manual_amount?: number
    fiscal_period: string
  }) => {
    try {
      await api.post('/cash-matches', { ...payload, match_type: 'cash' })
      return true
    } catch {
      return false
    }
  }

  const deleteCashMatch = async (matchId: string) => {
    try {
      await api.delete(`/cash-matches/${matchId}`)
      return true
    } catch {
      return false
    }
  }

  const fetchCashSummary = async (params: { fiscal_period?: string } = {}) => {
    try {
      const query = new URLSearchParams(
        Object.fromEntries(Object.entries(params).filter(([, v]) => v)) as Record<string, string>
      ).toString()
      cashSummary.value = await api.get<CashSummary>(
        `/cash-summary${query ? '?' + query : ''}`
      )
    } catch {
      cashSummary.value = null
    }
  }

  return {
    accounts,
    transactions,
    cashMatches,
    cashSummary,
    isLoading,
    fetchAccounts,
    createAccount,
    updateAccount,
    fetchTransactions,
    createTransaction,
    updateTransaction,
    deleteTransaction,
    fetchCashMatches,
    createCashMatch,
    deleteCashMatch,
    fetchCashSummary,
  }
}
