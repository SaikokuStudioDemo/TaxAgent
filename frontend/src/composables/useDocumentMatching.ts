/**
 * useDocumentMatching.ts
 * 消込ページ共通ロジック（領収書・請求書で共有）
 *
 * MatchingPage.vue / InvoiceMatchingPage.vue の重複を解消する。
 * UI テンプレートは各ページで個別に保持する。
 */
import { ref, computed, isRef, type Ref } from 'vue';
import { useTransactions, type Transaction as ApiTransaction } from '@/composables/useTransactions';

// ── 共通型 ──────────────────────────────────────────────────────

/** 消込対象ドキュメント（領収書・請求書）が実装すべき最小インターフェース */
export interface MatchableDocument {
  id: string;
  matched: boolean;
}

/** 消込UI用にマップされた取引明細 */
export interface MatchingTransaction {
  id: string;
  date: string;
  description: string;
  amount: number;
  type: 'bank' | 'card';
  transaction_type: 'credit' | 'debit';
  matched: boolean;
}

/** matchedPairs / candidatePairs の1エントリ */
export interface MatchedPair<T extends MatchableDocument> {
  matchId: string;
  document: T;
  transaction: MatchingTransaction;
  matchedAt: string;
}

export interface CandidatePair<T extends MatchableDocument> {
  document: T;
  transaction: MatchingTransaction;
}

// ── オプション ───────────────────────────────────────────────────

export interface UseDocumentMatchingOptions<T extends MatchableDocument> {
  /** ドキュメント取得関数（呼び出し後に documents.value を更新すること） */
  fetchDocumentsFn: () => Promise<void>;
  /** ドキュメントの ref（MatchableDocument を実装した型） */
  documents: Ref<T[]>;
  /** POST /matches の match_type */
  matchType: 'receipt' | 'invoice';
  /** 金額を返す accessor（金額マッチング・差額計算に使用） */
  getAmount: (item: T) => number;
  /** 検索用テキストを返す accessor */
  getDescription: (item: T) => string;
  /**
   * 取引明細を transaction_type でフィルタする（入金: 'credit' / 出金: 'debit'）
   * Ref を渡すことで reactive に切り替え可能
   */
  transactionTypeFilter?: Ref<'credit' | 'debit'> | 'credit' | 'debit';
}

// ── composable ──────────────────────────────────────────────────

export function useDocumentMatching<T extends MatchableDocument>(
  options: UseDocumentMatchingOptions<T>,
) {
  const { fetchDocumentsFn, documents, matchType, getAmount, getDescription, transactionTypeFilter } = options;

  // transactionTypeFilter を統一的に読む getter
  const getTxTypeFilter = (): string | undefined =>
    isRef(transactionTypeFilter) ? transactionTypeFilter.value : transactionTypeFilter;

  const {
    transactions: apiTransactions,
    matches,
    fetchTransactions,
    fetchMatches,
    createMatch,
    deleteMatch,
  } = useTransactions();

  // ── ローカル状態 ─────────────────────────────────────────────
  const rawTransactions = ref<MatchingTransaction[]>([]) as Ref<MatchingTransaction[]>;

  const activeTab = ref<'unmatched' | 'candidates' | 'matched'>('unmatched');
  const documentSearch = ref('');
  const transactionSearch = ref('');
  const selectedDocumentIds = ref<string[]>([]);
  const selectedTransactionIds = ref<string[]>([]);
  const selectedCandidateIds = ref<string[]>([]);

  // 金額差確認モーダル
  const showConfirmMatch = ref(false);
  const confirmMatchResolve = ref<((value: boolean) => void) | null>(null);
  const confirmMatchAmount = ref(0);

  // ── データ変換 ──────────────────────────────────────────────
  const mapApiToTransaction = (t: ApiTransaction): MatchingTransaction => ({
    id: t.id,
    date: t.transaction_date,
    description: t.description,
    amount: t.amount,
    type: t.source_type,
    transaction_type: t.transaction_type,
    matched: false,
  });

  /** matches の内容を documents / rawTransactions の matched フラグに反映 */
  const applyMatches = () => {
    rawTransactions.value.forEach(t => { t.matched = false; });
    documents.value.forEach(d => { d.matched = false; });
    matches.value
      .filter((m: any) => m.match_type === matchType)
      .forEach((m: any) => {
        (m.document_ids ?? []).forEach((did: string) => {
          const doc = documents.value.find(d => d.id === did);
          if (doc) doc.matched = true;
        });
        (m.transaction_ids ?? []).forEach((tid: string) => {
          const tx = rawTransactions.value.find(t => t.id === tid);
          if (tx) tx.matched = true;
        });
      });
  };

  /** 初回ロード / リロード */
  const loadData = async () => {
    await Promise.all([
      fetchDocumentsFn(),
      fetchTransactions({}),
      fetchMatches({ match_type: matchType }),
    ]);
    rawTransactions.value = apiTransactions.value.map(mapApiToTransaction);
    applyMatches();
  };

  // ── computed ────────────────────────────────────────────────
  const unmatchedTransactions = computed(() => {
    const txFilter = getTxTypeFilter();
    let list = rawTransactions.value.filter(t => !t.matched);
    if (txFilter) {
      list = list.filter(t => t.transaction_type === txFilter);
    }
    if (transactionSearch.value) {
      list = list.filter(
        t => t.description.includes(transactionSearch.value) ||
             t.amount.toString().includes(transactionSearch.value),
      );
    }
    return list;
  });

  const unmatchedDocuments = computed(() => {
    let list = documents.value.filter(d => !d.matched);
    if (documentSearch.value) {
      list = list.filter(d => getDescription(d).includes(documentSearch.value));
    }
    return list;
  });

  const selectedTransactionSum = computed(() =>
    unmatchedTransactions.value
      .filter(t => selectedTransactionIds.value.includes(t.id))
      .reduce((sum, t) => sum + t.amount, 0),
  );

  const selectedDocumentSum = computed(() =>
    unmatchedDocuments.value
      .filter(d => selectedDocumentIds.value.includes(d.id))
      .reduce((sum, d) => sum + getAmount(d), 0),
  );

  const matchingDifference = computed(() =>
    Math.abs(selectedTransactionSum.value - selectedDocumentSum.value),
  );

  const suggestedDocumentIds = computed(() => {
    if (selectedTransactionIds.value.length === 0) return [];
    return unmatchedDocuments.value
      .filter(d => getAmount(d) === selectedTransactionSum.value)
      .map(d => d.id);
  });

  /** 金額が一致するドキュメント×取引明細のペアを自動候補として生成 */
  const candidatePairs = computed<CandidatePair<T>[]>(() => {
    const pairs: CandidatePair<T>[] = [];
    const usedDocIds = new Set<string>();
    rawTransactions.value.filter(t => !t.matched).forEach(tx => {
      const match = documents.value.find(
        d => !d.matched && !usedDocIds.has(d.id) && getAmount(d) === tx.amount,
      );
      if (match) {
        pairs.push({ document: match, transaction: tx });
        usedDocIds.add(match.id);
      }
    });
    return pairs;
  });

  /** matches テーブルから消込済みペアを構築 */
  const matchedPairs = computed<MatchedPair<T>[]>(() =>
    matches.value
      .filter((m: any) => m.match_type === matchType)
      .map((m: any) => {
        const doc = documents.value.find(d => (m.document_ids ?? []).includes(d.id));
        const tx  = rawTransactions.value.find(t => (m.transaction_ids ?? []).includes(t.id));
        if (!doc || !tx) return null;
        return {
          matchId: m.id as string,
          document: doc,
          transaction: tx,
          matchedAt: m.matched_at ?? '',
        };
      })
      .filter((item): item is MatchedPair<T> => item !== null),
  );

  const matchedCount = computed(() => rawTransactions.value.filter(t => t.matched).length);

  // ── アクション ──────────────────────────────────────────────
  const selectTransaction = (id: string) => {
    const idx = selectedTransactionIds.value.indexOf(id);
    if (idx > -1) selectedTransactionIds.value.splice(idx, 1);
    else selectedTransactionIds.value.push(id);
  };

  const selectDocument = (id: string) => {
    const idx = selectedDocumentIds.value.indexOf(id);
    if (idx > -1) selectedDocumentIds.value.splice(idx, 1);
    else selectedDocumentIds.value.push(id);
  };

  const toggleCandidate = (txId: string) => {
    const idx = selectedCandidateIds.value.indexOf(txId);
    if (idx > -1) selectedCandidateIds.value.splice(idx, 1);
    else selectedCandidateIds.value.push(txId);
  };

  const toggleAllCandidates = () => {
    if (selectedCandidateIds.value.length === candidatePairs.value.length) {
      selectedCandidateIds.value = [];
    } else {
      selectedCandidateIds.value = candidatePairs.value.map(p => p.transaction.id);
    }
  };

  const handleMatch = async () => {
    if (selectedDocumentIds.value.length === 0 || selectedTransactionIds.value.length === 0) return;

    if (matchingDifference.value > 1000) {
      confirmMatchAmount.value = matchingDifference.value;
      showConfirmMatch.value = true;
      const confirmed = await new Promise<boolean>(resolve => {
        confirmMatchResolve.value = resolve;
      });
      showConfirmMatch.value = false;
      if (!confirmed) return;
    }

    const period = new Date().toISOString().slice(0, 7);
    await createMatch({
      match_type: matchType,
      transaction_ids: [...selectedTransactionIds.value],
      document_ids: [...selectedDocumentIds.value],
      fiscal_period: period,
    });

    await fetchMatches({ match_type: matchType });
    applyMatches();
    selectedDocumentIds.value = [];
    selectedTransactionIds.value = [];
  };

  const handleBulkMatch = async () => {
    const period = new Date().toISOString().slice(0, 7);
    for (const txId of selectedCandidateIds.value) {
      const pair = candidatePairs.value.find(p => p.transaction.id === txId);
      if (!pair) continue;
      await createMatch({
        match_type: matchType,
        transaction_ids: [txId],
        document_ids: [pair.document.id],
        fiscal_period: period,
      });
    }
    selectedCandidateIds.value = [];
    await fetchMatches({ match_type: matchType });
    applyMatches();
    activeTab.value = 'matched';
  };

  const revertToUnmatched = async (txId: string, docId?: string) => {
    const m = matches.value.find((mx: any) =>
      mx.transaction_ids?.includes(txId) &&
      (!docId || mx.document_ids?.includes(docId)),
    );
    if (m) await deleteMatch(m.id);
    await fetchMatches({ match_type: matchType });
    applyMatches();
    const idx = selectedCandidateIds.value.indexOf(txId);
    if (idx > -1) selectedCandidateIds.value.splice(idx, 1);
  };

  return {
    rawTransactions,
    activeTab,
    documentSearch,
    transactionSearch,
    selectedDocumentIds,
    selectedTransactionIds,
    selectedCandidateIds,
    showConfirmMatch,
    confirmMatchResolve,
    confirmMatchAmount,
    unmatchedTransactions,
    unmatchedDocuments,
    selectedTransactionSum,
    selectedDocumentSum,
    matchingDifference,
    suggestedDocumentIds,
    candidatePairs,
    matchedPairs,
    matchedCount,
    loadData,
    selectTransaction,
    selectDocument,
    toggleCandidate,
    toggleAllCandidates,
    handleMatch,
    handleBulkMatch,
    revertToUnmatched,
  };
}
