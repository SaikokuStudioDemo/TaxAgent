from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

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

VALID_MEMBER_ROLES = {"admin", "approver", "member"}


class ProjectMemberAdd(BaseModel):
    user_id: str
    role: str = "member"


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


# ─────────────────────────────────────────────────────────────
# Project Members（role フィールドつき）
# ─────────────────────────────────────────────────────────────

@router.get("/{project_id}/members", summary="プロジェクトメンバー一覧を取得する")
async def list_project_members(
    project_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(project_id, "project")
    project = await ctx.db["projects"].find_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    cursor = ctx.db["project_members"].find({"project_id": project_id})
    members = await cursor.to_list(length=200)
    result = []
    for m in members:
        m["role"] = m.get("role", "member")  # 既存データへのフォールバック
        result.append(_serialize(m))
    return result


@router.post("/{project_id}/members", summary="プロジェクトメンバーを追加する")
async def add_project_member(
    project_id: str,
    payload: ProjectMemberAdd,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    if payload.role not in VALID_MEMBER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role は {VALID_MEMBER_ROLES} のいずれかを指定してください",
        )
    oid = parse_oid(project_id, "project")
    project = await ctx.db["projects"].find_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = await ctx.db["project_members"].find_one({
        "project_id": project_id,
        "employee_id": payload.user_id,
    })
    if existing:
        raise HTTPException(status_code=400, detail="このユーザーは既にメンバーです")

    doc = {
        "project_id": project_id,
        "employee_id": payload.user_id,
        "role": payload.role,
        "joined_at": datetime.utcnow(),
    }
    result = await ctx.db["project_members"].insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.patch("/{project_id}/members/{user_id}", summary="プロジェクトメンバーのロールを更新する")
async def update_project_member_role(
    project_id: str,
    user_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    role = payload.get("role")
    if not role or role not in VALID_MEMBER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"role は {VALID_MEMBER_ROLES} のいずれかを指定してください",
        )
    oid = parse_oid(project_id, "project")
    project = await ctx.db["projects"].find_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await ctx.db["project_members"].update_one(
        {"project_id": project_id, "employee_id": user_id},
        {"$set": {"role": role}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    return {"status": "updated", "user_id": user_id, "role": role}


@router.delete("/{project_id}/members/{user_id}", summary="プロジェクトメンバーを削除する")
async def remove_project_member(
    project_id: str,
    user_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(project_id, "project")
    project = await ctx.db["projects"].find_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await ctx.db["project_members"].delete_one({
        "project_id": project_id,
        "employee_id": user_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    return {"status": "removed", "user_id": user_id}
