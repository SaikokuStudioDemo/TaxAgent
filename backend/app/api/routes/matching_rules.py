from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.matching_rule import MatchingRuleCreate, MatchingRuleUpdate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="消込条件ルール一覧を取得する")
async def list_matching_rules(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["matching_rules"].find({"corporate_id": ctx.corporate_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="消込条件ルールを作成する")
async def create_matching_rule(
    payload: MatchingRuleCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = {**payload.model_dump(), "corporate_id": ctx.corporate_id, "created_at": datetime.utcnow()}
    result = await ctx.db["matching_rules"].insert_one(doc)
    created = await ctx.db["matching_rules"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/{rule_id}", summary="消込条件ルールを更新する")
async def update_matching_rule(
    rule_id: str,
    payload: MatchingRuleUpdate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(rule_id, "matching_rule")
    update_data = payload.model_dump(exclude_unset=True)

    result = await ctx.db["matching_rules"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Matching rule not found")

    updated = await ctx.db["matching_rules"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{rule_id}", summary="消込条件ルールを削除する")
async def delete_matching_rule(
    rule_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(rule_id, "matching_rule")
    result = await ctx.db["matching_rules"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Matching rule not found")
    return {"status": "deleted", "rule_id": rule_id}
