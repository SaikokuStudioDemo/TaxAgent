/**
 * useReceipts.ts - Receipt composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface Receipt {
    id: string;
    date: string;
    amount: number;
    tax_rate: number;
    payee: string;
    category: string;
    payment_method: string;
    status: string;
    review_status: string;
    approval_rule_id: string | null;
    current_step: number;
    fiscal_period: string;
    submitted_by: string;
    created_at: string;
    attachments?: string[];
    approval_history?: ApprovalEvent[];
}

export interface ApprovalEvent {
    id: string;
    step: number;
    approver_id: string;
    action: string;
    comment?: string;
    timestamp: string;
}

export function useReceipts() {
    const receipts = ref<Receipt[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchReceipts = async (params?: {
        review_status?: string;
        status?: string;
        fiscal_period?: string;
        submitted_by?: string;
    }) => {
        isLoading.value = true;
        error.value = null;
        try {
            const query = new URLSearchParams();
            if (params?.review_status) query.append('review_status', params.review_status);
            if (params?.status) query.append('status', params.status);
            if (params?.fiscal_period) query.append('fiscal_period', params.fiscal_period);
            if (params?.submitted_by) query.append('submitted_by', params.submitted_by);
            const qs = query.toString();
            receipts.value = await api.get<Receipt[]>(`/receipts${qs ? '?' + qs : ''}`);
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

    const submitApprovalAction = async (
        receiptId: string,
        action: 'approved' | 'rejected' | 'returned',
        step: number,
        comment?: string,
        addedSteps?: any[]
    ) => {
        try {
            return await api.post('/approvals/actions', {
                document_type: 'receipt',
                document_id: receiptId,
                action,
                step,
                approver_id: 'current_user',
                comment: comment ?? null,
                added_steps: addedSteps
            });
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const approveReceipt = async (
        id: string,
        action: 'approve' | 'reject',
        comment?: string,
    ) => {
        const apiAction = action === 'approve' ? 'approved' : 'rejected';
        return submitApprovalAction(id, apiAction, 1, comment);
    };

    return {
        receipts,
        isLoading,
        error,
        fetchReceipts,
        getReceipt,
        createReceipt,
        updateReceipt,
        deleteReceipt,
        submitApprovalAction,
        approveReceipt,
    };
}
