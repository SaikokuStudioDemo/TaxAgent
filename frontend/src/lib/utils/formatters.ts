/** 数値を日本語カンマ区切りにフォーマット（¥記号なし）例: 1234 → "1,234" */
export function formatNumber(amount: number): string {
    return new Intl.NumberFormat('ja-JP').format(amount ?? 0);
}

export function calculateTaxInclusive(amount: number, taxRate: number = 10): number {
    return Math.floor(amount * (1 + taxRate / 100));
}

export function formatCurrency(amount: number): string {
    return new Intl.NumberFormat('ja-JP', {
        style: 'currency',
        currency: 'JPY',
    }).format(amount);
}

/**
 * 日付から fiscal_period（YYYY-MM）を生成する。
 * 引数なしの場合は現在月を返す。
 */
export function getFiscalPeriod(date?: Date | string): string {
  if (!date) return new Date().toISOString().slice(0, 7)
  if (typeof date === 'string') return date.slice(0, 7)
  return date.toISOString().slice(0, 7)
}

/**
 * Date を YYYY-MM-DD 形式に変換する。
 */
export function formatDateISO(date: Date): string {
  return date.toISOString().split('T')[0]
}

export function formatInputAmount(val: number | string): string {
    if (val === null || val === undefined || val === '') return '';
    const numStr = val.toString().replace(/[^\d]/g, '');
    if (!numStr) return '';
    return parseInt(numStr, 10).toLocaleString('ja-JP');
}

export function parseInputAmount(val: string): number {
    const parsed = parseInt(val.replace(/[^\d]/g, ''), 10);
    return isNaN(parsed) ? 0 : parsed;
}
