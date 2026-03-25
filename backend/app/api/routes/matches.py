from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    get_doc_or_404,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", summary="マッチング（消込）を作成する")
async def create_match(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Create a match linking bank transactions to receipts or invoices.

    Auto-matching rules:
      - If |difference| < AUTO_MATCH_THRESHOLD (¥1,000):
          difference > 0 and bank > doc → 差額を「雑損失」として自動処理
          difference > 0 and bank < doc → 差額を「雑収入」として自動処理
      - If |difference| >= ¥1,000: requires manual difference_treatment in payload

    Payload:
      match_type: "receipt" | "invoice"
      transaction_ids: list of bank_transaction IDs
      document_ids: list of receipt/invoice IDs
      difference_treatment: str (optional, overrides auto-detection)
      matched_by: "manual" | "ai"
      fiscal_period: str (YYYY-MM)
    """
    # ── 差額自動処理の閾値 ─────────────────────────────
    # TODO: 税理士確認後に変更可能。現在は雑損失/雑収入で処理。
    AUTO_MATCH_THRESHOLD = 1000  # ¥1,000未満は自動処理
    # ────────────────────────────────────────────────

    transaction_ids = payload.get("transaction_ids", [])
    document_ids = payload.get("document_ids", [])
    match_type = payload.get("match_type", "receipt")
    fiscal_period = payload.get("fiscal_period", datetime.utcnow().strftime("%Y-%m"))

    # ── 金額集計 ───────────────────────────────────────
    t_total = 0
    for tid in transaction_ids:
        try:
            t = await ctx.db["bank_transactions"].find_one({"_id": ObjectId(tid)})
            if t:
                t_total += t.get("amount", 0)
        except Exception:
            pass

    d_total = 0
    collection = "receipts" if match_type == "receipt" else "invoices"
    for did in document_ids:
        try:
            d = await ctx.db[collection].find_one({"_id": ObjectId(did)})
            if d:
                d_total += d.get("amount" if match_type == "receipt" else "total_amount", 0)
        except Exception:
            pass

    difference = t_total - d_total  # 符号あり: 正=銀行が多い, 負=書類が多い
    abs_diff = abs(difference)

    # ── 差額処理の決定 ─────────────────────────────────
    auto_resolved = False
    difference_treatment = payload.get("difference_treatment")

    if abs_diff == 0:
        difference_treatment = None  # 完全一致
        auto_resolved = True
    elif abs_diff < AUTO_MATCH_THRESHOLD:
        auto_resolved = True
        if difference_treatment is None:
            # 銀行引落 > 書類金額 → 差額は費用（雑損失）
            # 銀行引落 < 書類金額 → 差額は収益（雑収入）
            # ※ 税理士確認後に変更する場合は以下の2行を修正してください
            difference_treatment = "雑損失" if difference > 0 else "雑収入"

        # 自動仕訳エントリを生成
        journal_entries = payload.get("journal_entries", [])
        if abs_diff > 0 and not journal_entries:
            journal_entries = [{
                "debit_account": difference_treatment if difference > 0 else "売掛金",
                "credit_account": "普通預金" if difference > 0 else difference_treatment,
                "amount": abs_diff,
                "description": f"差額自動処理（{difference_treatment}）¥{abs_diff:,}",
                "auto_generated": True,
            }]
    else:
        # 差額が閾値以上 → 手動で difference_treatment を要求
        if not difference_treatment:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"差額が¥{abs_diff:,}あります（閾値¥{AUTO_MATCH_THRESHOLD:,}超）。"
                    f"差額の処理方法（difference_treatment）を指定してください。"
                ),
            )
        journal_entries = payload.get("journal_entries", [])

    match_doc = {
        "corporate_id": ctx.corporate_id,
        "match_type": match_type,
        "transaction_ids": transaction_ids,
        "document_ids": document_ids,
        "total_transaction_amount": t_total,
        "total_document_amount": d_total,
        "difference": abs_diff,
        "difference_direction": "bank_over" if difference > 0 else ("doc_over" if difference < 0 else "equal"),
        "difference_treatment": difference_treatment,
        "auto_resolved": auto_resolved,
        "matched_by": payload.get("matched_by", "manual"),
        "journal_entries": journal_entries,
        "fiscal_period": fiscal_period,
        "matched_at": datetime.utcnow(),
    }

    result = await ctx.db["matches"].insert_one(match_doc)

    # ── ステータス更新 ─────────────────────────────────
    for tid in transaction_ids:
        try:
            await ctx.db["bank_transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "matched"}}
            )
        except Exception:
            pass

    for did in document_ids:
        try:
            await ctx.db[collection].update_one(
                {"_id": ObjectId(did)}, {"$set": {"reconciliation_status": "reconciled"}}
            )
        except Exception:
            pass

    created = await ctx.db["matches"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", summary="マッチング一覧を取得する")
async def list_matches(
    match_type: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if match_type:
        query["match_type"] = match_type
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    cursor = ctx.db["matches"].find(query).sort("matched_at", -1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.get("/{match_id}", summary="マッチング詳細を取得する")
async def get_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")
    return _serialize(doc)


@router.delete("/{match_id}", summary="マッチングを解除する")
async def delete_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Unmatch: delete the match record and reset linked documents/transactions to unmatched.
    """
    match = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")

    # Restore statuses
    collection = "receipts" if match.get("match_type") == "receipt" else "invoices"
    for tid in match.get("transaction_ids", []):
        try:
            await ctx.db["bank_transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "unmatched"}}
            )
        except Exception:
            pass
    for did in match.get("document_ids", []):
        try:
            await ctx.db[collection].update_one(
                {"_id": ObjectId(did)},
                {"$set": {"reconciliation_status": "unreconciled", "approval_status": "approved"}}
            )
        except Exception:
            pass

    await ctx.db["matches"].delete_one({"_id": match["_id"]})
    return {"status": "unmatched", "match_id": match_id}
