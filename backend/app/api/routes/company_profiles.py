from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from app.models.master import CompanyProfileCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("", summary="自社プロファイル一覧を取得する")
async def list_profiles(current_user: dict = Depends(get_current_user)):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    cursor = db["company_profiles"].find({"corporate_id": corporate_id}).sort("is_default", -1)
    docs = await cursor.to_list(length=50)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="自社プロファイルを作成する")
async def create_profile(
    payload: CompanyProfileCreate,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    # If new profile is default, remove default from others
    if payload.is_default:
        await db["company_profiles"].update_many(
            {"corporate_id": corporate_id},
            {"$set": {"is_default": False}},
        )

    doc = {**payload.model_dump(), "corporate_id": corporate_id, "created_at": datetime.utcnow()}
    result = await db["company_profiles"].insert_one(doc)
    created = await db["company_profiles"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/{profile_id}", summary="自社プロファイルを更新する")
async def update_profile(
    profile_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(profile_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile ID")

    if payload.get("is_default"):
        await db["company_profiles"].update_many(
            {"corporate_id": corporate_id},
            {"$set": {"is_default": False}},
        )

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await db["company_profiles"].update_one(
        {"_id": oid, "corporate_id": corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")

    updated = await db["company_profiles"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{profile_id}", summary="自社プロファイルを削除する")
async def delete_profile(
    profile_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(profile_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid profile ID")

    result = await db["company_profiles"].delete_one({"_id": oid, "corporate_id": corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "deleted", "profile_id": profile_id}
