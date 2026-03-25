/**
 * useDepartments.ts - Department/Group composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface DepartmentGroup {
  id: string;
  name: string;
}

export interface Department {
  id: string;
  name: string;
  groups: DepartmentGroup[];
}

export function useDepartments() {
  const departments = ref<Department[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchDepartments = async () => {
    isLoading.value = true;
    error.value = null;
    try {
      const data = await api.get<any[]>('/departments');
      departments.value = data.map((d: any) => ({
        id: d.id,
        name: d.name,
        groups: (d.groups || []).map((g: any) => ({ id: g.id, name: g.name })),
      }));
    } catch (e: any) {
      error.value = 'データの取得に失敗しました。';
    } finally {
      isLoading.value = false;
    }
  };

  const createDepartment = async (name: string): Promise<Department | null> => {
    try {
      const created = await api.post<any>('/departments', { name });
      const dept: Department = { id: created.id, name: created.name, groups: created.groups || [] };
      departments.value.push(dept);
      return dept;
    } catch (e: any) {
      error.value = '部門の作成に失敗しました。';
      return null;
    }
  };

  const updateDepartment = async (id: string, name: string): Promise<boolean> => {
    try {
      await api.patch(`/departments/${id}`, { name });
      const dept = departments.value.find(d => d.id === id);
      if (dept) dept.name = name;
      return true;
    } catch (e: any) {
      error.value = '部門名の更新に失敗しました。';
      return false;
    }
  };

  const deleteDepartment = async (id: string): Promise<boolean> => {
    try {
      await api.delete(`/departments/${id}`);
      departments.value = departments.value.filter(d => d.id !== id);
      return true;
    } catch (e: any) {
      error.value = '部門の削除に失敗しました。';
      return false;
    }
  };

  const createGroup = async (deptId: string, name: string): Promise<boolean> => {
    try {
      const updated = await api.post<any>(`/departments/${deptId}/groups`, { name });
      const dept = departments.value.find(d => d.id === deptId);
      if (dept) dept.groups = updated.groups || [];
      return true;
    } catch (e: any) {
      error.value = 'グループの追加に失敗しました。';
      return false;
    }
  };

  const updateGroup = async (deptId: string, groupId: string, name: string): Promise<boolean> => {
    try {
      await api.patch(`/departments/${deptId}/groups/${groupId}`, { name });
      const dept = departments.value.find(d => d.id === deptId);
      if (dept) {
        const group = dept.groups.find(g => g.id === groupId);
        if (group) group.name = name;
      }
      return true;
    } catch (e: any) {
      error.value = 'グループ名の更新に失敗しました。';
      return false;
    }
  };

  const deleteGroup = async (deptId: string, groupId: string): Promise<boolean> => {
    try {
      await api.delete(`/departments/${deptId}/groups/${groupId}`);
      const dept = departments.value.find(d => d.id === deptId);
      if (dept) dept.groups = dept.groups.filter(g => g.id !== groupId);
      return true;
    } catch (e: any) {
      error.value = 'グループの削除に失敗しました。';
      return false;
    }
  };

  return {
    departments,
    isLoading,
    error,
    fetchDepartments,
    createDepartment,
    updateDepartment,
    deleteDepartment,
    createGroup,
    updateGroup,
    deleteGroup,
  };
}
