import { ref } from 'vue';
import { api, API_BASE } from '@/lib/api';

export interface BankAccount {
  id: string;
  corporate_id: string;
  owner_type: 'corporate' | 'client';
  profile_id?: string;
  client_id?: string;
  bank_name: string;
  branch_name: string;
  bank_code?: string;
  branch_code?: string;
  account_type: 'ordinary' | 'checking';
  account_number: string;
  account_holder: string;
  is_default: boolean;
  is_active: boolean;
}

export function useBankAccounts() {
  const accounts = ref<BankAccount[]>([]);
  const isLoading = ref(false);
  const error = ref('');

  const fetchBankAccounts = async (params: { profileId?: string; clientId?: string } = {}) => {
    isLoading.value = true;
    error.value = '';
    try {
      const query = params.profileId
        ? `?profile_id=${params.profileId}`
        : params.clientId
        ? `?client_id=${params.clientId}`
        : '';
      accounts.value = await api.get<BankAccount[]>(`/bank-accounts${query}`);
    } catch (e: any) {
      error.value = e.message;
    } finally {
      isLoading.value = false;
    }
  };

  const createBankAccount = async (data: Omit<BankAccount, 'id' | 'corporate_id' | 'is_active'>) => {
    const result = await api.post<BankAccount>('/bank-accounts', data);
    accounts.value.push(result);
    return result;
  };

  const updateBankAccount = async (id: string, data: Partial<BankAccount>) => {
    const result = await api.patch<BankAccount>(`/bank-accounts/${id}`, data);
    const idx = accounts.value.findIndex(a => a.id === id);
    if (idx !== -1) accounts.value[idx] = result;
    return result;
  };

  const deleteBankAccount = async (id: string) => {
    await api.delete(`/bank-accounts/${id}`);
    accounts.value = accounts.value.filter(a => a.id !== id);
  };

  const setDefaultBankAccount = async (id: string) => {
    await api.patch(`/bank-accounts/${id}/set-default`, {});
    accounts.value = accounts.value.map(a => ({ ...a, is_default: a.id === id }));
  };

  const lookupBank = async (bankCode: string): Promise<{ bank_code: string; bank_name: string; kana: string } | null> => {
    try {
      return await api.get(`/bank-accounts/zengin/banks/${bankCode}`);
    } catch {
      return null;
    }
  };

  const lookupBranch = async (bankCode: string, branchCode: string): Promise<{ branch_code: string; branch_name: string; kana: string } | null> => {
    try {
      return await api.get(`/bank-accounts/zengin/banks/${bankCode}/branches/${branchCode}`);
    } catch {
      return null;
    }
  };

  const searchBanks = async (q: string): Promise<{ code: string; name: string; kana: string }[]> => {
    if (!q) return [];
    try {
      return await api.get(`/bank-accounts/zengin/banks/search?q=${encodeURIComponent(q)}`);
    } catch {
      return [];
    }
  };

  const searchBranches = async (bankCode: string, q: string): Promise<{ code: string; name: string; kana: string }[]> => {
    if (!bankCode || !q) return [];
    try {
      return await api.get(`/bank-accounts/zengin/banks/${bankCode}/branches/search?q=${encodeURIComponent(q)}`);
    } catch {
      return [];
    }
  };

  return {
    accounts, isLoading, error,
    fetchBankAccounts, createBankAccount, updateBankAccount, deleteBankAccount, setDefaultBankAccount,
    lookupBank, lookupBranch, searchBanks, searchBranches,
  };
}
