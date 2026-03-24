export const TAX_RATE = 0.10; // 10% 消費税

/** 数値を日本語カンマ区切りにフォーマット（¥記号なし）例: 1234 → "1,234" */
export function formatNumber(amount: number): string {
    return new Intl.NumberFormat('ja-JP').format(amount ?? 0);
}

export function calculateTaxInclusive(amount: number): number {
    return Math.floor(amount * (1 + TAX_RATE));
}

export function formatCurrency(amount: number): string {
    return new Intl.NumberFormat('ja-JP', {
        style: 'currency',
        currency: 'JPY',
    }).format(amount);
}
