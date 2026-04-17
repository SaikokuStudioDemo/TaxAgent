"""
差額・手数料ズレの原因候補を提示するサービス。
設計ドキュメント Section 13.4 の4パターンに対応。
DB への書き込みは行わない（提案のみ）。
"""
import logging
from typing import List, Dict, Any, Optional

from bson import ObjectId

from app.db.mongodb import get_database

logger = logging.getLogger(__name__)

# 手数料の典型的な金額パターン（円）
COMMON_FEE_AMOUNTS = [110, 220, 330, 440, 550, 660, 770]


async def analyze_difference(
    corporate_id: str,
    transaction_id: str,
    document_ids: List[str],
    doc_type: str,  # "receipt" | "invoice"
) -> Dict[str, Any]:
    """
    取引と書類の差額を分析して原因候補を返す。
    4パターン（手数料・まとめ・相殺・一部）を検出する。
    DB への書き込みは行わない。
    """
    # ⑤ doc_type バリデーション
    collection_map = {"receipt": "receipts", "invoice": "invoices"}
    if doc_type not in collection_map:
        return {"error": f"Unknown doc_type: {doc_type}"}
    collection = collection_map[doc_type]
    amount_field = "amount" if doc_type == "receipt" else "total_amount"

    db = get_database()

    # 取引データを取得
    try:
        tx = await db["transactions"].find_one(
            {"_id": ObjectId(transaction_id), "corporate_id": corporate_id}
        )
    except Exception:
        return {"error": "取引データが見つかりません"}

    if not tx:
        return {"error": "取引データが見つかりません"}

    # ③ deposit_amount → withdrawal_amount → amount の順でフォールバック
    tx_amount: int = int(
        tx.get("deposit_amount")
        or tx.get("withdrawal_amount")
        or tx.get("amount")
        or 0
    )

    # 書類データを取得（corporate_id スコープで絞る）
    docs: List[dict] = []
    for doc_id in document_ids:
        try:
            doc = await db[collection].find_one(
                {"_id": ObjectId(doc_id), "corporate_id": corporate_id}
            )
            if doc:
                docs.append(doc)
        except Exception:
            continue

    if not docs:
        return {"error": "書類データが見つかりません"}

    doc_total: int = sum(int(d.get(amount_field) or 0) for d in docs)
    difference: int = tx_amount - doc_total
    abs_diff: int = abs(difference)

    candidates: List[Dict[str, Any]] = []

    # ── パターン1：振込手数料差引 ──────────────────────────────────────────
    # 差額が1000円以内の場合
    if 0 < abs_diff <= 1000:
        matched_fee: Optional[int] = None
        for fee in COMMON_FEE_AMOUNTS:
            if abs(abs_diff - fee) <= 10:
                matched_fee = fee
                break

        if matched_fee:
            desc = (
                f"手数料差引の可能性があります。"
                f"差額{abs_diff:,}円は振込手数料（{matched_fee:,}円）に近い金額です。"
            )
        else:
            desc = f"手数料差引の可能性があります。差額は{abs_diff:,}円です。"

        candidates.append({
            "pattern": "bank_fee",
            "label": "振込手数料差引",
            "description": desc,
            "suggested_action": "許容範囲内で消込しますか？",
            "difference": difference,
        })

    # ── パターン2：複数請求まとめ振込 ──────────────────────────────────────
    if abs_diff > 0:
        matched_combo = await _find_matching_combination(
            db, corporate_id, collection, amount_field,
            tx_amount, exclude_ids=document_ids,
        )
        if matched_combo:
            total_labels = "・".join(
                f"¥{int(d.get(amount_field) or 0):,}" for d in matched_combo
            )
            candidates.append({
                "pattern": "combined_payment",
                "label": "複数請求まとめ振込",
                "description": (
                    f"{len(matched_combo)}件の書類との合計が"
                    f"取引金額と一致します。（{total_labels}）"
                ),
                "suggested_action": "まとめて消込しますか？",
                "additional_document_ids": [str(d["_id"]) for d in matched_combo],
                "difference": 0,
            })

    # ── パターン3：相殺処理 ────────────────────────────────────────────────
    if abs_diff > 0:
        offsetting = await _find_offsetting_document(db, corporate_id, abs_diff)
        if offsetting:
            candidates.append({
                "pattern": "offset",
                "label": "相殺処理",
                "description": (
                    f"買掛金との相殺の可能性があります。"
                    f"差額{abs_diff:,}円が未消込書類の金額と一致します。"
                ),
                "suggested_action": "相殺処理しますか？",
                "difference": difference,
            })

    # ── パターン4：一部入金 ────────────────────────────────────────────────
    if difference < 0 and abs_diff > 1000:
        candidates.append({
            "pattern": "partial_payment",
            "label": "一部入金",
            "description": (
                f"一部入金の可能性があります。"
                f"請求{doc_total:,}円に対して入金{tx_amount:,}円"
                f"（差額{abs_diff:,}円）です。"
            ),
            "suggested_action": "残額は次回回収として処理しますか？",
            "remaining_amount": abs_diff,
            "difference": difference,
        })

    return {
        "transaction_id": transaction_id,
        "transaction_amount": tx_amount,
        "document_total": doc_total,
        "difference": difference,
        "candidates": candidates,
        "has_candidates": len(candidates) > 0,
    }


async def _find_matching_combination(
    db: Any,
    corporate_id: str,
    collection: str,
    amount_field: str,
    target_amount: int,
    exclude_ids: List[str],
    max_docs: int = 5,
) -> List[dict]:
    """
    target_amount に合計金額が一致する未消込書類の2件組み合わせを探す。
    計算量削減のため最大 max_docs 件の組み合わせのみ検索する。
    """
    exclude_oids: List[ObjectId] = []
    for eid in exclude_ids:
        try:
            exclude_oids.append(ObjectId(eid))
        except Exception:
            pass

    # ④ .limit() を削除して to_list(length=50) のみに統一
    candidates = await db[collection].find({
        "corporate_id": corporate_id,
        "approval_status": "approved",
        "reconciliation_status": {"$nin": ["reconciled"]},
        "_id": {"$nin": exclude_oids},
    }).to_list(length=50)

    # 2件の組み合わせで合計が target_amount に一致するものを探す
    search_limit = min(len(candidates), max_docs)
    for i in range(search_limit):
        for j in range(i + 1, search_limit):
            total = (
                int(candidates[i].get(amount_field) or 0)
                + int(candidates[j].get(amount_field) or 0)
            )
            if total == target_amount:
                return [candidates[i], candidates[j]]
    return []


async def _find_offsetting_document(
    db: Any,
    corporate_id: str,
    amount: int,
) -> Optional[dict]:
    """相殺候補となる書類（指定金額と一致する未消込の受領請求書）を探す。"""
    return await db["invoices"].find_one({
        "corporate_id": corporate_id,
        "document_type": "received",
        "approval_status": "approved",
        "reconciliation_status": {"$nin": ["reconciled"]},
        "total_amount": amount,
    })
