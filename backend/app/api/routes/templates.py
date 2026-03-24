from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime

from app.api.deps import get_current_user
from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.template import TemplateCreate, TemplateResponse, TemplateInDB

router = APIRouter()


@router.post("/generate", summary="AIを使ってHTMLテンプレートを生成する")
async def generate_template(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    from app.services.ai_service import AIService

    filename = payload.get("filename")
    result = await AIService.generate_invoice_html_template(filename or "")
    if not result:
        raise HTTPException(status_code=500, detail="AI Template generation failed")
    return result

@router.post("", response_model=TemplateResponse, summary="新しいテンプレートを保存する")
async def create_template(
    payload: TemplateCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "created_by": ctx.user_id,
        "created_at": datetime.utcnow(),
    }

    result = await ctx.db["templates"].insert_one(doc)
    created = await ctx.db["templates"].find_one({"_id": result.inserted_id})
    return _serialize(created)

@router.get("", response_model=List[TemplateResponse], summary="テンプレート一覧を取得する")
async def list_templates(
    ctx: CorporateContext = Depends(get_corporate_context),
):
    cursor = ctx.db["templates"].find({"corporate_id": ctx.corporate_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return [_serialize(doc) for doc in docs]

@router.patch("/{template_id}", response_model=TemplateResponse, summary="テンプレートを更新する")
async def update_template(
    template_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(template_id, "template")

    allowed_updates = {"name", "description", "html", "is_active", "thumbnail"}
    update_data = {k: v for k, v in payload.items() if k in allowed_updates}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid update fields provided")

    result = await ctx.db["templates"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")

    updated = await ctx.db["templates"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{template_id}", summary="テンプレートを削除する")
async def delete_template(
    template_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(template_id, "template")

    result = await ctx.db["templates"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")

    return {"status": "success"}
