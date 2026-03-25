/**
 * useInvoices.ts - Invoice composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface LineItem {
    description: string;
    category: string;
    amount: number;
    tax_rate: number;
}

export interface Invoice {
    id: string;
    document_type: 'issued' | 'received';
    invoice_number: string;
    client_id?: string;
    client_name: string;
    recipient_email: string;
    issue_date: string;
    due_date: string;
    subtotal: number;
    tax_amount: number;
    total_amount: number;
    approval_status: string;
    delivery_status?: 'unsent' | 'sent';
    reconciliation_status?: 'unreconciled' | 'reconciled';
    current_step: number;
    approval_rule_id: string | null;
    is_temporary_approval_needed: boolean;
    is_auto_send_enabled: boolean;
    fiscal_period: string;
    line_items: LineItem[];
    created_by: string;
    created_at: string;
    paid_at?: string;
    attachments?: string[];
    approval_history?: any[];
}

export function useInvoices() {
    const invoices = ref<Invoice[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchInvoices = async (params?: {
        document_type?: string;
        approval_status?: string;
        fiscal_period?: string;
    }) => {
        isLoading.value = true;
        error.value = null;
        try {
            const query = new URLSearchParams();
            if (params?.document_type) query.append('document_type', params.document_type);
            if (params?.approval_status) query.append('approval_status', params.approval_status);
            if (params?.fiscal_period) query.append('fiscal_period', params.fiscal_period);
            const qs = query.toString();
            invoices.value = await api.get<Invoice[]>(`/invoices${qs ? '?' + qs : ''}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const getInvoice = async (id: string): Promise<Invoice | null> => {
        try {
            return await api.get<Invoice>(`/invoices/${id}`);
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const createInvoice = async (data: Partial<Invoice>) => {
        try {
            const created = await api.post<Invoice>('/invoices', data);
            invoices.value.unshift(created);
            return created;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const updateInvoice = async (id: string, data: Partial<Invoice>) => {
        try {
            const updated = await api.patch<Invoice>(`/invoices/${id}`, data);
            const idx = invoices.value.findIndex(i => i.id === id);
            if (idx !== -1) invoices.value[idx] = updated;
            return updated;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const deleteInvoice = async (id: string) => {
        try {
            await api.delete(`/invoices/${id}`);
            invoices.value = invoices.value.filter(i => i.id !== id);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    const sendInvoice = async (id: string) => {
        try {
            return await api.post(`/invoices/${id}/send`, {});
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const bulkAction = async (ids: string[], action: 'delete' | 'send') => {
        try {
            await api.post('/invoices/bulk-action', { ids, action });
            if (action === 'delete') {
                invoices.value = invoices.value.filter(i => !ids.includes(i.id));
            } else if (action === 'send') {
                invoices.value.forEach(i => {
                    if (ids.includes(i.id)) i.delivery_status = 'sent';
                });
            }
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    return {
        invoices,
        isLoading,
        error,
        fetchInvoices,
        getInvoice,
        createInvoice,
        updateInvoice,
        deleteInvoice,
        sendInvoice,
        bulkAction,
    };
}
