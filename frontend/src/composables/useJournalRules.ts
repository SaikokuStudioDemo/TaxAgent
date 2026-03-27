/**
 * useJournalRules.ts - Journal rules composable backed by real API
 */
import { useGenericRules } from './useGenericRules';

export interface JournalRule {
    id: string;
    name: string;
    keyword: string;
    target_field: string;
    account_subject: string;
    tax_division: string;
    is_active: boolean;
    created_at: string;
}

export function useJournalRules() {
    return useGenericRules<JournalRule>('/journal-rules');
}
