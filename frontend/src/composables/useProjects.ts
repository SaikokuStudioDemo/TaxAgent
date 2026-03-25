/**
 * useProjects.ts - Project composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface ProjectApprover {
  user_id: string;
  name: string;
  order: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  approvers: ProjectApprover[];
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export function useProjects() {
  const projects = ref<Project[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchProjects = async () => {
    isLoading.value = true;
    error.value = null;
    try {
      const data = await api.get<any[]>('/projects');
      projects.value = data.map((p: any) => ({
        id: p.id,
        name: p.name,
        description: p.description ?? '',
        approvers: (p.approvers || []).sort((a: any, b: any) => a.order - b.order),
        is_active: p.is_active,
        created_at: p.created_at,
        updated_at: p.updated_at,
      }));
    } catch (e: any) {
      error.value = 'プロジェクトの取得に失敗しました。';
    } finally {
      isLoading.value = false;
    }
  };

  const createProject = async (data: { name: string; description?: string | null; approvers: ProjectApprover[] }): Promise<Project | null> => {
    try {
      const created = await api.post<any>('/projects', data);
      const proj: Project = {
        id: created.id,
        name: created.name,
        description: created.description ?? '',
        approvers: created.approvers || [],
        is_active: created.is_active,
      };
      projects.value.unshift(proj);
      return proj;
    } catch (e: any) {
      error.value = 'プロジェクトの作成に失敗しました。';
      return null;
    }
  };

  const updateProject = async (id: string, data: Partial<{ name: string; description: string | null; approvers: ProjectApprover[] }>): Promise<Project | null> => {
    try {
      const updated = await api.patch<any>(`/projects/${id}`, data);
      const proj: Project = {
        id: updated.id,
        name: updated.name,
        description: updated.description ?? '',
        approvers: updated.approvers || [],
        is_active: updated.is_active,
      };
      const idx = projects.value.findIndex(p => p.id === id);
      if (idx !== -1) projects.value[idx] = proj;
      return proj;
    } catch (e: any) {
      error.value = 'プロジェクトの更新に失敗しました。';
      return null;
    }
  };

  const deleteProject = async (id: string): Promise<boolean> => {
    try {
      await api.delete(`/projects/${id}`);
      projects.value = projects.value.filter(p => p.id !== id);
      return true;
    } catch (e: any) {
      error.value = 'プロジェクトの削除に失敗しました。';
      return false;
    }
  };

  return {
    projects,
    isLoading,
    error,
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
  };
}
