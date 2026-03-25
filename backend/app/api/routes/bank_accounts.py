import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
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

# In-memory cache: key -> (value, expires_at)
_zengin_cache: dict = {}
_CACHE_TTL = 86400  # 24 hours in seconds


async def _zengin_get(url: str) -> dict:
    now = datetime.utcnow().timestamp()
    if url in _zengin_cache:
        val, expires = _zengin_cache[url]
        if now < expires:
            return val
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    _zengin_cache[url] = (data, now + _CACHE_TTL)
    return data


@router.get("/zengin/banks/{bank_code}", status_code=status.HTTP_200_OK)
async def lookup_bank(bank_code: str):
    """全銀協API: 金融機関名を取得"""
    try:
        data = await _zengin_get(f"https://bank.teraren.com/banks/{bank_code}.json")
        return {"bank_code": bank_code, "bank_name": data.get("name", "")}
    except Exception:
        raise HTTPException(status_code=404, detail=f"Bank code {bank_code} not found")


@router.get("/zengin/banks/{bank_code}/branches/{branch_code}", status_code=status.HTTP_200_OK)
async def lookup_branch(bank_code: str, branch_code: str):
    """全銀協API: 支店名を取得"""
    try:
        data = await _zengin_get(f"https://bank.teraren.com/banks/{bank_code}/branches/{branch_code}.json")
        return {"branch_code": branch_code, "branch_name": data.get("name", "")}
    except Exception:
        raise HTTPException(status_code=404, detail=f"Branch code {branch_code} not found")


def _scope_filter(doc: dict) -> dict:
    """Return the filter to unset is_default for sibling accounts."""
    if doc.get("owner_type") == "client":
        return {"client_id": doc["client_id"]}
    return {"profile_id": doc["profile_id"]}


@router.get("", summary="銀行口座一覧を取得する")
async def list_bank_accounts(
    profile_id: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id, "is_active": True}
    if profile_id:
        query["profile_id"] = profile_id
    elif client_id:
        query["client_id"] = client_id
    cursor = ctx.db["bank_accounts"].find(query).sort("is_default", -1)
    docs = await cursor.to_list(length=200)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="銀行口座を作成する")
async def create_bank_account(
    payload: BankAccountCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    if payload.is_default:
        scope = {"profile_id": payload.profile_id} if payload.owner_type == "corporate" else {"client_id": payload.client_id}
        await ctx.db["bank_accounts"].update_many(
            {"corporate_id": ctx.corporate_id, **scope},
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

    doc = await ctx.db["bank_accounts"].find_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Bank account not found")

    if payload.get("is_default"):
        scope = _scope_filter(doc)
        await ctx.db["bank_accounts"].update_many(
            {"corporate_id": ctx.corporate_id, **scope},
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

    current = await ctx.db["bank_accounts"].find_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if not current:
        raise HTTPException(status_code=404, detail="Bank account not found")

    scope = _scope_filter(current)
    await ctx.db["bank_accounts"].update_many(
        {"corporate_id": ctx.corporate_id, **scope},
        {"$set": {"is_default": False, "updated_at": datetime.utcnow()}},
    )

    await ctx.db["bank_accounts"].update_one(
        {"_id": oid},
        {"$set": {"is_default": True, "updated_at": datetime.utcnow()}},
    )

    updated = await ctx.db["bank_accounts"].find_one({"_id": oid})
    return _serialize(updated)
