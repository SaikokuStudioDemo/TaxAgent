/**
 * useCompanyProfiles.ts - Company Profiles (自社情報) composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface CompanyProfile {
  id: string;
  profile_name: string;
  company_name: string;
  phone?: string;
  address?: string;
  registration_number?: string;
  is_default: boolean;
}

export function useCompanyProfiles() {
  const profiles = ref<CompanyProfile[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const fetchProfiles = async () => {
    isLoading.value = true;
    error.value = null;
    try {
      profiles.value = await api.get<CompanyProfile[]>('/company-profiles');
    } catch (e: any) {
      error.value = e.message;
    } finally {
      isLoading.value = false;
    }
  };

  const createProfile = async (data: Omit<CompanyProfile, 'id'>) => {
    try {
      const created = await api.post<CompanyProfile>('/company-profiles', data);
      profiles.value.push(created);
      return created;
    } catch (e: any) {
      error.value = e.message;
      return null;
    }
  };

  const updateProfile = async (id: string, data: Partial<CompanyProfile>) => {
    try {
      const updated = await api.patch<CompanyProfile>(`/company-profiles/${id}`, data);
      const idx = profiles.value.findIndex(p => p.id === id);
      if (idx !== -1) profiles.value[idx] = updated;
      return updated;
    } catch (e: any) {
      error.value = e.message;
      return null;
    }
  };

  const deleteProfile = async (id: string) => {
    try {
      await api.delete(`/company-profiles/${id}`);
      profiles.value = profiles.value.filter(p => p.id !== id);
      return true;
    } catch (e: any) {
      error.value = e.message;
      return false;
    }
  };

  const formatProfileForTextarea = (profile: CompanyProfile) => {
    const lines = [profile.company_name];
    if (profile.address) lines.push(profile.address);
    if (profile.phone) lines.push(`TEL: ${profile.phone}`);
    if (profile.registration_number) lines.push(`登録番号: ${profile.registration_number}`);
    return lines.join('\n');
  };

  return {
    profiles,
    isLoading,
    error,
    fetchProfiles,
    createProfile,
    updateProfile,
    deleteProfile,
    formatProfileForTextarea,
  };
}
