/**
 * useEmployees.ts - Employee list composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface Employee {
  id: string;
  name: string;
  email?: string;
  role?: string;
  firebase_uid?: string;
}

export function useEmployees() {
  const employees = ref<Employee[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchEmployees = async () => {
    isLoading.value = true;
    error.value = null;
    try {
      const data = await api.get<any[]>('/users/employees');
      employees.value = data.map((e: any) => ({
        id: e.id ?? e._id,
        name: e.name,
        email: e.email,
        role: e.role,
        firebase_uid: e.firebase_uid,
      }));
    } catch (e: any) {
      error.value = '従業員リストの取得に失敗しました。';
    } finally {
      isLoading.value = false;
    }
  };

  return { employees, isLoading, error, fetchEmployees };
}
