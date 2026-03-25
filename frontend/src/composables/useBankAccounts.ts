import { ref } from 'vue';
import { api } from '@/lib/api';

export interface BankAccount {
  id: string;
  corporate_id: string;
  profile_id: string;
  bank_name: string;
  branch_name: string;
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

  const fetchBankAccounts = async (profileId?: string) => {
    isLoading.value = true;
    error.value = '';
    try {
      const path = profileId ? `/bank-accounts?profile_id=${profileId}` : '/bank-accounts';
      accounts.value = await api.get<BankAccount[]>(path);
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

  return { accounts, isLoading, error, fetchBankAccounts, createBankAccount, updateBankAccount, deleteBankAccount, setDefaultBankAccount };
}
