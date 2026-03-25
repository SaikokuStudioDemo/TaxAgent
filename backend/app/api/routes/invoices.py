from fastapi import APIRouter, Depends, HTTPException, status
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
from app.models.invoice import InvoiceCreate, InvoiceInDB
import logging
from app.services.rule_evaluation_service import evaluate_approval_rules

logger = logging.getLogger(__name__)
router = APIRouter()

from app.api.routes.templates import router as templates_router
router.include_router(templates_router, prefix="/templates", tags=["invoice-templates"])


@router.post("", summary="請求書を作成する")
async def create_invoice(
    payload: InvoiceCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    # Determine fiscal period from issue_date (YYYY-MM-DD → YYYY-MM)
    fiscal_period = payload.issue_date[:7] if payload.issue_date else datetime.utcnow().strftime("%Y-%m")

    # Match approval rules
    rule_id, rule_steps = await evaluate_approval_rules(ctx.corporate_id, f"{payload.document_type}_invoice", payload.model_dump())

    requested_status = payload.approval_status or "draft"
    # 承認ルールなしで即送付 → 自動承認扱い
    is_auto_approved = requested_status == "sent" and rule_id is None

    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "created_by": ctx.user_id,
        "approval_status": "auto_approved" if is_auto_approved else requested_status,
        "reconciliation_status": "unreconciled",
        "current_step": 1,
        "approval_rule_id": rule_id,
        "approval_steps": rule_steps if rule_id else [],
        "attachments": payload.attachments or [],
        "fiscal_period": fiscal_period,
        "ai_extracted": False,
        "created_at": datetime.utcnow(),
        "paid_at": None,
    }

    result = await ctx.db["invoices"].insert_one(doc)
    created = await ctx.db["invoices"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", summary="請求書一覧を取得する")
async def list_invoices(
    document_type: Optional[str] = None,
    approval_status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id, "is_deleted": {"$ne": True}}
    if document_type:
        query["document_type"] = document_type
    if approval_status:
        query["approval_status"] = approval_status
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    cursor = ctx.db["invoices"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.get("/{invoice_id}", summary="請求書詳細を取得する")
async def get_invoice(
    invoice_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "invoices", invoice_id, ctx.corporate_id, "invoice")

    # Fetch approval events for this invoice
    events_cursor = ctx.db["approval_events"].find(
        {
            "document_id": invoice_id,
            "document_type": {"$in": ["invoice", "received_invoice", "issued_invoice"]}
        }
    ).sort("timestamp", 1)
    events = await events_cursor.to_list(length=100)
    serialized_events = [_serialize(e) for e in events]

    result = _serialize(doc)
    result["approval_history"] = serialized_events
    return result


@router.patch("/{invoice_id}", summary="請求書を更新する")
async def update_invoice(
    invoice_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(invoice_id, "invoice")

    # Disallow updating protected fields
    forbidden = {"corporate_id", "created_by", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    existing = await ctx.db["invoices"].find_one({"_id": oid, "corporate_id": ctx.corporate_id}, {"approval_rule_id": 1, "approval_status": 1})

    # pending_approval に遷移する場合はルールのステップを保存
    if update_data.get("approval_status") == "pending_approval" and existing:
        rule_id = existing.get("approval_rule_id")
        if rule_id:
            from app.services.rule_evaluation_service import get_rule_steps
            steps = await get_rule_steps(rule_id)
            update_data["approval_steps"] = steps


    result = await ctx.db["invoices"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    updated = await ctx.db["invoices"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{invoice_id}", summary="請求書を削除する")
async def delete_invoice(
    invoice_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(invoice_id, "invoice")

    result = await ctx.db["invoices"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": {"is_deleted": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {"status": "deleted", "invoice_id": invoice_id}


@router.post("/{invoice_id}/send", summary="請求書を送付する")
async def send_invoice(
    invoice_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """Mark invoice as sent. Actual email sending will be handled by the notification service."""
    invoice = await get_doc_or_404(ctx.db, "invoices", invoice_id, ctx.corporate_id, "invoice")

    if invoice.get("document_type") != "issued":
        raise HTTPException(status_code=400, detail="Only issued invoices can be sent.")

    await ctx.db["invoices"].update_one(
        {"_id": invoice["_id"]},
        {"$set": {"delivery_status": "sent"}},
    )
    return {"status": "sent", "invoice_id": invoice_id}


@router.post("/bulk-action", summary="複数の請求書に対して一括操作を行う")
async def bulk_action(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Perform bulk actions (delete, send) on multiple invoices.
    Payload: { "action": "delete" | "send", "ids": ["id1", "id2", ...] }
    """
    ids = payload.get("ids", [])
    action = payload.get("action")

    if not ids or not action:
        raise HTTPException(status_code=400, detail="Missing ids or action")

    try:
        oids = [ObjectId(i) for i in ids]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format in list")

    if action == "delete":
        await ctx.db["invoices"].update_many(
            {"_id": {"$in": oids}, "corporate_id": ctx.corporate_id},
            {"$set": {"is_deleted": True}}
        )
    elif action == "send":
        await ctx.db["invoices"].update_many(
            {"_id": {"$in": oids}, "corporate_id": ctx.corporate_id, "document_type": "issued"},
            {"$set": {"delivery_status": "sent"}}
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    return {"status": "success", "action": action, "count": len(ids)}
