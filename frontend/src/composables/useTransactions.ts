/**
 * useTransactions.ts - Transactions (Bank/Card) and matching composable
 */
import { ref } from 'vue';
import { api, buildQueryString } from '@/lib/api';

export interface Transaction {
    id: string;
    source_type: 'bank' | 'card';
    account_name: string;
    transaction_date: string;
    description: string;
    normalized_name?: string;
    amount: number;
    transaction_type: 'credit' | 'debit';
    status: 'unmatched' | 'matched';
    fiscal_period: string;
    imported_at: string;
}

export interface Match {
    id: string;
    match_type: 'receipt' | 'invoice';
    transaction_ids: string[];
    document_ids: string[];
    total_transaction_amount: number;
    total_document_amount: number;
    difference: number;
    difference_direction: string;
    difference_treatment?: string;
    auto_resolved: boolean;
    matched_by: string;
    journal_entries: any[];
    fiscal_period: string;
    matched_at: string;
    score?: number;
    score_breakdown?: { amount: number; date: number; name: number };
    auto_suggested: boolean;
    user_action: string;
}

export interface ApiCandidatePair {
    transaction: any;
    document: any;
    score: number;
    score_breakdown: { amount: number; date: number; name: number };
}

export function useTransactions() {
    const transactions = ref<Transaction[]>([]);
    const matches = ref<Match[]>([]);
    const isLoading = ref(false);
    const error = ref<string | null>(null);

    const fetchTransactions = async (params?: {
        source_type?: string;
        status?: string;
        fiscal_period?: string;
    }) => {
        isLoading.value = true;
        error.value = null;
        try {
            transactions.value = await api.get<Transaction[]>(`/transactions${buildQueryString(params)}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const importTransactions = async (data: {
        source_type: 'bank' | 'card';
        account_name: string;
        file_name?: string;
        transactions: Partial<Transaction>[];
    }) => {
        try {
            return await api.post('/transactions', data);
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const fetchMatches = async (params?: {
        match_type?: string;
        fiscal_period?: string;
    }) => {
        isLoading.value = true;
        error.value = null;
        try {
            const query = new URLSearchParams();
            if (params?.match_type) query.append('match_type', params.match_type);
            if (params?.fiscal_period) query.append('fiscal_period', params.fiscal_period);
            const qs = query.toString();
            matches.value = await api.get<Match[]>(`/matches${qs ? '?' + qs : ''}`);
        } catch (e: any) {
            error.value = e.message;
        } finally {
            isLoading.value = false;
        }
    };

    const createMatch = async (data: {
        match_type: 'receipt' | 'invoice';
        transaction_ids: string[];
        document_ids: string[];
        fiscal_period: string;
        matched_by?: string;
        difference_treatment?: string;
        auto_suggested?: boolean;
    }) => {
        try {
            const created = await api.post<Match>('/matches', {
                ...data,
                matched_by: data.matched_by || 'manual',
                auto_suggested: data.auto_suggested ?? false,
            });
            matches.value.unshift(created);
            return created;
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const patchMatch = async (id: string, data: Record<string, any>) => {
        try {
            return await api.patch<Match>(`/matches/${id}`, data);
        } catch (e: any) {
            error.value = e.message;
            return null;
        }
    };

    const deleteMatch = async (id: string) => {
        try {
            await api.delete(`/matches/${id}`);
            matches.value = matches.value.filter(m => m.id !== id);
            return true;
        } catch (e: any) {
            error.value = e.message;
            return false;
        }
    };

    const fetchCandidates = async (params?: {
        match_type?: string;
        fiscal_period?: string;
    }): Promise<ApiCandidatePair[]> => {
        try {
            const qs = buildQueryString(params);
            return await api.get<ApiCandidatePair[]>(`/matches/candidates${qs}`);
        } catch (e: any) {
            error.value = e.message;
            return [];
        }
    };

    return {
        transactions,
        matches,
        isLoading,
        error,
        fetchTransactions,
        importTransactions,
        fetchMatches,
        createMatch,
        patchMatch,
        deleteMatch,
        fetchCandidates,
    };
}
