from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", summary="銀行・カード明細を一括インポートする")
async def import_transactions(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Bulk import bank or card transactions from a parsed CSV/statement.
    Payload: { source_type: "bank"|"card", account_name: str, transactions: [...] }
    """
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
            "corporate_id": ctx.corporate_id,
            "source_type": source_type,
            "account_name": account_name,
            "transaction_date": date_str,
            "description": t.get("description", ""),
            "normalized_name": t.get("normalized_name"),
            "amount": t.get("amount", 0),
            "transaction_type": t.get("transaction_type", t.get("direction", "debit")),
            "status": "unmatched",
            "fiscal_period": fiscal_period,
            "imported_at": datetime.utcnow(),
        })

    result = await ctx.db["bank_transactions"].insert_many(docs)

    # AI Matching Hook: Fetch candidates for fuzzy matching
    try:
        clients_cursor = ctx.db["clients"].find({"corporate_id": ctx.corporate_id})
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
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if source_type:
        query["source_type"] = source_type
    if status:
        query["status"] = status
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    cursor = ctx.db["bank_transactions"].find(query).sort("transaction_date", -1)
    docs = await cursor.to_list(length=1000)
    return [_serialize(doc) for doc in docs]


@router.delete("/{transaction_id}", summary="明細を削除する")
async def delete_transaction(
    transaction_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(transaction_id, "transaction")

    result = await ctx.db["bank_transactions"].delete_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted", "transaction_id": transaction_id}
