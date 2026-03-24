from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from app.api.deps import get_current_user
from app.api.helpers import resolve_corporate_id
from app.db.mongodb import get_database
from app.models.template import TemplateCreate, TemplateResponse, TemplateInDB

router = APIRouter()

def _serialize(doc: dict) -> dict:
    """Convert ObjectId to string for JSON serialization."""
    doc["id"] = str(doc.pop("_id"))
    return doc

@router.post("", response_model=TemplateResponse, summary="新しいテンプレートを保存する")
async def create_template(
    payload: TemplateCreate,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, user_id = await resolve_corporate_id(firebase_uid)
    db = get_database()

    doc = {
        **payload.model_dump(),
        "corporate_id": corporate_id,
        "created_by": user_id,
        "created_at": datetime.utcnow(),
    }

    result = await db["templates"].insert_one(doc)
    created = await db["templates"].find_one({"_id": result.inserted_id})
    return _serialize(created)

@router.get("", response_model=List[TemplateResponse], summary="テンプレート一覧を取得する")
async def list_templates(
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    cursor = db["templates"].find({"corporate_id": corporate_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return [_serialize(doc) for doc in docs]

@router.delete("/{template_id}", summary="テンプレートを削除する")
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_user),
):
    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    try:
        oid = ObjectId(template_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    result = await db["templates"].delete_one({"_id": oid, "corporate_id": corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {"status": "success"}
