"""
税理士向けレビュー API
税理士法人が配下法人のデータを確認・コメントする。
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.helpers import serialize_doc, verify_tax_firm
from app.db.mongodb import get_database

logger = logging.getLogger(__name__)
router = APIRouter()


class CommentCreate(BaseModel):
    comment: str
    fiscal_period: str  # "YYYY-MM"


class CommentUpdate(BaseModel):
    comment: str


async def _verify_tax_firm_access(
    corporate_id: str,
    firebase_uid: str,
    db,
) -> dict:
    """
    税理士法人であること、かつ対象法人が自分の配下法人であることを確認する。
    corporate_id は配下法人の firebase_uid。
    """
    await verify_tax_firm(firebase_uid, db)
    corporate = await db["corporates"].find_one({
        "firebase_uid": corporate_id,
        "advising_tax_firm_id": firebase_uid,
    })
    if not corporate:
        raise HTTPException(status_code=404, detail="配下法人が見つかりません")
    return corporate


@router.get("/{corporate_id}/summary")
async def get_review_summary(
    corporate_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """配下法人のサマリー情報を返す。"""
    db = get_database()
    firebase_uid = current_user.get("uid")
    corporate = await _verify_tax_firm_access(corporate_id, firebase_uid, db)
    corporate_oid = str(corporate["_id"])

    profile = await db["company_profiles"].find_one({"corporate_id": corporate_oid})
    corporate_name = (
        profile.get("company_name", "") if profile
        else corporate.get("companyName", "")
    )

    (
        pending_receipts_count,
        pending_invoices_count,
        unreconciled_count,
        recent_notifications,
    ) = await asyncio.gather(
        db["receipts"].count_documents({
            "corporate_id": corporate_oid,
            "approval_status": "pending_approval",
            "is_deleted": {"$ne": True},
        }),
        db["invoices"].count_documents({
            "corporate_id": corporate_oid,
            "approval_status": "pending_approval",
            "is_deleted": {"$ne": True},
        }),
        db["receipts"].count_documents({
            "corporate_id": corporate_oid,
            "approval_status": "approved",
            "reconciliation_status": {"$ne": "reconciled"},
            "is_deleted": {"$ne": True},
        }),
        db["notifications"].find({
            "corporate_id": corporate_oid,
        }).sort("created_at", -1).limit(5).to_list(length=5),
    )

    alerts: List[str] = [
        n.get("message") or n.get("type", "")
        for n in recent_notifications
        if n.get("message") or n.get("type")
    ]

    return {
        "corporate_id": corporate_id,
        "corporate_name": corporate_name,
        "pending_receipts_count": pending_receipts_count,
        "pending_invoices_count": pending_invoices_count,
        "unreconciled_count": unreconciled_count,
        "recent_alerts": alerts,
    }


@router.get("/{corporate_id}/documents")
async def get_review_documents(
    corporate_id: str,
    fiscal_period: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    配下法人の承認済み書類一覧を返す（最大50件）。
    receipts と invoices を合算して日付降順で返す。
    corporate_id（firebase_uid）から MongoDB ObjectId を引いてフィルタする。
    """
    db = get_database()
    firebase_uid = current_user.get("uid")
    corporate = await _verify_tax_firm_access(corporate_id, firebase_uid, db)
    corporate_oid = str(corporate["_id"])

    base_query: Dict[str, Any] = {
        "corporate_id": corporate_oid,
        "approval_status": "approved",
        "is_deleted": {"$ne": True},
    }
    if fiscal_period:
        base_query["fiscal_period"] = fiscal_period

    receipts_raw, invoices_raw = await asyncio.gather(
        db["receipts"].find(base_query).sort("created_at", -1).to_list(length=50),
        db["invoices"].find(base_query).sort("created_at", -1).to_list(length=50),
    )

    documents: List[Dict[str, Any]] = []
    for r in receipts_raw:
        documents.append({
            "id": str(r["_id"]),
            "type": "receipt",
            "date": r.get("date", ""),
            "amount": r.get("amount") or r.get("total_amount") or 0,
            "vendor": r.get("payee") or r.get("vendor") or "",
            "status": r.get("approval_status", ""),
            "fiscal_period": r.get("fiscal_period", ""),
        })
    for inv in invoices_raw:
        documents.append({
            "id": str(inv["_id"]),
            "type": "invoice",
            "date": inv.get("issue_date", "") or inv.get("date", ""),
            "amount": inv.get("total_amount") or inv.get("amount") or 0,
            "vendor": inv.get("client_name") or inv.get("vendor") or "",
            "status": inv.get("approval_status", ""),
            "fiscal_period": inv.get("fiscal_period", ""),
        })

    documents.sort(key=lambda d: d.get("date", ""), reverse=True)
    return documents[:50]


@router.get("/{corporate_id}/comments")
async def get_review_comments(
    corporate_id: str,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """コメント一覧を新しい順で返す。"""
    db = get_database()
    firebase_uid = current_user.get("uid")
    await _verify_tax_firm_access(corporate_id, firebase_uid, db)

    cursor = db["tax_firm_reviews"].find(
        {"corporate_id": corporate_id}
    ).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return [serialize_doc(doc) for doc in docs]


@router.post("/{corporate_id}/comments", status_code=201)
async def post_review_comment(
    corporate_id: str,
    payload: CommentCreate,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """コメントを登録する。created_by は firebase_uid で管理する。"""
    db = get_database()
    firebase_uid = current_user.get("uid")
    await _verify_tax_firm_access(corporate_id, firebase_uid, db)

    if not payload.comment or not payload.comment.strip():
        raise HTTPException(status_code=400, detail="comment は必須です")

    now = datetime.utcnow()
    result = await db["tax_firm_reviews"].insert_one({
        "tax_firm_id": firebase_uid,
        "corporate_id": corporate_id,
        "fiscal_period": payload.fiscal_period,
        "comment": payload.comment.strip(),
        "created_by": firebase_uid,
        "created_at": now,
        "updated_at": now,
    })
    doc = await db["tax_firm_reviews"].find_one({"_id": result.inserted_id})
    return serialize_doc(doc)


@router.put("/{corporate_id}/comments/{comment_id}")
async def update_review_comment(
    corporate_id: str,
    comment_id: str,
    payload: CommentUpdate,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """自分のコメントのみ更新できる（created_by == firebase_uid）。"""
    db = get_database()
    firebase_uid = current_user.get("uid")
    await _verify_tax_firm_access(corporate_id, firebase_uid, db)

    try:
        oid = ObjectId(comment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="無効なコメントIDです")

    existing = await db["tax_firm_reviews"].find_one({
        "_id": oid,
        "corporate_id": corporate_id,
    })
    if not existing:
        raise HTTPException(status_code=404, detail="コメントが見つかりません")
    if existing.get("created_by") != firebase_uid:
        raise HTTPException(status_code=403, detail="自分のコメントのみ編集できます")

    await db["tax_firm_reviews"].update_one(
        {"_id": oid},
        {"$set": {"comment": payload.comment, "updated_at": datetime.utcnow()}},
    )
    doc = await db["tax_firm_reviews"].find_one({"_id": oid})
    return serialize_doc(doc)


@router.delete("/{corporate_id}/comments/{comment_id}", status_code=204)
async def delete_review_comment(
    corporate_id: str,
    comment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """自分のコメントのみ物理削除できる（created_by == firebase_uid）。"""
    db = get_database()
    firebase_uid = current_user.get("uid")
    await _verify_tax_firm_access(corporate_id, firebase_uid, db)

    try:
        oid = ObjectId(comment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="無効なコメントIDです")

    existing = await db["tax_firm_reviews"].find_one({
        "_id": oid,
        "corporate_id": corporate_id,
    })
    if not existing:
        raise HTTPException(status_code=404, detail="コメントが見つかりません")
    if existing.get("created_by") != firebase_uid:
        raise HTTPException(status_code=403, detail="自分のコメントのみ削除できます")

    await db["tax_firm_reviews"].delete_one({"_id": oid})
