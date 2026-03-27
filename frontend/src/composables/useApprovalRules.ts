/**
 * useApprovalRules.ts - Approval rules composable backed by real API
 */
import { useGenericRules } from './useGenericRules';

export interface ApprovalCondition {
    field: string;
    operator: string;
    value: number | string;
}

export interface ApprovalStep {
    step: number;
    role: string;
    required: boolean;
    user_id?: string;
    approver_name?: string;
}

export interface ApprovalRule {
    id: string;
    name: string;
    applies_to: string[];
    conditions: ApprovalCondition[];
    steps: ApprovalStep[];
    active: boolean;
    created_at: string;
    project_id?: string;
}

export function useApprovalRules() {
    // applies_to クエリパラメータを filterParam として渡す
    return useGenericRules<ApprovalRule>('/approvals/rules', { filterParam: 'applies_to' });
}
