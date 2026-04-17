"""
テンプレート管理 API。
invoice_templates と receipt_templates を1つのルーターで管理する。
invoices.py → /invoices/templates
receipts.py → /receipts/templates
それぞれ template_type クエリパラメータでフィルタリングする。

権限：
- 一覧・詳細取得（GET）：認証ユーザー全員
- 作成・更新・削除：accounting・manager・admin のみ
- is_default=True のテンプレートは削除不可（400）
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.helpers import (
    CorporateContext,
    FULL_ACCESS_ROLES,
    get_corporate_context,
    parse_oid,
    serialize_doc as _serialize,
)
from app.models.template import TemplateCreate, TemplateResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_write_permission(ctx: CorporateContext) -> None:
    """accounting・manager・admin のみ作成・更新・削除が可能。"""
    if (ctx.role or "") not in FULL_ACCESS_ROLES:
        raise HTTPException(
            status_code=403,
            detail="テンプレートの編集は経理担当者以上のみ実行できます",
        )


# ─────────────────────────────────────────────────────────────────────────────
# AI テンプレート生成（既存・変更なし）
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/generate", summary="AI を使って HTML テンプレートを生成する")
async def generate_template(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """accounting・manager・admin のみ実行可能。"""
    _check_write_permission(ctx)
    from app.services.ai_service import AIService
    filename = payload.get("filename")
    result = await AIService.generate_invoice_html_template(filename or "")
    if not result:
        raise HTTPException(status_code=500, detail="AI Template generation failed")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# GET /templates — 一覧取得（⑤ html を除外）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", summary="テンプレート一覧を取得する（html 除く）")
async def list_templates(
    template_type: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    ⑤ html フィールドは除外して返す（レスポンスサイズ削減）。
    ⑥ template_type が指定された場合はその種別のみ返す。
    """
    query: Dict[str, Any] = {"corporate_id": ctx.corporate_id}
    if template_type:
        query["template_type"] = template_type

    # ⑤ projection で html を除外
    cursor = (
        ctx.db["templates"]
        .find(query, {"html": 0})
        .sort("created_at", -1)
    )
    docs = await cursor.to_list(length=100)
    return [_serialize(doc) for doc in docs]


# ─────────────────────────────────────────────────────────────────────────────
# GET /templates/:id — 詳細取得（⑤ html 含む）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{template_id}", summary="テンプレート詳細を取得する（html 含む）")
async def get_template(
    template_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """⑤ 詳細取得は html を含めて返す。"""
    oid = parse_oid(template_id, "template")
    doc = await ctx.db["templates"].find_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize(doc)


# ─────────────────────────────────────────────────────────────────────────────
# POST /templates — 新規作成
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", summary="テンプレートを新規作成する")
async def create_template(
    payload: TemplateCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """accounting・manager・admin のみ作成可能。"""
    _check_write_permission(ctx)

    # template_type のバリデーション
    if payload.template_type not in ("invoice", "receipt"):
        raise HTTPException(
            status_code=400,
            detail="template_type は 'invoice' または 'receipt' のみ有効です",
        )

    now = datetime.utcnow()
    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "created_by": ctx.user_id or "",
        "created_at": now,
        "updated_at": now,
    }
    result = await ctx.db["templates"].insert_one(doc)
    created = await ctx.db["templates"].find_one({"_id": result.inserted_id})
    return _serialize(created)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /templates/:id — 更新
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/{template_id}", summary="テンプレートを更新する")
async def update_template(
    template_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """accounting・manager・admin のみ更新可能。"""
    _check_write_permission(ctx)

    oid = parse_oid(template_id, "template")

    # is_default は PUT で変更不可（作成時のみ設定可能）
    allowed_updates = {"name", "description", "html", "is_active", "thumbnail", "template_type"}
    update_data = {k: v for k, v in payload.items() if k in allowed_updates}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid update fields provided")

    update_data["updated_at"] = datetime.utcnow()
    result = await ctx.db["templates"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")

    updated = await ctx.db["templates"].find_one({"_id": oid})
    return _serialize(updated)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /templates/:id — 部分更新（後方互換）
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/{template_id}", summary="テンプレートを部分更新する")
async def patch_template(
    template_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """PATCH も PUT と同じ処理を行う（後方互換）。"""
    return await update_template(template_id, payload, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /templates/:id — 削除（⑦ is_default 保護）
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{template_id}", summary="テンプレートを削除する")
async def delete_template(
    template_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    accounting・manager・admin のみ削除可能。
    ⑦ is_default=True のテンプレートは削除不可（400）。
    """
    _check_write_permission(ctx)

    oid = parse_oid(template_id, "template")

    existing = await ctx.db["templates"].find_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    # ⑦ デフォルトテンプレートは削除不可
    if existing.get("is_default", False):
        raise HTTPException(
            status_code=400,
            detail="デフォルトテンプレートは削除できません",
        )

    await ctx.db["templates"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    return {"status": "success"}
