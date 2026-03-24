from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.master import CompanyProfileCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="自社プロファイル一覧を取得する")
async def list_profiles(ctx: CorporateContext = Depends(get_corporate_context)):
    cursor = ctx.db["company_profiles"].find({"corporate_id": ctx.corporate_id}).sort("is_default", -1)
    docs = await cursor.to_list(length=50)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="自社プロファイルを作成する")
async def create_profile(
    payload: CompanyProfileCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    # If new profile is default, remove default from others
    if payload.is_default:
        await ctx.db["company_profiles"].update_many(
            {"corporate_id": ctx.corporate_id},
            {"$set": {"is_default": False}},
        )

    doc = {**payload.model_dump(), "corporate_id": ctx.corporate_id, "created_at": datetime.utcnow()}
    result = await ctx.db["company_profiles"].insert_one(doc)
    created = await ctx.db["company_profiles"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/{profile_id}", summary="自社プロファイルを更新する")
async def update_profile(
    profile_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(profile_id, "profile")

    if payload.get("is_default"):
        await ctx.db["company_profiles"].update_many(
            {"corporate_id": ctx.corporate_id},
            {"$set": {"is_default": False}},
        )

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await ctx.db["company_profiles"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")

    updated = await ctx.db["company_profiles"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{profile_id}", summary="自社プロファイルを削除する")
async def delete_profile(
    profile_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(profile_id, "profile")

    result = await ctx.db["company_profiles"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "deleted", "profile_id": profile_id}
