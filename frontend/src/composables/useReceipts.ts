/**
 * useReceipts.ts - Receipt composable backed by real API
 */
import { ref } from 'vue';
import { api, buildQueryString } from '@/lib/api';
import type { ApprovalHistory } from '@/lib/types/approvalTypes';

export interface Receipt {
    id: string;
    date: string;
    amount: number;
    tax_rate: number;
    payee: string;
    category: string;
    payment_method: string;
    receipt_type?: 'expense' | 'payment_proof';
    approval_status: string;
    reconciliation_status?: 'unreconciled' | 'reconciled';
    approval_rule_id: string | null;
    current_step: number;
    fiscal_period: string;
    submitted_by: string;
    created_at: string;
    attachments?: string[];
    approval_history?: ApprovalHistory[];
    extra_approval_steps?: { roleId: string; roleName: string; approverName?: string }[];
    // Optional fields populated by API
    submitter_name?: string;
    department?: string;
    group_name?: string;
    project_name?: string;
    image_url?: string;
    memo?: string;
    project_id?: string;
    document_type?: string;
    line_items?: any[];
}

export function useReceipts() {
    const receipts = ref<Receipt[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchReceipts = async (params?: {
        approval_status?: string;
        fiscal_period?: string;
        submitted_by?: string;
        receipt_type?: string;
        reconciliation_status?: string;
    }) => {
        isLoading.value = true;
        error.value = null;
        try {
            receipts.value = await api.get<Receipt[]>(`/receipts${buildQueryString(params)}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const pendingForMe = ref<Receipt[]>([]);

    const fetchPendingForMe = async () => {
        isLoading.value = true;
        error.value = null;
        try {
            pendingForMe.value = await api.get<Receipt[]>('/approvals/pending-for-me?document_type=receipt');
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const getReceipt = async (id: string): Promise<Receipt | null> => {
        try {
            return await api.get<Receipt>(`/receipts/${id}`);
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const createReceipt = async (data: Partial<Receipt>) => {
        try {
            const created = await api.post<Receipt>('/receipts', data);
            receipts.value.unshift(created);
            return created;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const updateReceipt = async (id: string, data: Partial<Receipt>) => {
        try {
            const updated = await api.patch<Receipt>(`/receipts/${id}`, data);
            const idx = receipts.value.findIndex(r => r.id === id);
            if (idx !== -1) receipts.value[idx] = updated;
            return updated;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const deleteReceipt = async (id: string) => {
        try {
            await api.delete(`/receipts/${id}`);
            receipts.value = receipts.value.filter(r => r.id !== id);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    return {
        receipts,
        pendingForMe,
        isLoading,
        error,
        fetchReceipts,
        fetchPendingForMe,
        getReceipt,
        createReceipt,
        updateReceipt,
        deleteReceipt,
    };
}
