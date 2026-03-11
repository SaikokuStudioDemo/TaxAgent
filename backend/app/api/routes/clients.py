from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from bson import ObjectId

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from app.models.master import ClientCreate
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("", summary="取引先一覧を取得する")
async def list_clients(
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    cursor = db["clients"].find({"corporate_id": corporate_id}).sort("name", 1)
    docs = await cursor.to_list(length=500)
    return [_serialize(doc) for doc in docs]


@router.post("", summary="取引先を作成する")
async def create_client(
    payload: ClientCreate,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    doc = {**payload.model_dump(), "corporate_id": corporate_id, "created_at": datetime.utcnow()}
    result = await db["clients"].insert_one(doc)
    created = await db["clients"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("/{client_id}", summary="取引先詳細を取得する")
async def get_client(
    client_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(client_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid client ID")

    doc = await db["clients"].find_one({"_id": oid, "corporate_id": corporate_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize(doc)


@router.patch("/{client_id}", summary="取引先を更新する")
async def update_client(
    client_id: str,
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(client_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid client ID")

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await db["clients"].update_one(
        {"_id": oid, "corporate_id": corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")

    updated = await db["clients"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{client_id}", summary="取引先を削除する")
async def delete_client(
    client_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(client_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid client ID")

    result = await db["clients"].delete_one({"_id": oid, "corporate_id": corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"status": "deleted", "client_id": client_id}
