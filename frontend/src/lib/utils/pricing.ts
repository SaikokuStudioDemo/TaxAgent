export function calculateMonthlyFee(
    plans: any[],
    options: any[],
    planId: string,
    selectedOptionIds: string[],
): number {
    const selectedPlan = plans.find((p) => p.id === planId);
    const selectedOptionsData = options.filter((o) => selectedOptionIds.includes(o.id));
    const planPrice = selectedPlan?.price ?? 0;
    const optionsPrice = selectedOptionsData.reduce((acc: number, curr: any) => acc + curr.price, 0);
    return planPrice + optionsPrice;
}
