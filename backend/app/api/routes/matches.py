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
from app.services.matching_score_service import calculate_match_score
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", summary="マッチング（消込）を作成する")
async def create_match(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Create a match linking transactions to receipts or invoices.

    Auto-matching rules:
      - If |difference| < AUTO_MATCH_THRESHOLD (¥1,000):
          差額を「支払手数料」として自動処理
      - If |difference| >= ¥1,000: requires manual difference_treatment in payload

    Payload:
      match_type: "receipt" | "invoice"
      transaction_ids: list of transaction IDs
      document_ids: list of receipt/invoice IDs
      difference_treatment: str (optional, overrides auto-detection)
      matched_by: "manual" | "ai"
      fiscal_period: str (YYYY-MM)
      auto_suggested: bool (候補から実行したか)
    """
    AUTO_MATCH_THRESHOLD = 1000

    transaction_ids = payload.get("transaction_ids", [])
    document_ids = payload.get("document_ids", [])
    match_type = payload.get("match_type", "receipt")
    fiscal_period = payload.get("fiscal_period", datetime.utcnow().strftime("%Y-%m"))
    collection = "receipts" if match_type == "receipt" else "invoices"

    # ── 金額集計 ───────────────────────────────────────
    t_total = 0
    first_tx = None
    for tid in transaction_ids:
        try:
            t = await ctx.db["transactions"].find_one({"_id": ObjectId(tid)})
            if t:
                t_total += t.get("amount", 0)
                if first_tx is None:
                    first_tx = t
        except Exception:
            pass
    # fallback: bank_transactions (legacy)
    if t_total == 0:
        for tid in transaction_ids:
            try:
                t = await ctx.db["bank_transactions"].find_one({"_id": ObjectId(tid)})
                if t:
                    t_total += t.get("amount", 0)
                    if first_tx is None:
                        first_tx = t
            except Exception:
                pass

    d_total = 0
    first_doc = None
    for did in document_ids:
        try:
            d = await ctx.db[collection].find_one({"_id": ObjectId(did)})
            if d:
                d_total += d.get("amount" if match_type == "receipt" else "total_amount", 0)
                if first_doc is None:
                    first_doc = d
        except Exception:
            pass

    difference = t_total - d_total
    abs_diff = abs(difference)

    # ── 差額処理の決定 ─────────────────────────────────
    auto_resolved = False
    difference_treatment = payload.get("difference_treatment")
    journal_entries = payload.get("journal_entries", [])

    if abs_diff == 0:
        difference_treatment = None
        auto_resolved = True
    elif abs_diff < AUTO_MATCH_THRESHOLD:
        auto_resolved = True
        if difference_treatment is None:
            difference_treatment = "支払手数料"
        if abs_diff > 0 and not journal_entries:
            journal_entries = [{
                "debit_account": difference_treatment if difference > 0 else "売掛金",
                "credit_account": "普通預金" if difference > 0 else difference_treatment,
                "amount": abs_diff,
                "description": f"差額自動処理（{difference_treatment}）¥{abs_diff:,}",
                "auto_generated": True,
            }]
    else:
        if not difference_treatment:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"差額が¥{abs_diff:,}あります（閾値¥{AUTO_MATCH_THRESHOLD:,}超）。"
                    f"差額の処理方法（difference_treatment）を指定してください。"
                ),
            )

    # ── スコア計算 ─────────────────────────────────────
    score_result: dict = {}
    if first_tx and first_doc:
        score_result = calculate_match_score(first_tx, first_doc, match_type)

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
        "score": score_result.get("score"),
        "score_breakdown": score_result.get("score_breakdown"),
        "auto_suggested": payload.get("auto_suggested", False),
        "user_action": "confirmed",
        "confirmed_at": datetime.utcnow(),
    }

    result = await ctx.db["matches"].insert_one(match_doc)

    # ── ステータス更新 ─────────────────────────────────
    for tid in transaction_ids:
        try:
            await ctx.db["transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "matched"}}
            )
        except Exception:
            pass
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


@router.get("/candidates", summary="消込候補ペアを取得する")
async def get_candidates(
    match_type: str = "receipt",
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    未消込の取引明細と未消込ドキュメントを全件取得し、
    スコアリングして is_candidate=True のペアのみ返す。

    Returns:
        [{ transaction, document, score, score_breakdown }, ...]
        score の降順でソート
    """
    # 未消込 transactions を取得
    tx_query: dict = {
        "corporate_id": ctx.corporate_id,
        "status": {"$nin": ["matched", "transferred"]},
    }
    if fiscal_period:
        tx_query["fiscal_period"] = fiscal_period

    txs = await ctx.db["transactions"].find(tx_query).to_list(length=1000)

    # auto_expense で処理済みの transaction_ids を除外
    auto_expense_matches = await ctx.db["matches"].find(
        {
            "corporate_id": ctx.corporate_id,
            "match_type": "auto_expense",
            "is_active": {"$ne": False},
        }
    ).to_list(length=1000)

    auto_expense_tx_ids = set()
    for m in auto_expense_matches:
        for tid in m.get("transaction_ids", []):
            auto_expense_tx_ids.add(tid)

    if auto_expense_tx_ids:
        txs = [t for t in txs if str(t["_id"]) not in auto_expense_tx_ids]

    # 未消込 documents を取得
    doc_collection = "receipts" if match_type == "receipt" else "invoices"
    doc_query: dict = {
        "corporate_id": ctx.corporate_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
        "is_deleted": {"$ne": True},
    }
    if fiscal_period:
        doc_query["fiscal_period"] = fiscal_period

    docs = await ctx.db[doc_collection].find(doc_query).to_list(length=1000)

    if not txs or not docs:
        return []

    # スコアリング（全組み合わせ）
    candidates = []
    for tx in txs:
        for doc in docs:
            result = calculate_match_score(tx, doc, match_type)
            if result["is_candidate"]:
                candidates.append({
                    "transaction": _serialize(dict(tx)),
                    "document": _serialize(dict(doc)),
                    "score": result["score"],
                    "score_breakdown": result["score_breakdown"],
                })

    # スコア降順でソート
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


@router.get("/candidates/by-applicant", summary="申請者別の消込候補を取得する")
async def get_candidates_by_applicant(
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    クレジットカード / 振込出金の取引明細と、申請者の領収書をAIファジーマッチングで紐付け候補を返す。

    Returns:
        [{ transaction, receipts: [{receipt, employee}], best_employee }]
    """
    from app.services.ai_service import AIService

    # 未消込のクレジット / 出金系 transactions
    tx_query: dict = {
        "corporate_id": ctx.corporate_id,
        "status": {"$nin": ["matched", "transferred"]},
        "transaction_type": {"$in": ["debit", "withdrawal", "credit_payment"]},
    }
    if fiscal_period:
        tx_query["fiscal_period"] = fiscal_period

    txs = await ctx.db["transactions"].find(tx_query).to_list(length=500)

    # 従業員一覧（bank_display_name があるもの優先）
    employees = await ctx.db["employees"].find(
        {"corporate_id": ctx.corporate_id, "status": {"$ne": "inactive"}}
    ).to_list(length=500)

    emp_map = {str(e["_id"]): e for e in employees}

    # 未消込の領収書（申請者IDあり）
    receipt_query: dict = {
        "corporate_id": ctx.corporate_id,
        "reconciliation_status": {"$in": ["unreconciled", None, ""]},
        "is_deleted": {"$ne": True},
        "applicant_id": {"$exists": True, "$ne": None},
    }
    if fiscal_period:
        receipt_query["fiscal_period"] = fiscal_period

    receipts = await ctx.db["receipts"].find(receipt_query).to_list(length=1000)

    if not txs or not receipts:
        return []

    # 申請者IDごとに領収書をグループ化
    receipts_by_applicant: dict = {}
    for r in receipts:
        aid = str(r.get("applicant_id", ""))
        if aid:
            receipts_by_applicant.setdefault(aid, []).append(r)

    # 従業員名リスト（AIマッチング用）
    emp_names = []
    for e in employees:
        display = e.get("bank_display_name") or e.get("name", "")
        if display:
            emp_names.append(display)
    emp_name_to_id = {}
    for e in employees:
        display = e.get("bank_display_name") or e.get("name", "")
        if display:
            emp_name_to_id[display] = str(e["_id"])

    results = []
    for tx in txs:
        desc = tx.get("description", "")
        if not desc or not emp_names:
            continue

        ai_result = await AIService.fuzzy_match_names(desc, emp_names)
        if not ai_result or not ai_result.get("match") or ai_result.get("confidence", 0) < 0.5:
            continue

        matched_name = ai_result["match"]
        emp_id = emp_name_to_id.get(matched_name)
        if not emp_id:
            continue

        emp = emp_map.get(emp_id)
        applicant_receipts = receipts_by_applicant.get(emp_id, [])

        results.append({
            "transaction": _serialize(dict(tx)),
            "employee": _serialize(dict(emp)) if emp else None,
            "receipts": [_serialize(dict(r)) for r in applicant_receipts],
            "confidence": ai_result.get("confidence"),
            "match_reason": ai_result.get("reason"),
        })

    return results


@router.get("", summary="マッチング一覧を取得する")
async def list_matches(
    match_type: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id, "is_active": {"$ne": False}}
    if match_type:
        query["match_type"] = match_type
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    cursor = ctx.db["matches"].find(query).sort("matched_at", -1)
    docs = await cursor.to_list(length=500)

    result = []
    for doc in docs:
        serialized = _serialize(doc)
        if doc.get("match_type") == "auto_expense":
            tx_ids = doc.get("transaction_ids", [])
            if tx_ids:
                try:
                    tx = await ctx.db["transactions"].find_one({"_id": ObjectId(tx_ids[0])})
                    if tx:
                        serialized["transaction_date"] = tx.get("transaction_date")
                        serialized["transaction_description"] = tx.get("description")
                except Exception:
                    pass
        result.append(serialized)
    return result


@router.get("/{match_id}", summary="マッチング詳細を取得する")
async def get_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")
    if doc.get("is_active") is False:
        raise HTTPException(status_code=404, detail="Match not found")
    return _serialize(doc)


@router.patch("/{match_id}", summary="マッチング情報を更新する")
async def patch_match(
    match_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """user_action などのメタデータを更新する。"""
    oid = parse_oid(match_id, "match")
    allowed_fields = {"user_action", "note"}
    update_data = {k: v for k, v in payload.items() if k in allowed_fields}

    if not update_data:
        raise HTTPException(status_code=400, detail="更新可能なフィールドがありません")

    result = await ctx.db["matches"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Match not found")

    updated = await ctx.db["matches"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{match_id}", summary="マッチングを解除する")
async def delete_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Unmatch: 論理削除（is_active: false）し、紐付いた transaction/document を unmatched に戻す。
    """
    match = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")

    collection = "receipts" if match.get("match_type") == "receipt" else "invoices"
    for tid in match.get("transaction_ids", []):
        try:
            await ctx.db["transactions"].update_one(
                {"_id": ObjectId(tid)}, {"$set": {"status": "unmatched"}}
            )
        except Exception:
            pass
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

    await ctx.db["matches"].update_one(
        {"_id": match["_id"]},
        {"$set": {"is_active": False, "inactivated_at": datetime.utcnow()}},
    )
    return {"status": "unmatched", "match_id": match_id}
