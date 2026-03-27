/**
 * useDocumentApproval.ts
 * 承認ダッシュボード共通ロジック（領収書・請求書で共有）
 *
 * ApprovalDashboardPage.vue / InvoiceApprovalPage.vue の重複を解消する。
 */
import { ref, computed, type Ref } from 'vue';

type TabView = 'pending' | 'pending_all' | 'approved' | 'rejected';

const DONE_STATUSES = ['approved', 'auto_approved', 'rejected'];

export interface UseDocumentApprovalOptions<T extends { id: string }> {
  /** データ取得関数（fetchFn 内で fetchPendingForMe 等も呼んでよい） */
  fetchFn: () => Promise<void>;
  /** 全件データの ref（pending_all / approved / rejected タブのソース） */
  items: Ref<T[]>;
  /**
   * 「あなたの承認待ち」タブ専用のデータ ref（省略時は items を使う）
   * 領収書の /receipts/pending-for-me など、別エンドポイントから取得する場合に指定する
   */
  pendingItems?: Ref<T[]>;
  /** approval_status を返す accessor */
  getApprovalStatus: (item: T) => string;
  /** 金額を返す accessor（urgent 判定に使用） */
  getAmount: (item: T) => number;
  /** 高額アラート閾値（デフォルト: 50000） */
  urgentThreshold?: number;
  /** 検索対象テキストを返す accessor（部分一致検索に使用） */
  getSearchableText: (item: T) => string;
}

export function useDocumentApproval<T extends { id: string }>(
  options: UseDocumentApprovalOptions<T>,
) {
  const {
    fetchFn,
    items,
    pendingItems,
    getApprovalStatus,
    getAmount,
    urgentThreshold = 50000,
    getSearchableText,
  } = options;

  // 「あなたの承認待ち」タブのソース: pendingItems があればそれを、なければ items を使う
  const pendingSource = pendingItems ?? items;

  const activeTab = ref<TabView>('pending');
  const searchQuery = ref('');
  const selectedItem = ref<T | null>(null) as Ref<T | null>;
  const isDetailModalOpen = ref(false);

  // ── フィルタリング ──────────────────────────────────────────
  const pendingList = computed(() =>
    pendingSource.value.filter(item => !DONE_STATUSES.includes(getApprovalStatus(item))),
  );

  const pendingAllList = computed(() =>
    items.value.filter(item => !DONE_STATUSES.includes(getApprovalStatus(item))),
  );

  const approvedList = computed(() => {
    return items.value.filter(item => {
      const s = getApprovalStatus(item);
      return s === 'approved' || s === 'auto_approved';
    });
  });

  const rejectedList = computed(() =>
    items.value.filter(item => getApprovalStatus(item) === 'rejected'),
  );

  const applySearch = (list: T[]): T[] => {
    const q = searchQuery.value.trim().toLowerCase();
    if (!q) return list;
    return list.filter(item => getSearchableText(item).toLowerCase().includes(q));
  };

  const displayedItems = computed<T[]>(() => {
    let list: T[];
    switch (activeTab.value) {
      case 'pending':     list = pendingList.value; break;
      case 'pending_all': list = pendingAllList.value; break;
      case 'approved':    list = approvedList.value; break;
      case 'rejected':    list = rejectedList.value; break;
      default:            list = [];
    }
    return applySearch(list);
  });

  // ── メトリクス ──────────────────────────────────────────────
  const metrics = computed(() => ({
    pendingCount: pendingList.value.length,
    urgentCount: pendingList.value.filter(item => getAmount(item) >= urgentThreshold).length,
  }));

  // ── モーダル管理 ────────────────────────────────────────────
  const openDetail = (item: T) => {
    selectedItem.value = item;
    isDetailModalOpen.value = true;
  };

  const closeDetail = () => {
    isDetailModalOpen.value = false;
    setTimeout(() => { selectedItem.value = null; }, 300);
  };

  const handleActionCompleted = async () => {
    closeDetail();
    await fetchFn();
  };

  return {
    activeTab,
    searchQuery,
    pendingList,
    pendingAllList,
    approvedList,
    rejectedList,
    displayedItems,
    metrics,
    selectedItem,
    isDetailModalOpen,
    openDetail,
    closeDetail,
    handleActionCompleted,
  };
}
