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
from app.models.cash import CashAccountCreate, CashTransactionCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Cash Accounts ─────────────────────────────────────────────────────────────

@router.post("/cash-accounts", summary="現金口座を作成する")
async def create_cash_account(
    payload: CashAccountCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = {
        "corporate_id": ctx.corporate_id,
        "name": payload.name,
        "initial_balance": payload.initial_balance,
        "current_balance": payload.initial_balance,
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["cash_accounts"].insert_one(doc)
    created = await ctx.db["cash_accounts"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/cash-accounts", summary="現金口座一覧を取得する")
async def list_cash_accounts(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["cash_accounts"].find({"corporate_id": ctx.corporate_id}).sort("created_at", 1)
    docs = await cursor.to_list(length=100)
    return [_serialize(doc) for doc in docs]


@router.patch("/cash-accounts/{account_id}", summary="現金口座情報を更新する")
async def update_cash_account(
    account_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(account_id, "cash_account")
    allowed = {"name", "initial_balance"}
    update_data = {k: v for k, v in payload.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="更新可能なフィールドがありません")

    result = await ctx.db["cash_accounts"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cash account not found")

    updated = await ctx.db["cash_accounts"].find_one({"_id": oid})
    return _serialize(updated)


# ── Cash Transactions ─────────────────────────────────────────────────────────

@router.post("/cash-transactions", summary="現金取引を手動登録する")
async def create_cash_transaction(
    payload: CashTransactionCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    account_oid = parse_oid(payload.cash_account_id, "cash_account")
    account = await ctx.db["cash_accounts"].find_one({
        "_id": account_oid,
        "corporate_id": ctx.corporate_id,
    })
    if not account:
        raise HTTPException(status_code=404, detail="Cash account not found")

    doc = {
        "corporate_id": ctx.corporate_id,
        **payload.model_dump(),
        "status": "unmatched",
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["cash_transactions"].insert_one(doc)

    current_balance = account.get("current_balance", 0)
    if payload.direction == "income":
        new_balance = current_balance + payload.amount
    else:
        new_balance = current_balance - payload.amount
    await ctx.db["cash_accounts"].update_one(
        {"_id": account_oid},
        {"$set": {"current_balance": new_balance}},
    )

    created = await ctx.db["cash_transactions"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/cash-transactions", summary="現金取引一覧を取得する")
async def list_cash_transactions(
    cash_account_id: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    status: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if cash_account_id:
        query["cash_account_id"] = cash_account_id
    if fiscal_period:
        query["fiscal_period"] = fiscal_period
    if status:
        query["status"] = status

    cursor = ctx.db["cash_transactions"].find(query).sort("transaction_date", 1)
    docs = await cursor.to_list(length=2000)
    return [_serialize(doc) for doc in docs]


@router.patch("/cash-transactions/{transaction_id}", summary="現金取引を更新する")
async def update_cash_transaction(
    transaction_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(transaction_id, "cash_transaction")
    tx = await ctx.db["cash_transactions"].find_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if not tx:
        raise HTTPException(status_code=404, detail="Cash transaction not found")

    allowed = {"transaction_date", "amount", "direction", "description", "category",
               "fiscal_period", "note", "status"}
    update_data = {k: v for k, v in payload.items() if k in allowed}

    # 金額・方向が変わった場合は残高を差分更新
    old_amount = tx.get("amount", 0)
    old_direction = tx.get("direction", "expense")
    new_amount = update_data.get("amount", old_amount)
    new_direction = update_data.get("direction", old_direction)

    if new_amount != old_amount or new_direction != old_direction:
        account_oid = parse_oid(tx["cash_account_id"], "cash_account")
        account = await ctx.db["cash_accounts"].find_one({"_id": account_oid})
        if account:
            # 旧分を戻す
            balance = account.get("current_balance", 0)
            balance = balance - old_amount if old_direction == "income" else balance + old_amount
            # 新分を適用
            balance = balance + new_amount if new_direction == "income" else balance - new_amount
            await ctx.db["cash_accounts"].update_one(
                {"_id": account_oid},
                {"$set": {"current_balance": balance}},
            )

    await ctx.db["cash_transactions"].update_one({"_id": oid}, {"$set": update_data})
    updated = await ctx.db["cash_transactions"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/cash-transactions/{transaction_id}", summary="現金取引を削除する")
async def delete_cash_transaction(
    transaction_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(transaction_id, "cash_transaction")
    tx = await ctx.db["cash_transactions"].find_one({
        "_id": oid,
        "corporate_id": ctx.corporate_id,
    })
    if not tx:
        raise HTTPException(status_code=404, detail="Cash transaction not found")

    # 残高を戻す
    account_oid = parse_oid(tx["cash_account_id"], "cash_account")
    account = await ctx.db["cash_accounts"].find_one({"_id": account_oid})
    if account:
        balance = account.get("current_balance", 0)
        if tx.get("direction") == "income":
            new_balance = balance - tx.get("amount", 0)
        else:
            new_balance = balance + tx.get("amount", 0)
        await ctx.db["cash_accounts"].update_one(
            {"_id": account_oid},
            {"$set": {"current_balance": new_balance}},
        )

    await ctx.db["cash_transactions"].delete_one({"_id": oid})
    return {"status": "deleted", "transaction_id": transaction_id}


# ── Cash Matches ──────────────────────────────────────────────────────────────

@router.post("/cash-matches", summary="現金消込を作成する")
async def create_cash_match(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cash_tx_id = payload.get("cash_transaction_id")
    document_ids = payload.get("document_ids", [])
    transaction_ids = payload.get("transaction_ids", [])
    fiscal_period = payload.get("fiscal_period", datetime.utcnow().strftime("%Y-%m"))
    no_document_reason = payload.get("no_document_reason")

    cash_tx = await ctx.db["cash_transactions"].find_one({
        "_id": ObjectId(cash_tx_id),
        "corporate_id": ctx.corporate_id,
    })
    if not cash_tx:
        raise HTTPException(status_code=404, detail="Cash transaction not found")

    match_doc = {
        "corporate_id": ctx.corporate_id,
        "match_type": "cash",
        "cash_transaction_id": cash_tx_id,
        "transaction_ids": transaction_ids,
        "document_ids": document_ids,
        "no_document_reason": no_document_reason,
        "manual_category": payload.get("manual_category"),
        "manual_description": payload.get("manual_description"),
        "manual_amount": payload.get("manual_amount"),
        "matched_by": "manual",
        "fiscal_period": fiscal_period,
        "matched_at": datetime.utcnow(),
        "is_active": True,
        "user_action": "manual",
    }
    result = await ctx.db["matches"].insert_one(match_doc)

    await ctx.db["cash_transactions"].update_one(
        {"_id": ObjectId(cash_tx_id)},
        {"$set": {"status": "matched"}},
    )

    for did in document_ids:
        for col in ["receipts", "invoices"]:
            await ctx.db[col].update_one(
                {"_id": ObjectId(did), "corporate_id": ctx.corporate_id},
                {"$set": {"reconciliation_status": "reconciled"}},
            )

    for tid in transaction_ids:
        await ctx.db["transactions"].update_one(
            {"_id": ObjectId(tid), "corporate_id": ctx.corporate_id},
            {"$set": {"status": "matched"}},
        )

    created = await ctx.db["matches"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.delete("/cash-matches/{match_id}", summary="現金消込を解除する")
async def delete_cash_match(
    match_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    match = await get_doc_or_404(ctx.db, "matches", match_id, ctx.corporate_id, "match")

    await ctx.db["matches"].update_one(
        {"_id": match["_id"]},
        {"$set": {"is_active": False, "inactivated_at": datetime.utcnow()}},
    )

    cash_tx_id = match.get("cash_transaction_id")
    if cash_tx_id:
        await ctx.db["cash_transactions"].update_one(
            {"_id": ObjectId(cash_tx_id)},
            {"$set": {"status": "unmatched"}},
        )

    for did in match.get("document_ids", []):
        for col in ["receipts", "invoices"]:
            await ctx.db[col].update_one(
                {"_id": ObjectId(did), "corporate_id": ctx.corporate_id},
                {"$set": {"reconciliation_status": "unreconciled"}},
            )

    for tid in match.get("transaction_ids", []):
        await ctx.db["transactions"].update_one(
            {"_id": ObjectId(tid), "corporate_id": ctx.corporate_id},
            {"$set": {"status": "unmatched"}},
        )

    return {"status": "unmatched", "match_id": match_id}


# ── Cash Summary ──────────────────────────────────────────────────────────────

@router.get("/cash-summary", summary="現金未消込サマリーを取得する")
async def get_cash_summary(
    fiscal_period: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if fiscal_period:
        query["fiscal_period"] = fiscal_period

    all_txs = await ctx.db["cash_transactions"].find(query).to_list(length=1000)

    total_income  = sum(t["amount"] for t in all_txs if t.get("direction") == "income")
    total_expense = sum(t["amount"] for t in all_txs if t.get("direction") == "expense")
    unmatched     = [t for t in all_txs if t.get("status") != "matched"]
    matched       = [t for t in all_txs if t.get("status") == "matched"]

    accounts = await ctx.db["cash_accounts"].find(
        {"corporate_id": ctx.corporate_id}
    ).to_list(length=100)
    current_balance = sum(a.get("current_balance", 0) for a in accounts)

    return {
        "total_income":     total_income,
        "total_expense":    total_expense,
        "unmatched_count":  len(unmatched),
        "unmatched_amount": sum(t["amount"] for t in unmatched),
        "matched_count":    len(matched),
        "current_balance":  current_balance,
    }
