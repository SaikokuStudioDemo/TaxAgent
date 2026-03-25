from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId as BsonObjectId

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.bank_account import BankAccountCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="銀行口座一覧を取得する")
async def list_bank_accounts(
    profile_id: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if profile_id:
        query["profile_id"] = profile_id
    cursor = ctx.db["bank_accounts"].find(query).sort("is_default", -1)
    docs = await cursor.to_list(length=100)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="銀行口座を作成する")
async def create_bank_account(
    payload: BankAccountCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    # If new account is default, unset others with same profile_id
    if payload.is_default:
        await ctx.db["bank_accounts"].update_many(
            {"corporate_id": ctx.corporate_id, "profile_id": payload.profile_id},
            {"$set": {"is_default": False}},
        )

    now = datetime.utcnow()
    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    result = await ctx.db["bank_accounts"].insert_one(doc)
    created = await ctx.db["bank_accounts"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/{account_id}", summary="銀行口座を更新する")
async def update_bank_account(
    account_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(account_id, "bank_account")

    # If setting as default, need to unset others with same profile_id first
    if payload.get("is_default"):
        # Find current account to get its profile_id
        current = await ctx.db["bank_accounts"].find_one(
            {"_id": oid, "corporate_id": ctx.corporate_id}
        )
        if not current:
            raise HTTPException(status_code=404, detail="Bank account not found")
        profile_id = payload.get("profile_id") or current.get("profile_id")
        await ctx.db["bank_accounts"].update_many(
            {"corporate_id": ctx.corporate_id, "profile_id": profile_id},
            {"$set": {"is_default": False}},
        )

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}
    update_data["updated_at"] = datetime.utcnow()

    result = await ctx.db["bank_accounts"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found")

    updated = await ctx.db["bank_accounts"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{account_id}", summary="銀行口座を削除する")
async def delete_bank_account(
    account_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(account_id, "bank_account")

    result = await ctx.db["bank_accounts"].delete_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return {"status": "deleted", "account_id": account_id}


@router.patch("/{account_id}/set-default", summary="銀行口座をデフォルトに設定する")
async def set_default_bank_account(
    account_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(account_id, "bank_account")

    # Find current account to get its profile_id
    current = await ctx.db["bank_accounts"].find_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if not current:
        raise HTTPException(status_code=404, detail="Bank account not found")

    profile_id = current.get("profile_id")

    # Unset all accounts with same profile_id
    await ctx.db["bank_accounts"].update_many(
        {"corporate_id": ctx.corporate_id, "profile_id": profile_id},
        {"$set": {"is_default": False, "updated_at": datetime.utcnow()}},
    )

    # Set this account as default
    await ctx.db["bank_accounts"].update_one(
        {"_id": oid},
        {"$set": {"is_default": True, "updated_at": datetime.utcnow()}},
    )

    updated = await ctx.db["bank_accounts"].find_one({"_id": oid})
    return _serialize(updated)
