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


# ---------------------------------------------------------------------------
# 全銀コード検索（ローカルDB）
# ---------------------------------------------------------------------------

@router.get("/zengin/banks/search", status_code=status.HTTP_200_OK)
async def search_banks(
    q: str = Query(..., min_length=1),
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """銀行名・カナで前方一致検索"""
    regex = {"$regex": f"^{q}", "$options": "i"}
    cursor = ctx.db["zengin_banks"].find(
        {"$or": [{"name": regex}, {"kana": regex}, {"hira": regex}]},
        {"_id": 0, "code": 1, "name": 1, "kana": 1},
    ).limit(20)
    docs = await cursor.to_list(length=20)
    return docs


@router.get("/zengin/banks/{bank_code}/branches/search", status_code=status.HTTP_200_OK)
async def search_branches(
    bank_code: str,
    q: str = Query(..., min_length=1),
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """支店名・カナで前方一致検索"""
    regex = {"$regex": f"^{q}", "$options": "i"}
    cursor = ctx.db["zengin_branches"].find(
        {"bank_code": bank_code, "$or": [{"name": regex}, {"kana": regex}, {"hira": regex}]},
        {"_id": 0, "code": 1, "name": 1, "kana": 1},
    ).limit(20)
    docs = await cursor.to_list(length=20)
    return docs


@router.get("/zengin/banks/{bank_code}/branches/{branch_code}", status_code=status.HTTP_200_OK)
async def lookup_branch(
    bank_code: str,
    branch_code: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """支店コードから支店名を取得"""
    doc = await ctx.db["zengin_branches"].find_one(
        {"bank_code": bank_code, "code": branch_code},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"Branch {bank_code}/{branch_code} not found")
    return {"branch_code": doc["code"], "branch_name": doc["name"], "kana": doc.get("kana", "")}


@router.get("/zengin/banks/{bank_code}", status_code=status.HTTP_200_OK)
async def lookup_bank(
    bank_code: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """銀行コードから銀行名を取得"""
    doc = await ctx.db["zengin_banks"].find_one({"code": bank_code}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Bank code {bank_code} not found")
    return {"bank_code": doc["code"], "bank_name": doc["name"], "kana": doc.get("kana", "")}


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
