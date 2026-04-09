from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    get_doc_or_404,
)
from app.models.master import ClientCreate, BankDisplayName
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="取引先一覧を取得する")
async def list_clients(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["clients"].find({"corporate_id": ctx.corporate_id}).sort("name", 1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="取引先を作成する")
async def create_client(
    payload: ClientCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = {**payload.model_dump(), "corporate_id": ctx.corporate_id, "created_at": datetime.utcnow()}
    result = await ctx.db["clients"].insert_one(doc)
    created = await ctx.db["clients"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/{client_id}", summary="取引先詳細を取得する")
async def get_client(
    client_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "clients", client_id, ctx.corporate_id, "client")
    client_doc = _serialize(doc)
    bank_accounts = await ctx.db["bank_accounts"].find(
        {"corporate_id": ctx.corporate_id, "client_id": client_id, "is_active": True}
    ).to_list(50)
    for a in bank_accounts:
        a["id"] = str(a.pop("_id"))
    return {**client_doc, "bank_accounts": bank_accounts}


@router.patch("/{client_id}", summary="取引先を更新する")
async def update_client(
    client_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(client_id, "client")

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await ctx.db["clients"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")

    updated = await ctx.db["clients"].find_one({"_id": oid})
    return _serialize(updated)


@router.post("/{client_id}/bank-display-names", summary="銀行表示名パターンを追加する")
async def add_bank_display_name(
    client_id: str,
    payload: BankDisplayName,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    取引先に銀行振込表示名パターンを追加する。
    マッチングスコアリングで使用される（取引明細の description との照合）。
    """
    oid = parse_oid(client_id, "client")
    entry = {
        "pattern": payload.pattern,
        "source": payload.source,
        "confidence": payload.confidence,
        "added_at": datetime.utcnow().isoformat(),
    }
    result = await ctx.db["clients"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$push": {"bank_display_names": entry}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    updated = await ctx.db["clients"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{client_id}/bank-display-names/{pattern}", summary="銀行表示名パターンを削除する")
async def remove_bank_display_name(
    client_id: str,
    pattern: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(client_id, "client")
    result = await ctx.db["clients"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$pull": {"bank_display_names": {"pattern": pattern}}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    updated = await ctx.db["clients"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{client_id}", summary="取引先を削除する")
async def delete_client(
    client_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(client_id, "client")

    result = await ctx.db["clients"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"status": "deleted", "client_id": client_id}
