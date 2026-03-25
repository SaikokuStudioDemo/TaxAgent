from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.project import ProjectCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", summary="プロジェクト一覧を取得する")
async def list_projects(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["projects"].find(
        {"corporate_id": ctx.corporate_id, "is_active": True}
    ).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="プロジェクトを作成する")
async def create_project(
    payload: ProjectCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    now = datetime.utcnow()
    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    result = await ctx.db["projects"].insert_one(doc)
    created = await ctx.db["projects"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/{project_id}", summary="プロジェクトを更新する")
async def update_project(
    project_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(project_id, "project")

    doc = await ctx.db["projects"].find_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Project not found")

    forbidden = {"corporate_id", "created_at", "_id", "is_active"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}
    update_data["updated_at"] = datetime.utcnow()

    await ctx.db["projects"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    updated = await ctx.db["projects"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{project_id}", summary="プロジェクトを論理削除する")
async def delete_project(
    project_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(project_id, "project")

    result = await ctx.db["projects"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted", "project_id": project_id}
