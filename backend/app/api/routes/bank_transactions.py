from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.post("", summary="銀行・カード明細を一括インポートする")
async def import_transactions(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Bulk import bank or card transactions from a parsed CSV/statement.
    Payload: { source_type: "bank"|"card", account_name: str, transactions: [...] }
    """
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    source_type = payload.get("source_type", "bank")
    account_name = payload.get("account_name", "")
    transactions = payload.get("transactions", [])

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions provided.")

    docs = []
    for t in transactions:
        date_str = t.get("transaction_date", t.get("date", ""))
        fiscal_period = date_str[:7] if date_str else datetime.utcnow().strftime("%Y-%m")
        docs.append({
            "corporate_id": corporate_id,
            "source_type": source_type,
            "account_name": account_name,
            "transaction_date": date_str,
            "description": t.get("description", ""),
            "normalized_name": t.get("normalized_name"),
            "amount": t.get("amount", 0),
            "direction": t.get("direction", "debit"),
            "status": "unmatched",
            "fiscal_period": fiscal_period,
            "imported_at": datetime.utcnow(),
        })

    result = await db["bank_transactions"].insert_many(docs)
    
    # AI Matching Hook: Fetch candidates for fuzzy matching
    try:
        clients_cursor = db["clients"].find({"corporate_id": corporate_id})
        clients = await clients_cursor.to_list(length=1000)
        client_names = [c.get("name") for c in clients if c.get("name")]
        
        # Note: In a real background task, we would run AI matching here
        # for doc in docs:
        #    match = await AIService.fuzzy_match_names(doc["description"], client_names)
        #    if match and match["confidence"] > 0.8:
        #        ... flag as candidate ...
    except Exception as e:
        logger.error(f"Post-import AI analysis failed: {e}")

    return {
        "status": "success",
        "imported_count": len(result.inserted_ids),
    }


@router.get("", summary="銀行・カード明細一覧を取得する")
async def list_transactions(
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    query: dict = {"corporate_id": corporate_id}
    if source_type:
        query["source_type"] = source_type
    if status:
        query["status"] = status
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    cursor = db["bank_transactions"].find(query).sort("transaction_date", -1)
    docs = await cursor.to_list(length=1000)
    return [_serialize(doc) for doc in docs]


@router.delete("/{transaction_id}", summary="明細を削除する")
async def delete_transaction(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(transaction_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")

    result = await db["bank_transactions"].delete_one({
        "_id": oid,
        "corporate_id": corporate_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted", "transaction_id": transaction_id}
