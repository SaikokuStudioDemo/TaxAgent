import { PLANS, OPTIONS } from '@/lib/constants/mockData';

export function calculateMonthlyFee(planId: string, selectedOptions: string[]): number {
    const selectedPlan = PLANS.find((p) => p.id === planId);
    const selectedOptionsData = OPTIONS.filter((o) => selectedOptions.includes(o.id));

    const planPrice = selectedPlan?.price || 0;
    const optionsPrice = selectedOptionsData.reduce((acc, curr) => acc + curr.price, 0);

    return planPrice + optionsPrice;
}
