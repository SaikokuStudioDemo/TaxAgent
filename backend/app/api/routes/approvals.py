from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from app.api.helpers import (
    serialize_doc as _serialize,
    get_corporate_context,
    CorporateContext,
    parse_oid,
)
from app.models.approval import ApprovalRuleCreate, ApprovalEventCreate, ApprovalPreviewRequest
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────── Approval Rules ───────────────

@router.get("/rules", summary="承認ルール一覧を取得する")
async def list_approval_rules(
    applies_to: Optional[str] = None,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    query: dict = {"corporate_id": ctx.corporate_id}
    if applies_to:
        query["applies_to"] = applies_to

    cursor = ctx.db["approval_rules"].find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=200)
    return [_serialize(doc) for doc in docs]


@router.post("/rules", summary="承認ルールを作成する")
async def create_approval_rule(
    payload: ApprovalRuleCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "created_at": datetime.utcnow(),
    }
    result = await ctx.db["approval_rules"].insert_one(doc)
    created = await ctx.db["approval_rules"].find_one({"_id": result.inserted_id})
    return _serialize(created)


@router.patch("/rules/{rule_id}", summary="承認ルールを更新する")
async def update_approval_rule(
    rule_id: str,
    payload: dict,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(rule_id, "rule")

    forbidden = {"corporate_id", "created_at", "_id"}
    update_data = {k: v for k, v in payload.items() if k not in forbidden}

    result = await ctx.db["approval_rules"].update_one(
        {"_id": oid, "corporate_id": ctx.corporate_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Approval rule not found")

    updated = await ctx.db["approval_rules"].find_one({"_id": oid})
    return _serialize(updated)


@router.delete("/rules/{rule_id}", summary="承認ルールを削除する")
async def delete_approval_rule(
    rule_id: str,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    oid = parse_oid(rule_id, "rule")

    result = await ctx.db["approval_rules"].delete_one({"_id": oid, "corporate_id": ctx.corporate_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Approval rule not found")
    return {"status": "deleted", "rule_id": rule_id}


@router.post("/rules/preview", summary="適用される承認ルールをプレビューする")
async def preview_approval_rule(
    payload: ApprovalPreviewRequest,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    from app.services.rule_evaluation_service import evaluate_approval_rules

    # Simple document shim for evaluation
    doc_shim = {
        "amount": payload.amount,
        "total_amount": payload.amount,
        **(payload.payload or {})
    }

    rule_id, steps = await evaluate_approval_rules(ctx.corporate_id, payload.document_type, doc_shim)

    return {
        "rule_id": rule_id,
        "steps": steps,
        "matched": rule_id is not None
    }


# ─────────────── Approval Actions ───────────────

@router.post("/actions", summary="承認アクション（承認・却下・差戻し）を記録する")
async def record_approval_action(
    payload: ApprovalEventCreate,
    ctx: CorporateContext = Depends(get_corporate_context),
):
    from app.services.notification_service import notify_next_approver, notify_submitter

    if payload.action == "rejected" and not payload.comment:
        raise HTTPException(status_code=400, detail="差戻しの場合はコメントが必要です。")

    # Persist the event
    event_doc = {
        **payload.model_dump(),
        "corporate_id": ctx.corporate_id,
        "approver_id": ctx.user_id,
        "timestamp": datetime.utcnow(),
    }
    await ctx.db["approval_events"].insert_one(event_doc)

    # Update the parent document's approval_status
    collection = "receipts" if payload.document_type == "receipt" else "invoices"
    doc_oid = parse_oid(payload.document_id, "document")

    doc = await ctx.db[collection].find_one({"_id": doc_oid})
    rule_id = doc.get("approval_rule_id") if doc else None
    current_step = doc.get("current_step", 1) if doc else 1
    next_step = current_step + 1
    submitter_id = doc.get("submitted_by", doc.get("created_by", "")) if doc else ""
    doc_summary = f"¥{doc.get('amount', doc.get('total_amount', 0)):,}" if doc else ""

    if payload.action == "approved":
        all_approved = False

        # Persist manually added extra steps if provided
        if payload.added_steps:
            added_steps_dicts = [s.model_dump() for s in payload.added_steps]
            await ctx.db[collection].update_one(
                {"_id": doc_oid},
                {"$set": {"extra_approval_steps": added_steps_dicts}}
            )
            # Update the local doc object so the step count logic below works
            if doc:
                doc["extra_approval_steps"] = added_steps_dicts

        # Calculate standard steps using priority: custom_approvers > project > rule
        total_steps = 1  # Minimum implicit step
        custom_approvers = doc.get("custom_approvers") if doc else None
        project_id = doc.get("project_id") if doc else None

        if custom_approvers:
            # Priority 1: custom approvers set directly on the document
            total_steps = max(total_steps, len(custom_approvers))
        elif project_id:
            # Priority 2: project approvers
            try:
                from bson import ObjectId as _ObjId
                proj = await ctx.db["projects"].find_one({"_id": _ObjId(project_id)})
                if proj:
                    proj_approvers = proj.get("approvers", [])
                    if proj_approvers:
                        total_steps = max(total_steps, len(proj_approvers))
            except Exception as e:
                logger.error(f"Error fetching project {project_id}: {e}")
        elif rule_id:
            # Priority 3: approval_rules (existing logic)
            try:
                rule = await ctx.db["approval_rules"].find_one({"_id": ObjectId(rule_id)})
                if rule:
                    required_steps = [s["step"] for s in rule.get("steps", []) if s.get("required")]
                    if required_steps:
                        total_steps = max(total_steps, max(required_steps))
            except Exception as e:
                logger.error(f"Error fetching/parsing rule {rule_id}: {e}")

        # Add extra steps to the total count
        extra_steps = doc.get("extra_approval_steps", []) if doc else []
        total_steps += len(extra_steps)

        # Optimistic locking query to ensure current_step hasn't changed
        db_query = {"_id": doc_oid}
        if doc and "current_step" in doc:
            db_query["current_step"] = current_step
        else:
            db_query["current_step"] = {"$exists": False}

        # Logic check: Are there more steps?
        if next_step <= total_steps:
            # Not finished yet -> increment current_step and notify next
            update_result = await ctx.db[collection].update_one(
                db_query,
                {"$set": {"current_step": next_step}},
            )
            if update_result.matched_count == 0:
                raise HTTPException(status_code=409, detail="同時に別の承認操作が行われたため処理が競合しました。画面を更新して再度お試しください。")

            # Notify the next approver
            if rule_id:
                await notify_next_approver(
                    corporate_id=ctx.corporate_id,
                    document_type=payload.document_type,
                    document_id=payload.document_id,
                    current_step=next_step,
                    approval_rule_id=rule_id,
                    document_summary=doc_summary,
                )
        else:
            # All steps completed -> mark as approved
            all_approved = True
            update_result = await ctx.db[collection].update_one(
                db_query,
                {"$set": {"approval_status": "approved"}},
            )
            if update_result.matched_count == 0:
                raise HTTPException(status_code=409, detail="同時に別の承認操作が行われたため処理が競合しました。画面を更新して再度お試しください。")

            # Notify the submitter that it's fully approved
            if submitter_id:
                await notify_submitter(
                    corporate_id=ctx.corporate_id,
                    document_type=payload.document_type,
                    document_id=payload.document_id,
                    submitter_id=submitter_id,
                    action="approved",
                    document_summary=doc_summary,
                )

    elif payload.action in ("rejected", "returned"):
        db_query = {"_id": doc_oid}
        if doc and "current_step" in doc:
            db_query["current_step"] = current_step
        else:
            db_query["current_step"] = {"$exists": False}

        update_result = await ctx.db[collection].update_one(
            db_query,
            {"$set": {"approval_status": "rejected"}},
        )
        if update_result.matched_count == 0:
            raise HTTPException(status_code=409, detail="同時に別の承認操作が行われたため処理が競合しました。画面を更新して再度お試しください。")

        # Notify the submitter that it was rejected
        if submitter_id:
            await notify_submitter(
                corporate_id=ctx.corporate_id,
                document_type=payload.document_type,
                document_id=payload.document_id,
                submitter_id=submitter_id,
                action="rejected",
                document_summary=doc_summary,
            )

    return {"status": "recorded", "action": payload.action}
