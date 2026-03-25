import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from typing import List

from app.api.helpers import (
    serialize_doc,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    get_doc_or_404,
)

router = APIRouter()


def _serialize_department(doc: dict) -> dict:
    """Serialize a department document, mapping _id -> id."""
    result = dict(doc)
    result["id"] = str(result.pop("_id"))
    return result


@router.get("", summary="部門一覧を取得する")
async def list_departments(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["departments"].find({"corporate_id": ctx.corporate_id}).sort("created_at", 1)
    docs = await cursor.to_list(length=500)
    return [_serialize_department(doc) for doc in docs]


@router.post("", summary="部門を作成する", status_code=201)
async def create_department(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    doc = {
        "corporate_id": ctx.corporate_id,
        "name": name,
        "groups": [],
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["departments"].insert_one(doc)
    created = await ctx.db["departments"].find_one({"_id": result.inserted_id})
    return _serialize_department(created)


@router.patch("/{dept_id}", summary="部門名を更新する")
async def update_department(
    dept_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    oid = parse_oid(dept_id, "department")
    result = await ctx.db["departments"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": {"name": name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")

    updated = await ctx.db["departments"].find_one({"_id": oid})
    return _serialize_department(updated)


@router.delete("/{dept_id}", summary="部門を削除する", status_code=204)
async def delete_department(
    dept_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(dept_id, "department")
    result = await ctx.db["departments"].delete_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")


@router.post("/{dept_id}/groups", summary="グループを追加する", status_code=201)
async def add_group(
    dept_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    oid = parse_oid(dept_id, "department")
    group_id = str(uuid.uuid4())[:8]
    new_group = {"id": group_id, "name": name}

    result = await ctx.db["departments"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$push": {"groups": new_group}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")

    updated = await ctx.db["departments"].find_one({"_id": oid})
    return _serialize_department(updated)


@router.patch("/{dept_id}/groups/{group_id}", summary="グループ名を更新する")
async def update_group(
    dept_id: str,
    group_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    oid = parse_oid(dept_id, "department")
    result = await ctx.db["departments"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id, "groups.id": group_id},
        {"$set": {"groups.$.name": name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Department or group not found")

    updated = await ctx.db["departments"].find_one({"_id": oid})
    return _serialize_department(updated)


@router.delete("/{dept_id}/groups/{group_id}", summary="グループを削除する", status_code=204)
async def delete_group(
    dept_id: str,
    group_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(dept_id, "department")
    result = await ctx.db["departments"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$pull": {"groups": {"id": group_id}}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")
