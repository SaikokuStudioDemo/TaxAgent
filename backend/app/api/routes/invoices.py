from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

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
)
from app.models.invoice import InvoiceCreate, InvoiceInDB
import logging
from app.services.rule_evaluation_service import evaluate_approval_rules
from app.services.journal_rule_service import apply_journal_rules

logger = logging.getLogger(__name__)
router = APIRouter()

from app.api.routes.templates import router as templates_router
router.include_router(templates_router, prefix="/templates", tags=["invoice-templates"])


@router.post("", summary="請求書を作成する")
async def create_invoice(
    payload: InvoiceCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    # Determine fiscal period from issue_date (YYYY-MM-DD → YYYY-MM)
    fiscal_period = payload.issue_date[:7] if payload.issue_date else datetime.utcnow().strftime("%Y-%m")

    # ── received請求書の特別処理 ──────────────────────────────────
    if payload.document_type == "received":
        # client_nameが空の場合は自社名を自動セット
        if not payload.client_name:
            profile = await ctx.db["company_profiles"].find_one(
                {"corporate_id": ctx.corporate_id, "is_default": True}
            )
            if not profile:
                profile = await ctx.db["company_profiles"].find_one(
                    {"corporate_id": ctx.corporate_id}
                )
            if profile:
                payload = payload.model_copy(update={"client_name": profile.get("company_name", "")})
                logger.info(f"received invoice: client_name auto-set to '{payload.client_name}'")

        # vendor_nameが空の場合は警告ログ
        if not payload.vendor_name:
            logger.warning(
                f"received invoice created without vendor_name "
                f"(client_name={payload.client_name!r}, amount={payload.total_amount})"
            )

    # Match approval rules
    rule_id, rule_steps = await evaluate_approval_rules(ctx.corporate_id, f"{payload.document_type}_invoice", payload.model_dump())

    requested_status = payload.approval_status or "draft"
    # 承認ルールなしで即送付 → 自動承認扱い
    is_auto_approved = requested_status == "sent" and rule_id is None

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
        for i, s in enumerate(rule_steps or [])
    ]

    payload_dict = payload.model_dump()
    submitted_by = payload_dict.pop("submitted_by", None) or ctx.user_id
    doc = {
        **payload_dict,
        "corporate_id": ctx.corporate_id,
        "created_by": ctx.user_id,
        "submitted_by": submitted_by,
        "approval_status": "auto_approved" if is_auto_approved else requested_status,
        "reconciliation_status": "unreconciled",
        "current_step": 1,
        "approval_rule_id": rule_id,
        "approval_steps": rule_steps if rule_id else [],
        "approval_history": initial_history,
        "attachments": payload.attachments or [],
        "fiscal_period": fiscal_period,
        "ai_extracted": False,
        "created_at": datetime.utcnow(),
        "paid_at": None,
    }

    docs = await apply_journal_rules(ctx.db, ctx.corporate_id, [doc], doc_type="invoice")
    doc = docs[0]

    result = await ctx.db["invoices"].insert_one(doc)
    await ctx.db["audit_logs"].insert_one({
        "corporate_id": ctx.corporate_id,
        "document_type": "invoice",
        "document_id": str(result.inserted_id),
        "step": 0,
        "action": "submitted",
        "approver_id": ctx.user_id,
        "comment": None,
        "timestamp": datetime.utcnow(),
    })
    created = await ctx.db["invoices"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.get("", summary="請求書一覧を取得する")
async def list_invoices(
    document_type: Optional[str] = None,
    approval_status: Optional[str] = None,
    fiscal_period: Optional[str] = None,
    reconciliation_status: Optional[str] = None,
    submitted_by: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query = build_list_query(
        ctx.corporate_id,
        document_type=document_type,
        approval_status=approval_status,
        fiscal_period=fiscal_period,
    )
    query["is_deleted"] = {"$ne": True}
    scope = build_scope_filter(ctx)
    if scope:
        query.update(scope)
    if reconciliation_status:
        query["reconciliation_status"] = reconciliation_status
    if submitted_by == "me":
        query["submitted_by"] = ctx.user_id
    elif submitted_by:
        query["submitted_by"] = submitted_by

    cursor = ctx.db["invoices"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    user_ids = {doc.get("created_by") for doc in docs if doc.get("created_by")}
    submitted_ids = {doc.get("submitted_by") for doc in docs if doc.get("submitted_by")}
    name_map = await build_name_map(ctx.db, user_ids | submitted_ids)
    result = []
    for doc in docs:
        s = _serialize(doc)
        s["creator_name"] = name_map.get(s.get("created_by", ""), "不明")
        s["submitter_name"] = name_map.get(s.get("submitted_by", ""), "不明")
        result.append(s)
    return result


@router.get("/{invoice_id}", summary="請求書詳細を取得する")
async def get_invoice(
    invoice_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = await get_doc_or_404(ctx.db, "invoices", invoice_id, ctx.corporate_id, "invoice")

    result = _serialize(doc)
    return await enrich_with_approval_history(
        ctx.db, result, invoice_id,
        ["invoice", "received_invoice", "issued_invoice"],
    )


@router.patch("/{invoice_id}", summary="請求書を更新する")
async def update_invoice(
    invoice_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(invoice_id, "invoice")

    # Disallow updating protected fields
    forbidden = {"corporate_id", "created_by", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    existing = await ctx.db["invoices"].find_one({"_id": oid, "corporate_id": ctx.corporate_id}, {"approval_rule_id": 1, "approval_status": 1})

    # pending_approval に遷移する場合はルールのステップを保存
    if update_data.get("approval_status") == "pending_approval" and existing:
        rule_id = existing.get("approval_rule_id")
        if rule_id:
            from app.services.rule_evaluation_service import get_rule_steps
            steps = await get_rule_steps(rule_id)
            update_data["approval_steps"] = steps


    result = await ctx.db["invoices"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    updated = await ctx.db["invoices"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/{invoice_id}", summary="請求書を削除する")
async def delete_invoice(
    invoice_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(invoice_id, "invoice")

    result = await ctx.db["invoices"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": {"is_deleted": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {"status": "deleted", "invoice_id": invoice_id}


@router.post("/{invoice_id}/send", summary="請求書を送付する")
async def send_invoice(
    invoice_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """Mark invoice as sent. Actual email sending will be handled by the notification service."""
    invoice = await get_doc_or_404(ctx.db, "invoices", invoice_id, ctx.corporate_id, "invoice")

    if invoice.get("document_type") != "issued":
        raise HTTPException(status_code=400, detail="Only issued invoices can be sent.")

    await ctx.db["invoices"].update_one(
        {"_id": invoice["_id"]},
        {"$set": {"delivery_status": "sent"}},
    )
    return {"status": "sent", "invoice_id": invoice_id}


@router.post("/bulk-action", summary="複数の請求書に対して一括操作を行う")
async def bulk_action(
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    """
    Perform bulk actions (delete, send) on multiple invoices.
    Payload: { "action": "delete" | "send", "ids": ["id1", "id2", ...] }
    """
    ids = payload.get("ids", [])
    action = payload.get("action")

    if not ids or not action:
        raise HTTPException(status_code=400, detail="Missing ids or action")

    try:
        oids = [ObjectId(i) for i in ids]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format in list")

    if action == "delete":
        await ctx.db["invoices"].update_many(
            {"_id": {"$in": oids}, "corporate_id": ctx.corporate_id},
            {"$set": {"is_deleted": True}}
        )
    elif action == "send":
        await ctx.db["invoices"].update_many(
            {"_id": {"$in": oids}, "corporate_id": ctx.corporate_id, "document_type": "issued"},
            {"$set": {"delivery_status": "sent"}}
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    return {"status": "success", "action": action, "count": len(ids)}
