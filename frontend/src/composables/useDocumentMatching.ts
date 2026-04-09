/**
 * useDocumentMatching.ts
 * 消込ページ共通ロジック（領収書・請求書で共有）
 *
 * MatchingPage.vue / InvoiceMatchingPage.vue の重複を解消する。
 * UI テンプレートは各ページで個別に保持する。
 */
import { ref, computed, isRef, type Ref } from 'vue';
import { useTransactions, type Transaction as ApiTransaction } from '@/composables/useTransactions';
import type { ApiCandidatePair } from '@/composables/useTransactions';
import { sortSelectedFirst, sortByProximity } from '@/utils/matching';

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
  source_type: 'bank' | 'card';  // 追加
  transaction_type: 'credit' | 'debit';
  status: 'unmatched' | 'matched' | 'transferred';
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
  score?: number;
  score_breakdown?: { amount: number; date: number; name: number };
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
  /**
   * 請求書種別（candidates API の絞り込みに使用）
   * 'issued': 入金系取引のみ / 'received': 出金系取引のみ
   */
  invoiceType?: 'issued' | 'received';
  /**
   * 取引明細を source_type でフィルタする（'bank' / 'card'）
   * Ref を渡すことで reactive に切り替え可能
   */
  sourceTypeFilter?: Ref<'bank' | 'card' | 'all'> | 'bank' | 'card' | 'all';
}

// ── composable ──────────────────────────────────────────────────

export function useDocumentMatching<T extends MatchableDocument>(
  options: UseDocumentMatchingOptions<T>,
) {
  const { fetchDocumentsFn, documents, matchType, getAmount, getDescription, transactionTypeFilter, invoiceType, sourceTypeFilter } = options;

  // transactionTypeFilter を統一的に読む getter
  const getTxTypeFilter = (): string | undefined =>
    isRef(transactionTypeFilter) ? transactionTypeFilter.value : transactionTypeFilter;

  // sourceTypeFilter を統一的に読む getter
  const getSourceTypeFilter = (): string | undefined => {
    const v = isRef(sourceTypeFilter) ? sourceTypeFilter.value : sourceTypeFilter;
    return v === 'all' ? undefined : v;
  };

  const {
    transactions: apiTransactions,
    matches,
    fetchTransactions,
    fetchMatches,
    createMatch,
    patchMatch,
    deleteMatch,
    fetchCandidates,
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
    source_type: t.source_type,
    transaction_type: t.transaction_type,
    status: t.status ?? 'unmatched',
    matched: t.status === 'matched' || t.status === 'transferred',
  });

  /** matches の内容を documents / rawTransactions の matched フラグに反映 */
  const applyMatches = () => {
    rawTransactions.value.forEach(t => { t.matched = t.status === 'matched' || t.status === 'transferred'; });
    documents.value.forEach(d => { d.matched = false; });
    matches.value
      .filter((m: any) => m.match_type === matchType || m.match_type === 'transfer')
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
    // transfer matches を追加取得して matches に追記（applyMatches で transfer 消込も反映するため）
    const savedMatches = [...matches.value];
    await fetchMatches({ match_type: 'transfer' });
    const transferMatches = matches.value;
    const merged = [...savedMatches];
    for (const tm of transferMatches) {
      if (!merged.some(m => m.id === tm.id)) merged.push(tm);
    }
    matches.value = merged;
    rawTransactions.value = apiTransactions.value.map(mapApiToTransaction);
    applyMatches();
    // バックエンドのスコアリングAPIから候補ペアを取得
    const apiCandidates: ApiCandidatePair[] = await fetchCandidates({ match_type: matchType, invoice_type: invoiceType });
    candidatePairs.value = apiCandidates
      .map(c => {
        const doc = documents.value.find(d => d.id === c.document.id);
        const tx = rawTransactions.value.find(t => t.id === c.transaction.id);
        if (!doc || !tx) return null;
        return {
          document: doc,
          transaction: tx,
          score: c.score,
          score_breakdown: c.score_breakdown,
        } as CandidatePair<T>;
      })
      .filter((p): p is CandidatePair<T> => p !== null);
  };

  // ── computed ────────────────────────────────────────────────

  /** バックエンドのスコアリングAPIから取得した候補ペア（loadData で更新） */
  const candidatePairs = ref<CandidatePair<T>[]>([]) as Ref<CandidatePair<T>[]>;

  /** 自動消込候補に含まれる取引ID セット（手動消込リストから除外するために使用） */
  const candidateTxIds = computed(
    () => new Set(candidatePairs.value.map(p => p.transaction.id)),
  );

  /** 自動消込候補に含まれるドキュメントID セット（手動消込リストから除外するために使用） */
  const candidateDocIds = computed(
    () => new Set(candidatePairs.value.map(p => p.document.id)),
  );

  const unmatchedTransactions = computed(() => {
    const txFilter = getTxTypeFilter();
    const srcFilter = getSourceTypeFilter();
    let list = rawTransactions.value.filter(
      t => !t.matched && t.status !== 'transferred' && !candidateTxIds.value.has(t.id),
    );
    if (txFilter) {
      list = list.filter(t => t.transaction_type === txFilter);
    }
    if (srcFilter) {
      list = list.filter(t => t.source_type === srcFilter);
    }
    if (transactionSearch.value) {
      list = list.filter(
        t => t.description.includes(transactionSearch.value) ||
             t.amount.toString().includes(transactionSearch.value),
      );
    }
    return sortSelectedFirst(list, selectedTransactionIds.value, t => t.id);
  });

  const unmatchedDocuments = computed(() => {
    let list = documents.value.filter(d => !d.matched && !candidateDocIds.value.has(d.id));
    if (documentSearch.value) {
      list = list.filter(d =>
        d.id.includes(documentSearch.value) || getDescription(d).includes(documentSearch.value),
      );
    }
    return sortSelectedFirst(list, selectedDocumentIds.value, d => d.id);
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

  /** 選択した取引に金額・日付が近いドキュメントを先頭に並び替え（手動消込用） */
  const sortedUnmatchedDocuments = computed(() => {
    const list = unmatchedDocuments.value;
    if (selectedTransactionIds.value.length === 0) return list;
    const tx = unmatchedTransactions.value.find(t => selectedTransactionIds.value.includes(t.id));
    return sortByProximity(list, getAmount, () => undefined, selectedTransactionSum.value, tx?.date);
  });

  /** docId → (txId → score) の O(1) ルックアップ用マップ */
  const candidateScoreMap = computed(() => {
    const map = new Map<string, Map<string, number>>();
    for (const pair of candidatePairs.value) {
      if (!map.has(pair.document.id)) map.set(pair.document.id, new Map());
      map.get(pair.document.id)!.set(pair.transaction.id, pair.score ?? 0);
    }
    return map;
  });

  /**
   * ドキュメントを1件選択中のとき、右ペインの取引明細を金額・日付が近い順でソート（手動消込用）。
   */
  const sortedUnmatchedTransactions = computed(() => {
    const list = unmatchedTransactions.value;
    if (selectedDocumentIds.value.length === 0) return list;
    const doc = unmatchedDocuments.value.find(d => selectedDocumentIds.value.includes(d.id));
    return sortByProximity(list, t => t.amount, t => t.date, selectedDocumentSum.value, (doc as any)?.due_date ?? (doc as any)?.date);
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

  /** ペアの一意キー: "docId:txId" */
  const pairKey = (docId: string, txId: string) => `${docId}:${txId}`;

  const toggleCandidate = (docId: string, txId: string) => {
    const key = pairKey(docId, txId);
    const idx = selectedCandidateIds.value.indexOf(key);
    if (idx > -1) selectedCandidateIds.value.splice(idx, 1);
    else selectedCandidateIds.value.push(key);
  };

  const toggleAllCandidates = () => {
    if (selectedCandidateIds.value.length === candidatePairs.value.length) {
      selectedCandidateIds.value = [];
    } else {
      selectedCandidateIds.value = candidatePairs.value.map(p => pairKey(p.document.id, p.transaction.id));
    }
  };

  const handleMatch = async (receiptIds?: string[]) => {
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
      auto_suggested: false,
      ...(receiptIds && receiptIds.length > 0 ? { receipt_ids: receiptIds } : {}),
    });

    await fetchMatches({ match_type: matchType });
    applyMatches();
    selectedDocumentIds.value = [];
    selectedTransactionIds.value = [];
  };

  const handleBulkMatch = async () => {
    const period = new Date().toISOString().slice(0, 7);
    for (const key of selectedCandidateIds.value) {
      const [docId, txId] = key.split(':');
      const pair = candidatePairs.value.find(
        p => p.document.id === docId && p.transaction.id === txId,
      );
      if (!pair) continue;
      await createMatch({
        match_type: matchType,
        transaction_ids: [txId],
        document_ids: [docId],
        fiscal_period: period,
        auto_suggested: true,
      });
    }
    selectedCandidateIds.value = [];
    await fetchMatches({ match_type: matchType });
    applyMatches();
    // 候補リストを再取得してリフレッシュ
    const apiCandidates: ApiCandidatePair[] = await fetchCandidates({ match_type: matchType, invoice_type: invoiceType });
    candidatePairs.value = apiCandidates
      .map(c => {
        const doc = documents.value.find(d => d.id === c.document.id);
        const tx = rawTransactions.value.find(t => t.id === c.transaction.id);
        if (!doc || !tx) return null;
        return { document: doc, transaction: tx, score: c.score, score_breakdown: c.score_breakdown } as CandidatePair<T>;
      })
      .filter((p): p is CandidatePair<T> => p !== null);
    activeTab.value = 'matched';
  };

  const revertToUnmatched = async (txId: string, docId?: string) => {
    const m = matches.value.find((mx: any) =>
      mx.transaction_ids?.includes(txId) &&
      (!docId || mx.document_ids?.includes(docId)),
    );
    if (m) {
      // 自動提案から確定したマッチを解除する場合は rejected を記録
      if (m.auto_suggested) {
        await patchMatch(m.id, { user_action: 'rejected' });
      }
      await deleteMatch(m.id);
    }
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
    sortedUnmatchedDocuments,
    selectedTransactionSum,
    selectedDocumentSum,
    matchingDifference,
    suggestedDocumentIds,
    candidatePairs,
    candidateScoreMap,
    sortedUnmatchedTransactions,
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
