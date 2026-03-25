from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    get_doc_or_404,
)
from app.models.transaction import ReceiptCreate
import logging
from app.services.rule_evaluation_service import evaluate_approval_rules

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────── Batch Submit (existing feature, kept for backwards compat) ───────────────

class BatchSubmitPayload:
    pass

@router.post("/batch", summary="領収書を一括提出する（AI抽出用）")
async def submit_receipts_batch(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Batch submit receipts (e.g., from AI extraction).
    Kept for backwards compatibility with the frontend AI upload flow.
    """
    receipts_data = payload.get("receipts", [])
    if not receipts_data:
        raise HTTPException(status_code=400, detail="No receipts provided.")

    docs_to_insert = []
    for r in receipts_data:
        amount = r.get("amount", 0)
        fiscal_period = r.get("date", datetime.utcnow().strftime("%Y-%m"))[:7]
        rule_id, _ = await evaluate_approval_rules(ctx.corporate_id, "receipt", r)
        doc = {
            "corporate_id": ctx.corporate_id,
            "submitted_by": ctx.user_id,
            "document_type": "receipt",
            "date": r.get("date", ""),
            "amount": amount,
            "tax_rate": r.get("taxRate", r.get("tax_rate", 10)),
            "payee": r.get("payee", ""),
            "category": r.get("category", ""),
            "payment_method": r.get("payment_method", "立替"),
            "line_items": r.get("line_items", []),
            "attachments": r.get("attachments", []),
            "fiscal_period": fiscal_period,
            "ai_extracted": True,
            "approval_status": "pending_approval",
            "reconciliation_status": "unreconciled",
            "approval_rule_id": rule_id,
            "current_step": 1,
            "created_at": datetime.utcnow(),
        }
        docs_to_insert.append(doc)

    result = await ctx.db["receipts"].insert_many(docs_to_insert)
    return {
        "status": "success",
        "message": f"{len(docs_to_insert)} receipts submitted",
        "inserted_count": len(docs_to_insert),
    }


# ─────────────── Single Receipt CRUD ───────────────

@router.post("", summary="領収書を1件作成する")
async def create_receipt(
    payload: ReceiptCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    rule_id, _ = await evaluate_approval_rules(ctx.corporate_id, "receipt", payload.model_dump())
    fiscal_period = payload.date[:7] if payload.date else datetime.utcnow().strftime("%Y-%m")

    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "submitted_by": ctx.user_id,
        "document_type": "receipt",
        "approval_status": "pending_approval",
        "reconciliation_status": "unreconciled",
        "approval_rule_id": rule_id,
        "current_step": 1,
        "fiscal_period": fiscal_period,
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["receipts"].insert_one(doc)
    created = await ctx.db["receipts"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", summary="領収書一覧を取得する")
async def list_receipts(
    approval_status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    submitted_by: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if approval_status:
        query["approval_status"] = approval_status
    if fiscal_period:
        query["fiscal_period"] = fiscal_period
    if submitted_by == "me":
        query["submitted_by"] = ctx.user_id

    cursor = ctx.db["receipts"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.get("/pending-for-me", summary="自分が承認すべき領収書一覧を取得する")
async def list_pending_for_me(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Returns receipts where the current user is the expected approver
    at the current_step, based on their role and the applied approval_rule.
    """
    # Get current user's role
    employee = await ctx.db["employees"].find_one({"firebase_uid": ctx.firebase_uid})
    user_role = employee.get("role", "staff") if employee else "admin"

    # Get all pending receipts for this corporate
    cursor = ctx.db["receipts"].find({
        "corporate_id": ctx.corporate_id,
        "approval_status": "pending_approval",
    })
    all_pending = await cursor.to_list(length=500)

    my_pending = []
    for receipt in all_pending:
        rule_id = receipt.get("approval_rule_id")
        current_step = receipt.get("current_step", 1)
        if not rule_id:
            continue
        try:
            rule = await ctx.db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
        except Exception:
            continue
        if not rule:
            continue
        steps = rule.get("steps", [])
        matching_step = next((s for s in steps if s.get("step") == current_step), None)
        if matching_step and matching_step.get("role") == user_role:
            my_pending.append(receipt)

    return [_serialize(r) for r in my_pending]


@router.get("/{receipt_id}", summary="領収書詳細を取得する")
async def get_receipt(
    receipt_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "receipts", receipt_id, ctx.corporate_id, "receipt")

    # Enrich with approval history
    events_cursor = ctx.db["approval_events"].find(
        {"document_id": receipt_id, "document_type": "receipt"}
    ).sort("timestamp", 1)
    events = await events_cursor.to_list(length=100)

    result = _serialize(doc)
    result["approval_history"] = [_serialize(e) for e in events]
    return result


@router.patch("/{receipt_id}", summary="領収書を更新する")
async def update_receipt(
    receipt_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(receipt_id, "receipt")

    # Re-evaluate approval rule if amount changed
    if "amount" in payload:
        new_rule_id = await _find_matching_rule(ctx.db, ctx.corporate_id, payload["amount"])
        payload["approval_rule_id"] = new_rule_id

    forbidden = {"corporate_id", "submitted_by", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await ctx.db["receipts"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Receipt not found")

    updated = await ctx.db["receipts"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{receipt_id}", summary="領収書を削除する")
async def delete_receipt(
    receipt_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(receipt_id, "receipt")

    result = await ctx.db["receipts"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"status": "deleted", "receipt_id": receipt_id}
