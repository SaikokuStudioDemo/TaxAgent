/**
 * useClients.ts - Clients (取引先) composable backed by real API
 */
import { ref } from 'vue';
import { api } from '@/lib/api';

export interface BankDisplayName {
    pattern: string;
    source: 'manual' | 'ai';
    confidence: number;
    added_at?: string;
}

export interface Client {
    id: string;
    name: string;
    client_category?: 'company' | 'individual';
    registration_number?: string;
    email?: string;
    phone?: string;
    address?: string;
    payment_terms?: string;
    department?: string;
    contact_person?: string;
    postal_code?: string;
    internal_notes?: string;
    bank_display_names?: BankDisplayName[];
    created_at: string;
}

export function useClients() {
    const clients = ref<Client[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchClients = async () => {
        isLoading.value = true;
        error.value = null;
        try {
            clients.value = await api.get<Client[]>('/clients');
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const getClient = async (id: string): Promise<Client | null> => {
        try {
            return await api.get<Client>(`/clients/${id}`);
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const createClient = async (data: Omit<Client, 'id' | 'created_at'>) => {
        try {
            const created = await api.post<Client>('/clients', data);
            clients.value.push(created);
            return created;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const updateClient = async (id: string, data: Partial<Client>) => {
        try {
            const updated = await api.patch<Client>(`/clients/${id}`, data);
            const idx = clients.value.findIndex(c => c.id === id);
            if (idx !== -1) clients.value[idx] = updated;
            return updated;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const deleteClient = async (id: string) => {
        try {
            await api.delete(`/clients/${id}`);
            clients.value = clients.value.filter(c => c.id !== id);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    const addBankDisplayName = async (clientId: string, pattern: string, source: 'manual' | 'ai' = 'manual') => {
        try {
            const updated = await api.post<Client>(`/clients/${clientId}/bank-display-names`, { pattern, source, confidence: 1.0 });
            const idx = clients.value.findIndex(c => c.id === clientId);
            if (idx !== -1) clients.value[idx] = updated;
            return updated;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const removeBankDisplayName = async (clientId: string, pattern: string) => {
        try {
            const encoded = encodeURIComponent(pattern);
            const updated = await api.delete<Client>(`/clients/${clientId}/bank-display-names/${encoded}`);
            const idx = clients.value.findIndex(c => c.id === clientId);
            if (idx !== -1) clients.value[idx] = updated;
            return updated;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    return {
        clients,
        isLoading,
        error,
        fetchClients,
        getClient,
        createClient,
        updateClient,
        deleteClient,
        addBankDisplayName,
        removeBankDisplayName,
    };
}
