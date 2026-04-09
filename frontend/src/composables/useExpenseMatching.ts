/**
 * useExpenseMatching.ts
 * 経費消込専用コンポーザブル
 *
 * 左ペイン：申請者グループ（N件の領収書を合計して1カード）
 * 右ペイン：未消込の振込出金明細
 * マッチング：グループ選択 × 振込選択 → POST /matches (1tx : N docs)
 */
import { ref, computed } from 'vue';
import { useReceipts, type Receipt } from '@/composables/useReceipts';
import { useTransactions, type Transaction, type Match } from '@/composables/useTransactions';
import { sortSelectedFirst, sortByProximity } from '@/utils/matching';

// ── 型定義 ───────────────────────────────────────────────

export interface ReceiptGroup {
  userId: string;       // submitted_by
  userName: string;     // submitter_name（API付加）
  receipts: Receipt[];
  total: number;
}

export interface MatchedExpense {
  matchId: string;
  group: ReceiptGroup;
  transaction: Transaction;
  matchedAt: string;
}

// ── composable ──────────────────────────────────────────

export function useExpenseMatching() {
  const { receipts, fetchReceipts } = useReceipts();
  const { transactions, matches, fetchTransactions, fetchMatches, createMatch, deleteMatch } = useTransactions();

  const isLoading = ref(false);
  const activeTab = ref<'unmatched' | 'matched'>('unmatched');

  // 検索
  const groupSearch = ref('');
  const transactionSearch = ref('');

  // 選択状態
  const selectedGroupUserId = ref<string | null>(null);
  const selectedTransactionId = ref<string | null>(null);

  // ── データロード ────────────────────────────────────────

  const loadData = async () => {
    isLoading.value = true;
    try {
      await Promise.all([
        fetchReceipts({ receipt_type: 'expense' }),
        fetchTransactions({}),
        fetchMatches({ match_type: 'receipt' }),
      ]);
    } finally {
      isLoading.value = false;
    }
  };

  // ── 消込済み transaction_id セット ──────────────────────

  const matchedTransactionIds = computed<Set<string>>(() => {
    const ids = new Set<string>();
    matches.value
      .filter((m: Match) => m.match_type === 'receipt')
      .forEach((m: Match) => m.transaction_ids.forEach(id => ids.add(id)));
    return ids;
  });

  const matchedReceiptIds = computed<Set<string>>(() => {
    const ids = new Set<string>();
    matches.value
      .filter((m: Match) => m.match_type === 'receipt')
      .forEach((m: Match) => m.document_ids.forEach(id => ids.add(id)));
    return ids;
  });

  // ── 申請者グループ（未消込） ───────────────────────────

  const receiptGroups = computed<ReceiptGroup[]>(() => {
    // 未消込かつ承認済みの領収書のみ
    const unreconciled = receipts.value.filter(
      r => !matchedReceiptIds.value.has(r.id) && r.reconciliation_status !== 'reconciled'
    );

    // submitted_by でグルーピング
    const map = new Map<string, Receipt[]>();
    for (const r of unreconciled) {
      const uid = r.submitted_by;
      if (!uid) continue;
      if (!map.has(uid)) map.set(uid, []);
      map.get(uid)!.push(r);
    }

    const groups: ReceiptGroup[] = [];
    for (const [userId, recs] of map) {
      const userName = recs[0].submitter_name ?? userId;
      groups.push({
        userId,
        userName,
        receipts: recs,
        total: recs.reduce((s, r) => s + r.amount, 0),
      });
    }

    // 検索フィルタ
    const filtered = groupSearch.value
      ? groups.filter(g =>
          g.userName.includes(groupSearch.value) ||
          g.receipts.some(r => r.payee?.includes(groupSearch.value))
        )
      : groups;
    const selectedIds = selectedGroupUserId.value ? [selectedGroupUserId.value] : [];
    return sortSelectedFirst(filtered, selectedIds, g => g.userId);
  });

  // ── 選択した取引に金額・日付が近いグループを先頭に（手動消込用） ──

  const sortedReceiptGroups = computed<ReceiptGroup[]>(() => {
    const list = receiptGroups.value;
    if (!selectedTransactionId.value) return list;
    const tx = transactions.value.find(t => t.id === selectedTransactionId.value);
    if (!tx) return list;
    return sortByProximity(list, g => g.total, () => undefined, tx.amount, tx.transaction_date);
  });

  // ── 未消込の振込出金明細 ─────────────────────────────

  const unmatchedDebitTransactions = computed<Transaction[]>(() => {
    let list = transactions.value.filter(
      t => t.transaction_type === 'debit' && t.source_type === 'bank' && t.status === 'unmatched' && !matchedTransactionIds.value.has(t.id)
    );
    if (transactionSearch.value) {
      list = list.filter(
        t => t.description.includes(transactionSearch.value) ||
             t.amount.toString().includes(transactionSearch.value)
      );
    }
    const selectedIds = selectedTransactionId.value ? [selectedTransactionId.value] : [];
    return sortSelectedFirst(list, selectedIds, t => t.id);
  });

  // ── 選択したグループに金額・日付が近い取引明細を先頭に（手動消込用） ──

  const sortedDebitTransactions = computed<Transaction[]>(() => {
    const list = unmatchedDebitTransactions.value;
    if (!selectedGroupUserId.value) return list;
    const group = receiptGroups.value.find(g => g.userId === selectedGroupUserId.value);
    if (!group) return list;
    return sortByProximity(list, t => t.amount, t => t.transaction_date, group.total);
  });

  // ── 選択中グループ・明細 ─────────────────────────────

  const selectedGroup = computed(() =>
    receiptGroups.value.find(g => g.userId === selectedGroupUserId.value) ?? null
  );

  const selectedTransaction = computed(() =>
    unmatchedDebitTransactions.value.find(t => t.id === selectedTransactionId.value) ?? null
  );

  const difference = computed(() => {
    if (!selectedGroup.value || !selectedTransaction.value) return null;
    return selectedGroup.value.total - selectedTransaction.value.amount;
  });

  // ── 消込済みペア ─────────────────────────────────────

  const matchedExpenses = computed<MatchedExpense[]>(() =>
    matches.value
      .filter((m: Match) => m.match_type === 'receipt')
      .map((m: Match) => {
        // グループ再構築（全領収書から該当するものを集める）
        const matchedReceipts = receipts.value.filter(r => m.document_ids.includes(r.id));
        const tx = transactions.value.find(t => m.transaction_ids.includes(t.id));
        if (!tx || matchedReceipts.length === 0) return null;

        const userId = matchedReceipts[0].submitted_by;
        const userName = matchedReceipts[0].submitter_name ?? userId;
        const group: ReceiptGroup = {
          userId,
          userName,
          receipts: matchedReceipts,
          total: matchedReceipts.reduce((s, r) => s + r.amount, 0),
        };
        return { matchId: m.id, group, transaction: tx, matchedAt: m.matched_at } as MatchedExpense;
      })
      .filter((x): x is MatchedExpense => x !== null)
  );

  // ── アクション ──────────────────────────────────────

  const selectGroup = (userId: string) => {
    selectedGroupUserId.value = selectedGroupUserId.value === userId ? null : userId;
  };

  const selectTransaction = (txId: string) => {
    selectedTransactionId.value = selectedTransactionId.value === txId ? null : txId;
  };

  const isMatching = ref(false);

  const handleMatch = async () => {
    if (!selectedGroup.value || !selectedTransaction.value) return;
    isMatching.value = true;
    try {
      await createMatch({
        match_type: 'receipt',
        transaction_ids: [selectedTransaction.value.id],
        document_ids: selectedGroup.value.receipts.map(r => r.id),
        fiscal_period: selectedTransaction.value.fiscal_period ?? new Date().toISOString().slice(0, 7),
        matched_by: 'manual',
      });
      selectedGroupUserId.value = null;
      selectedTransactionId.value = null;
      // 消込済みに反映するため receipts も再取得
      await Promise.all([
        fetchReceipts({ approval_status: 'approved' }),
        fetchMatches({ match_type: 'receipt' }),
      ]);
    } finally {
      isMatching.value = false;
    }
  };

  const revertMatch = async (matchId: string) => {
    await deleteMatch(matchId);
    await Promise.all([
      fetchReceipts({ receipt_type: 'expense' }),
      fetchTransactions({}),
      fetchMatches({ match_type: 'receipt' }),
    ]);
  };

  return {
    isLoading,
    activeTab,
    groupSearch,
    transactionSearch,
    receiptGroups,
    sortedReceiptGroups,
    unmatchedDebitTransactions,
    sortedDebitTransactions,
    selectedGroupUserId,
    selectedTransactionId,
    selectedGroup,
    selectedTransaction,
    difference,
    matchedExpenses,
    isMatching,
    loadData,
    selectGroup,
    selectTransaction,
    handleMatch,
    revertMatch,
  };
}
