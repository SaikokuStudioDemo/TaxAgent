from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
    get_doc_or_404,
    build_list_query,
    build_scope_filter,
    enrich_with_approval_history,
    build_name_map,
    extract_fiscal_period,
    ApprovalStatus,
)
from app.services.duplicate_detector import check_duplicate_receipt
from app.models.transaction import ReceiptCreate
import logging
from app.services.rule_evaluation_service import evaluate_approval_rules
from app.api.routes.templates import router as templates_router
from app.services.journal_rule_service import apply_journal_rules
from app.services.firebase_storage import generate_signed_url
from app.services.alert_service import get_default_tax_rate

logger = logging.getLogger(__name__)
router = APIRouter()

router.include_router(templates_router, prefix="/templates", tags=["receipt-templates"])


# ─────────────── Batch Submit ───────────────

@router.post("/batch", summary="領収書を一括提出する（AI抽出用）")
async def submit_receipts_batch(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    receipts_data = payload.get("receipts", [])
    if not receipts_data:
        raise HTTPException(status_code=400, detail="No receipts provided.")

    default_tax_rate = await get_default_tax_rate(ctx.db)
    docs_to_insert = []
    for r in receipts_data:
        amount = r.get("amount", 0)
        fiscal_period = extract_fiscal_period(r.get("date"))
        rule_id, steps = await evaluate_approval_rules(ctx.corporate_id, "receipt", r)
        role_name_map = {
            "direct_manager": "直属上長",
            "accounting": "経理担当",
            "dept_manager": "部門長",
            "admin": "管理者",
            "group_leader": "グループリーダー",
        }
        initial_history = [
            {
                "step": s.get("step", i + 1),
                "roleId": s.get("role", ""),
                "roleName": role_name_map.get(s.get("role", ""), s.get("role", "")),
                "status": "pending",
            }
            for i, s in enumerate(steps or [])
        ]
        doc = {
            "corporate_id": ctx.corporate_id,
            "submitted_by": ctx.user_id,
            "document_type": "receipt",
            "date": r.get("date", ""),
            "amount": amount,
            "tax_rate": r.get("taxRate", r.get("tax_rate", default_tax_rate)),
            "payee": r.get("payee", ""),
            "category": r.get("category", ""),
            "payment_method": r.get("payment_method", "立替"),
            "line_items": r.get("line_items", []),
            "attachments": r.get("attachments", []),
            "storage_path": r.get("storage_path"),
            "storage_url": r.get("storage_url"),
            "fiscal_period": fiscal_period,
            "ai_extracted": True,
            "approval_status": ApprovalStatus.PENDING,
            "reconciliation_status": "unreconciled",
            "approval_rule_id": rule_id,
            "approval_history": initial_history,
            "current_step": 1,
            "created_at": datetime.utcnow(),
        }
        docs_to_insert.append(doc)

    docs_to_insert = await apply_journal_rules(ctx.db, ctx.corporate_id, docs_to_insert)

    result = await ctx.db["receipts"].insert_many(docs_to_insert)

    for oid in result.inserted_ids:
        await ctx.db["audit_logs"].insert_one({
            "corporate_id": ctx.corporate_id,
            "document_type": "receipt",
            "document_id": str(oid),
            "step": 0,
            "action": "submitted",
            "approver_id": ctx.user_id,
            "comment": None,
            "timestamp": datetime.utcnow(),
        })

    return {
        "status": "success",
        "message": f"{len(docs_to_insert)} receipts submitted",
        "inserted_count": len(docs_to_insert),
        "inserted_ids": [str(oid) for oid in result.inserted_ids],
    }


# ─────────────── Single Receipt CRUD ───────────────

@router.post("", summary="領収書を1件作成する")
async def create_receipt(
    payload: ReceiptCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    rule_id, _ = await evaluate_approval_rules(ctx.corporate_id, "receipt", payload.model_dump())
    fiscal_period = extract_fiscal_period(payload.date)

    payload_dict = payload.model_dump()
    submitted_by = payload_dict.pop("submitted_by", None) or ctx.user_id
    doc = {
        **payload_dict,
        "corporate_id": ctx.corporate_id,
        "submitted_by": submitted_by,
        "document_type": "receipt",
        "approval_status": "pending_approval",
        "reconciliation_status": "unreconciled",
        "approval_rule_id": rule_id,
        "current_step": 1,
        "fiscal_period": fiscal_period,
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["receipts"].insert_one(doc)
    await ctx.db["approval_events"].insert_one({
        "corporate_id": ctx.corporate_id,
        "document_type": "receipt",
        "document_id": str(result.inserted_id),
        "step": 0,
        "action": "submitted",
        "approver_id": ctx.user_id,
        "comment": None,
        "timestamp": datetime.utcnow(),
    })
    created = await ctx.db["receipts"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", summary="領収書一覧を取得する")
async def list_receipts(
    approval_status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    submitted_by: Optional[str] = None,
    reconciliation_status: Optional[str] = None,
    receipt_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    amount_min: Optional[int] = None,
    amount_max: Optional[int] = None,
    payee: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query = build_list_query(ctx.corporate_id, approval_status=approval_status, fiscal_period=fiscal_period)
    query["is_deleted"] = {"$ne": True}

    scope = build_scope_filter(ctx)
    if scope:
        query.update(scope)
    if submitted_by == "me":
        query["submitted_by"] = ctx.user_id
    if reconciliation_status:
        query["reconciliation_status"] = reconciliation_status
    if receipt_type:
        query["receipt_type"] = receipt_type

    # 電子帳簿保存法対応の検索フィルター
    if date_from:
        query.setdefault("date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to
    if amount_min is not None:
        query.setdefault("amount", {})["$gte"] = amount_min
    if amount_max is not None:
        query.setdefault("amount", {})["$lte"] = amount_max
    if payee:
        query["payee"] = {"$regex": payee, "$options": "i"}

    cursor = ctx.db["receipts"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    user_ids = {doc.get("submitted_by") for doc in docs if doc.get("submitted_by")}
    name_map = await build_name_map(ctx.db, user_ids)
    result = []
    for doc in docs:
        s = _serialize(doc)
        s["submitter_name"] = name_map.get(s.get("submitted_by", ""), "不明")
        result.append(s)
    return result


@router.get("/{receipt_id}/file-url", summary="添付ファイルの署名付きURLを取得する")
async def get_file_url(
    receipt_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    storage_path から署名付きURL（有効60分）を生成して返す。
    電子帳簿保存法に基づき承認済みファイルも閲覧可能。
    """
    receipt = await ctx.db["receipts"].find_one({
        "_id": parse_oid(receipt_id, "receipt"),
        "corporate_id": ctx.corporate_id,
        "is_deleted": {"$ne": True},
    })
    if not receipt:
        raise HTTPException(status_code=404, detail="領収書が見つかりません")

    storage_path = receipt.get("storage_path")
    if not storage_path:
        raise HTTPException(status_code=404, detail="添付ファイルがありません")

    url = await generate_signed_url(storage_path)
    if not url:
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    return {"url": url, "expires_in": 3600}


@router.get("/{receipt_id}", summary="領収書詳細を取得する")
async def get_receipt(
    receipt_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(
        ctx.db, "receipts", receipt_id, ctx.corporate_id, "receipt",
        extra_filter={"is_deleted": {"$ne": True}},
    )
    result = _serialize(doc)
    return await enrich_with_approval_history(ctx.db, result, receipt_id, "receipt")


@router.patch("/{receipt_id}", summary="領収書を更新する")
async def update_receipt(
    receipt_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(receipt_id, "receipt")

    if "amount" in payload:
        new_rule_id, _ = await evaluate_approval_rules(ctx.corporate_id, "receipt", payload)
        payload["approval_rule_id"] = new_rule_id

    forbidden = {"corporate_id", "submitted_by", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await ctx.db["receipts"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Receipt not found")

    updated = await ctx.db["receipts"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{receipt_id}", summary="領収書を論理削除する")
async def delete_receipt(
    receipt_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(receipt_id, "receipt")

    receipt = await ctx.db["receipts"].find_one(
        {"_id": oid, "corporate_id": ctx.corporate_id}
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if receipt.get("approval_status") == ApprovalStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail="承認済みの領収書は削除できません。（電子帳簿保存法）",
        )

    await ctx.db["receipts"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": datetime.utcnow(),
            "deleted_by": ctx.user_id,
        }},
    )
    return {"status": "deleted", "receipt_id": receipt_id}


# ─────────────────────────────────────────────────────────────────────────────
# 二重計上チェック
# ─────────────────────────────────────────────────────────────────────────────

class CheckDuplicateReceiptRequest(BaseModel):
    date: str
    amount: int
    payee: str
    exclude_id: Optional[str] = None


@router.post("/check-duplicate", summary="領収書の二重計上チェックを行う")
async def check_duplicate_receipt_endpoint(
    payload: CheckDuplicateReceiptRequest,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    return await check_duplicate_receipt(
        corporate_id=ctx.corporate_id,
        date=payload.date,
        amount=payload.amount,
        payee=payload.payee,
        exclude_id=payload.exclude_id,
    )
