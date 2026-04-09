"""
Matching Score Service
取引明細とドキュメント（領収書・請求書）のマッチングスコアを計算する。
"""
from datetime import datetime
from typing import Optional


# ── ユーティリティ ────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _kata_to_hira(text: str) -> str:
    """カタカナをひらがなに変換する。"""
    result = []
    for c in text:
        code = ord(c)
        if 0x30A1 <= code <= 0x30F6:  # ァ〜ヶ
            result.append(chr(code - 0x60))
        else:
            result.append(c)
    return "".join(result)


# 銀行摘要・会社名から法人格表記を除去するためのプレフィックス/サフィックスリスト
_CORP_PREFIXES = ["株式会社", "有限会社", "合同会社", "合名会社", "合資会社",
                  "一般社団法人", "公益社団法人", "一般財団法人", "公益財団法人"]
_CORP_SUFFIXES = ["株式会社", "有限会社", "合同会社"]
# 銀行振込摘要に現れる法人格略称
_BANK_CORP_PREFIXES = ["カ）", "（カ）", "(カ)", "カ　", "ユ）", "（ユ）", "(ユ)", "ユ　",
                       "シャ）", "（シャ）", "(シャ)"]


def _normalize_corp_name(name: str) -> str:
    """会社名・銀行摘要から法人格プレフィックス/サフィックスを除去して正規化する。"""
    n = name.strip()
    for prefix in _CORP_PREFIXES + _BANK_CORP_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):].strip()
            break
    for suffix in _CORP_SUFFIXES:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
            break
    return n


# ── スコア計算 ────────────────────────────────────────────────

def _calc_amount_score(tx_amount: int, doc_amount: int) -> int:
    diff = abs(tx_amount - doc_amount)
    if diff == 0:
        return 40
    if diff <= 500:
        return 35
    if diff <= 1000:
        return 25
    return 0  # 候補から除外


def _calc_date_score(tx_date_str: Optional[str], doc_date_str: Optional[str]) -> int:
    tx_date = _parse_date(tx_date_str)
    doc_date = _parse_date(doc_date_str)
    if tx_date is None or doc_date is None:
        return 0
    diff = abs((tx_date - doc_date).days)
    if diff <= 1:
        return 30
    if diff <= 3:
        return 25
    if diff <= 7:
        return 15
    if diff <= 14:
        return 5
    if diff <= 30:
        return 2
    return 0


def _choose_closer_date(
    tx_date_str: Optional[str],
    date1_str: Optional[str],
    date2_str: Optional[str],
) -> Optional[str]:
    """2つの日付のうち、取引日付に近い方を返す。"""
    tx_date = _parse_date(tx_date_str)
    if tx_date is None:
        return date1_str or date2_str

    d1 = _parse_date(date1_str)
    d2 = _parse_date(date2_str)

    if d1 is None and d2 is None:
        return None
    if d1 is None:
        return date2_str
    if d2 is None:
        return date1_str

    return date1_str if abs((tx_date - d1).days) <= abs((tx_date - d2).days) else date2_str


def _calc_name_score(
    tx_desc: Optional[str],
    tx_norm: Optional[str],
    doc_name: Optional[str],
    bank_display_patterns: Optional[list] = None,
) -> int:
    """
    名称スコアを計算する。

    bank_display_patterns: 取引先マスターの bank_display_names パターンリスト。
    パターンが tx_desc に一致すれば満点（30点）を返す。
    """
    # 候補テキストリスト（空文字除外）
    tx_candidates = [s for s in [tx_desc or "", tx_norm or ""] if s]

    # ── 取引先マスターのパターン照合（最優先・満点）──────────────
    if bank_display_patterns:
        for pattern in bank_display_patterns:
            if not pattern:
                continue
            p_l = pattern.lower()
            for tx in tx_candidates:
                tx_l = tx.lower()
                if p_l in tx_l or tx_l in p_l:
                    return 30
            # カタカナ→ひらがな変換でも照合
            p_h = _kata_to_hira(p_l)
            for tx in tx_candidates:
                tx_h = _kata_to_hira(tx.lower())
                if p_h in tx_h or tx_h in p_h:
                    return 30

    if not doc_name:
        return 0

    candidates = [s.lower() for s in tx_candidates if s]
    doc_l = doc_name.lower()

    if not candidates:
        return 0

    # 1. 直接部分一致（大文字小文字無視）
    for c in candidates:
        if doc_l in c or c in doc_l:
            return 30

    # 2. 法人格プレフィックス除去後に部分一致（例: 株式会社エースリメイク ↔ カ）エースリメイク）
    doc_norm = _normalize_corp_name(doc_l)
    if doc_norm:
        for c in candidates:
            c_norm = _normalize_corp_name(c)
            if doc_norm in c_norm or c_norm in doc_norm:
                return 30

    # 3. カタカナ→ひらがな変換後に部分一致
    doc_h = _kata_to_hira(doc_l)
    for c in candidates:
        c_h = _kata_to_hira(c)
        if doc_h in c_h or c_h in doc_h:
            return 20

    # カタカナ→ひらがな変換 + 法人格除去
    doc_norm_h = _kata_to_hira(_normalize_corp_name(doc_l))
    if doc_norm_h:
        for c in candidates:
            c_norm_h = _kata_to_hira(_normalize_corp_name(c))
            if doc_norm_h in c_norm_h or c_norm_h in doc_norm_h:
                return 20

    # 4. 先頭3文字以上が一致
    if len(doc_l) >= 3:
        for c in candidates:
            if len(c) >= 3 and c[:3] == doc_l[:3]:
                return 10

    return 0


# ── メイン関数 ────────────────────────────────────────────────

def calculate_match_score(
    transaction: dict,
    document: dict,
    doc_type: str,  # "receipt" | "invoice"
    bank_display_patterns: Optional[list] = None,
) -> dict:
    """
    取引明細とドキュメントのマッチングスコアを計算する。

    返り値:
    {
        "score": 75,
        "score_breakdown": {"amount": 40, "date": 20, "name": 15},
        "is_candidate": True  # 60点以上なら True
    }
    """
    # ── 金額スコア ──────────────────────────────────────────────
    tx_amount = int(transaction.get("amount", 0))
    if doc_type == "receipt":
        doc_amount = int(document.get("amount", 0))
    else:
        doc_amount = int(document.get("total_amount", document.get("amount", 0)))

    amount_score = _calc_amount_score(tx_amount, doc_amount)
    if amount_score == 0:
        return {
            "score": 0,
            "score_breakdown": {"amount": 0, "date": 0, "name": 0},
            "is_candidate": False,
        }

    # ── 日付スコア ──────────────────────────────────────────────
    tx_date_str = transaction.get("transaction_date")
    if doc_type == "receipt":
        doc_date_str = document.get("date")
    else:
        # 請求書: issue_date と due_date のうち取引日付に近い方
        doc_date_str = _choose_closer_date(
            tx_date_str,
            document.get("issue_date"),
            document.get("due_date"),
        )

    date_score = _calc_date_score(tx_date_str, doc_date_str)

    # ── 名称スコア ──────────────────────────────────────────────
    tx_desc = transaction.get("description", "")
    tx_norm = transaction.get("normalized_name", "")
    if doc_type == "receipt":
        doc_name = document.get("payee", "")
    else:
        # received請求書は vendor_name（請求元）を使用、なければ client_name にフォールバック
        if document.get("document_type") == "received":
            doc_name = document.get("vendor_name") or document.get("client_name", "")
        else:
            doc_name = document.get("client_name", "")

    name_score = _calc_name_score(tx_desc, tx_norm, doc_name, bank_display_patterns)

    # date/name 両方が0点なら候補から除外
    # どちらか一方のみ0点の場合は金額スコアが高ければ候補に残す
    if date_score == 0 and name_score == 0:
        return {
            "score": 0,
            "score_breakdown": {"amount": amount_score, "date": date_score, "name": name_score},
            "is_candidate": False,
        }

    # ── 集計 ────────────────────────────────────────────────────
    total = amount_score + date_score + name_score
    return {
        "score": total,
        "score_breakdown": {
            "amount": amount_score,
            "date": date_score,
            "name": name_score,
        },
        "is_candidate": total >= 60,
    }
