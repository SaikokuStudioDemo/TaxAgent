from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from app.models.approval import ApprovalRuleCreate, ApprovalEventCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


# ─────────────── Approval Rules ───────────────

@router.get("/rules", summary="承認ルール一覧を取得する")
async def list_approval_rules(
    applies_to: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    query: dict = {"corporate_id": corporate_id}
    if applies_to:
        query["applies_to"] = applies_to

    cursor = db["approval_rules"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [_serialize(doc) for doc in docs]


@router.post("/rules", summary="承認ルールを作成する")
async def create_approval_rule(
    payload: ApprovalRuleCreate,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    doc = {
        **payload.model_dump(),
        "corporate_id": corporate_id,
        "created_at": datetime.utcnow(),
    }
    result = await db["approval_rules"].insert_one(doc)
    created = await db["approval_rules"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/rules/{rule_id}", summary="承認ルールを更新する")
async def update_approval_rule(
    rule_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(rule_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid rule ID")

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await db["approval_rules"].update_one(
        {"_id": oid, "corporate_id": corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    updated = await db["approval_rules"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/rules/{rule_id}", summary="承認ルールを削除する")
async def delete_approval_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(rule_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid rule ID")

    result = await db["approval_rules"].delete_one({"_id": oid, "corporate_id": corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Approval rule not found")
    return {"status": "deleted", "rule_id": rule_id}


# ─────────────── Approval Actions ───────────────

@router.post("/actions", summary="承認アクション（承認・却下・差戻し）を記録する")
async def record_approval_action(
    payload: ApprovalEventCreate,
    current_user: dict = Depends(get_current_user),
):
    from app.services.notification_service import notify_next_approver, notify_submitter

    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    db = get_database()

    if payload.action == "rejected" and not payload.comment:
        raise HTTPException(status_code=400, detail="差戻しの場合はコメントが必要です。")

    # Persist the event
    event_doc = {
        **payload.model_dump(),
        "corporate_id": corporate_id,
        "approver_id": user_id,
        "timestamp": datetime.utcnow(),
    }
    await db["approval_events"].insert_one(event_doc)

    # Update the parent document's review_status
    collection = "receipts" if payload.document_type == "receipt" else "invoices"
    try:
        doc_oid = ObjectId(payload.document_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc = await db[collection].find_one({"_id": doc_oid})
    rule_id = doc.get("approval_rule_id") if doc else None
    current_step = doc.get("current_step", 1) if doc else 1
    next_step = current_step + 1
    submitter_id = doc.get("submitted_by", doc.get("created_by", "")) if doc else ""
    doc_summary = f"¥{doc.get('amount', doc.get('total_amount', 0)):,}" if doc else ""

    if payload.action == "approved":
        all_approved = True
        if rule_id:
            try:
                rule = await db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
                if rule:
                    required_steps = [s["step"] for s in rule.get("steps", []) if s.get("required")]
                    if required_steps and next_step <= max(required_steps):
                        all_approved = False
            except Exception:
                pass

        if all_approved:
            await db[collection].update_one(
                {"_id": doc_oid},
                {"$set": {"review_status": "approved", "status": "approved"}},
            )
            # Notify the submitter that it's fully approved
            if submitter_id:
                await notify_submitter(
                    corporate_id=corporate_id,
                    document_type=payload.document_type,
                    document_id=payload.document_id,
                    submitter_id=submitter_id,
                    action="approved",
                    document_summary=doc_summary,
                )
        else:
            await db[collection].update_one(
                {"_id": doc_oid},
                {"$set": {"current_step": next_step}},
            )
            # Notify the next approver
            if rule_id:
                await notify_next_approver(
                    corporate_id=corporate_id,
                    document_type=payload.document_type,
                    document_id=payload.document_id,
                    current_step=next_step,
                    approval_rule_id=rule_id,
                    document_summary=doc_summary,
                )

    elif payload.action in ("rejected", "returned"):
        await db[collection].update_one(
            {"_id": doc_oid},
            {"$set": {"review_status": "rejected"}},
        )
        # Notify the submitter that it was rejected
        if submitter_id:
            await notify_submitter(
                corporate_id=corporate_id,
                document_type=payload.document_type,
                document_id=payload.document_id,
                submitter_id=submitter_id,
                action="rejected",
                document_summary=doc_summary,
            )

    return {"status": "recorded", "action": payload.action}
