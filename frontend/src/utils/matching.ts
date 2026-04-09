/**
 * 消込画面共通ユーティリティ
 */

/**
 * 選択済みアイテムをリストの先頭に移動する。
 * 既存の順序は維持したまま、選択済みを上位に並べる。
 */
export function sortSelectedFirst<T>(
  list: T[],
  selectedIds: string[],
  getId: (item: T) => string,
): T[] {
  return [...list].sort((a, b) => {
    const aSelected = selectedIds.includes(getId(a));
    const bSelected = selectedIds.includes(getId(b));
    if (aSelected === bSelected) return 0;
    return aSelected ? -1 : 1;
  });
}

/**
 * 金額差・日付差が小さい順に並び替える（手動消込用）。
 * 金額差が主キー、日付差が副キー。
 */
export function sortByProximity<T>(
  list: T[],
  getAmount: (item: T) => number,
  getDate: (item: T) => string | undefined,
  targetAmount: number,
  targetDate?: string,
): T[] {
  const targetMs = targetDate ? new Date(targetDate).getTime() : null;
  return [...list].sort((a, b) => {
    const aDiff = Math.abs(getAmount(a) - targetAmount);
    const bDiff = Math.abs(getAmount(b) - targetAmount);
    if (aDiff !== bDiff) return aDiff - bDiff;
    if (targetMs === null) return 0;
    const aMs = getDate(a) ? new Date(getDate(a)!).getTime() : null;
    const bMs = getDate(b) ? new Date(getDate(b)!).getTime() : null;
    const aDateDiff = aMs !== null ? Math.abs(aMs - targetMs) : Infinity;
    const bDateDiff = bMs !== null ? Math.abs(bMs - targetMs) : Infinity;
    return aDateDiff - bDateDiff;
  });
}
