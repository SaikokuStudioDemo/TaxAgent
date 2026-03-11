export const TAX_RATE = 0.10; // 10% 消費税

export function calculateTaxInclusive(amount: number): number {
    return Math.floor(amount * (1 + TAX_RATE));
}

export function formatCurrency(amount: number): string {
    return new Intl.NumberFormat('ja-JP', {
        style: 'currency',
        currency: 'JPY',
    }).format(amount);
}
