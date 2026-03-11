/**
 * useApprovalRules.ts - Approval rules composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface ApprovalCondition {
    field: string;
    operator: string;
    value: number;
}

export interface ApprovalStep {
    step: number;
    role: string;
    required: boolean;
}

export interface ApprovalRule {
    id: string;
    name: string;
    applies_to: string[];
    conditions: ApprovalCondition[];
    steps: ApprovalStep[];
    active: boolean;
    created_at: string;
}

export function useApprovalRules() {
    const rules = ref<ApprovalRule[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchRules = async (applies_to?: string) => {
        isLoading.value = true;
        error.value = null;
        try {
            const qs = applies_to ? `?applies_to=${applies_to}` : '';
            rules.value = await api.get<ApprovalRule[]>(`/approvals/rules${qs}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const createRule = async (data: Omit<ApprovalRule, 'id' | 'created_at'>) => {
        try {
            const created = await api.post<ApprovalRule>('/approvals/rules', data);
            rules.value.unshift(created);
            return created;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const updateRule = async (id: string, data: Partial<ApprovalRule>) => {
        try {
            const updated = await api.patch<ApprovalRule>(`/approvals/rules/${id}`, data);
            const idx = rules.value.findIndex(r => r.id === id);
            if (idx !== -1) rules.value[idx] = updated;
            return updated;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const deleteRule = async (id: string) => {
        try {
            await api.delete(`/approvals/rules/${id}`);
            rules.value = rules.value.filter(r => r.id !== id);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    return {
        rules,
        isLoading,
        error,
        fetchRules,
        createRule,
        updateRule,
        deleteRule,
    };
}
