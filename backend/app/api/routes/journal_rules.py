from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.journal_rule import JournalRuleCreate, JournalRuleUpdate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="自動仕訳ルール一覧を取得する")
async def list_journal_rules(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["journal_rules"].find({"corporate_id": ctx.corporate_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="自動仕訳ルールを作成する")
async def create_journal_rule(
    payload: JournalRuleCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = {**payload.model_dump(), "corporate_id": ctx.corporate_id, "created_at": datetime.utcnow()}
    result = await ctx.db["journal_rules"].insert_one(doc)
    created = await ctx.db["journal_rules"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/{rule_id}", summary="自動仕訳ルールを更新する")
async def update_journal_rule(
    rule_id: str,
    payload: JournalRuleUpdate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(rule_id, "journal_rule")
    update_data = payload.model_dump(exclude_unset=True)

    result = await ctx.db["journal_rules"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Journal rule not found")

    updated = await ctx.db["journal_rules"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{rule_id}", summary="自動仕訳ルールを削除する")
async def delete_journal_rule(
    rule_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(rule_id, "journal_rule")
    result = await ctx.db["journal_rules"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Journal rule not found")
    return {"status": "deleted", "rule_id": rule_id}
