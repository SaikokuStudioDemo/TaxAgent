import { ref } from 'vue';
import { api } from '@/lib/api';

export interface TaxRates {
  standard: number;
  reduced: number;
  exempt: number;
}

const DEFAULT_TAX_RATES: TaxRates = { standard: 10, reduced: 8, exempt: 0 };

export function useSystemSettings() {
  const taxRates = ref<TaxRates>({ ...DEFAULT_TAX_RATES });

  const fetchTaxRates = async (): Promise<void> => {
    try {
      const res = await api.get<TaxRates>('/system-settings/tax-rates');
      if (res) taxRates.value = res;
    } catch {
      // フォールバックはデフォルト値を維持
    }
  };

  return { taxRates, fetchTaxRates };
}
