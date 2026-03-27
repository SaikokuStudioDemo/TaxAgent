/**
 * useMatchingRules.ts - Matching rules composable backed by real API
 */
import { useGenericRules } from './useGenericRules';

export interface MatchingRule {
    id: string;
    name: string;
    target_field: string;
    condition_type: string;
    condition_value: string;
    action: string;
    is_active: boolean;
    created_at: string;
}

export function useMatchingRules() {
    return useGenericRules<MatchingRule>('/matching-rules');
}
