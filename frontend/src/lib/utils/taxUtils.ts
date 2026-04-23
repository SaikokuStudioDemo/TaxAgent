/**
 * 税込金額から消費税額を逆算する（四捨五入）。
 * taxRate は int（10・8・0）。
 */
export function calcTaxFromInclusive(amount: number, taxRate: number): number {
  if (taxRate === 0) return 0
  return Math.round(amount * taxRate / (100 + taxRate))
}

/**
 * 税抜金額から消費税額を直算する（切り捨て）。
 * 日本の消費税法の原則に従う。
 */
export function calcTaxFromExclusive(amount: number, taxRate: number): number {
  if (taxRate === 0) return 0
  return Math.floor(amount * taxRate / 100)
}

/**
 * 税抜金額から税込金額を計算する（切り捨て）。
 */
export function calcInclusiveFromExclusive(amount: number, taxRate: number): number {
  return amount + calcTaxFromExclusive(amount, taxRate)
}

/**
 * 内部値（0.10）をパーセント表示（10）に変換する。
 * すでに整数の場合はそのまま返す。
 */
export function formatTaxRatePercent(rate: number): number {
  return rate <= 1 ? Math.round(rate * 100) : rate
}

/**
 * パーセント入力（10）を内部値（0.10）に変換する。
 * すでに小数の場合はそのまま返す。
 */
export function parseTaxRateInput(value: number): number {
  return value > 1 ? value / 100 : value
}
