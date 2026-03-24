from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from app.models.invoice import InvoiceCreate, InvoiceInDB
import logging
from app.services.rule_evaluation_service import evaluate_approval_rules

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(doc: dict) -> dict:
    """Convert ObjectId to string for JSON serialization."""
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("", summary="請求書を作成する")
async def create_invoice(
    payload: InvoiceCreate,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    db = get_database()

    # Determine fiscal period from issue_date (YYYY-MM-DD → YYYY-MM)
    fiscal_period = payload.issue_date[:7] if payload.issue_date else datetime.utcnow().strftime("%Y-%m")

    # Match approval rules
    rule_id, _ = await evaluate_approval_rules(corporate_id, f"{payload.direction}_invoice", payload.model_dump())

    doc = {
        **payload.model_dump(),
        "corporate_id": corporate_id,
        "created_by": user_id,
        "status": payload.status or "draft",
        "review_status": "unreviewed",
        "current_step": 1,
        "approval_rule_id": rule_id,
        "attachments": payload.attachments or [],
        "fiscal_period": fiscal_period,
        "ai_extracted": False,
        "created_at": datetime.utcnow(),
        "paid_at": None,
    }

    result = await db["invoices"].insert_one(doc)
    created = await db["invoices"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", summary="請求書一覧を取得する")
async def list_invoices(
    direction: Optional[str] = None,
    review_status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    query: dict = {"corporate_id": corporate_id, "is_deleted": {"$ne": True}}
    if direction:
        query["direction"] = direction
    if review_status:
        query["review_status"] = review_status
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    cursor = db["invoices"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.get("/{invoice_id}", summary="請求書詳細を取得する")
async def get_invoice(
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(invoice_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid invoice ID")

    doc = await db["invoices"].find_one({"_id": oid, "corporate_id": corporate_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Fetch approval events for this invoice
    events_cursor = db["approval_events"].find(
        {"document_id": invoice_id, "document_type": "invoice"}
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
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(invoice_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid invoice ID")

    # Disallow updating protected fields
    forbidden = {"corporate_id", "created_by", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await db["invoices"].update_one(
        {"_id": oid, "corporate_id": corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    updated = await db["invoices"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{invoice_id}", summary="請求書を削除する")
async def delete_invoice(
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(invoice_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid invoice ID")

    result = await db["invoices"].update_one(
        {"_id": oid, "corporate_id": corporate_id},
        {"$set": {"is_deleted": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {"status": "deleted", "invoice_id": invoice_id}


@router.post("/{invoice_id}/send", summary="請求書を送付する")
async def send_invoice(
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark invoice as sent. Actual email sending will be handled by the notification service."""
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(invoice_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid invoice ID")

    invoice = await db["invoices"].find_one({"_id": oid, "corporate_id": corporate_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.get("direction") != "issued":
        raise HTTPException(status_code=400, detail="Only issued invoices can be sent.")

    await db["invoices"].update_one(
        {"_id": oid},
        {"$set": {"status": "sent"}},
    )
    return {"status": "sent", "invoice_id": invoice_id}


@router.post("/bulk-action", summary="複数の請求書に対して一括操作を行う")
async def bulk_action(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Perform bulk actions (delete, send) on multiple invoices.
    Payload: { "action": "delete" | "send", "ids": ["id1", "id2", ...] }
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    ids = payload.get("ids", [])
    action = payload.get("action")

    if not ids or not action:
        raise HTTPException(status_code=400, detail="Missing ids or action")

    try:
        oids = [ObjectId(i) for i in ids]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format in list")

    if action == "delete":
        await db["invoices"].update_many(
            {"_id": {"$in": oids}, "corporate_id": corporate_id},
            {"$set": {"is_deleted": True}}
        )
    elif action == "send":
        await db["invoices"].update_many(
            {"_id": {"$in": oids}, "corporate_id": corporate_id, "direction": "issued", "status": "draft"},
            {"$set": {"status": "sent"}}
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    return {"status": "success", "action": action, "count": len(ids)}
