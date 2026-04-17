"""
Admin-only endpoints for internal operations like running alert checks.
These should be protected further in production (e.g., IP whitelist or admin role check).
"""
import asyncio
import logging

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.api.helpers import verify_tax_firm
from app.services.alert_service import run_all_alerts

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/run-alerts", summary="アラートチェックを手動実行する（管理者専用）")
async def trigger_alerts(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger all alert checks (due date + high amount).
    Only tax_firm corporates or users with admin role can call this endpoint.
    In production this should be scheduled via a cron job or APScheduler.
    """
    from app.db.mongodb import get_database
    firebase_uid = current_user.get("uid")
    db = get_database()

    # Check if the caller is a tax_firm corporate entity
    corporate = await db["corporates"].find_one({"firebase_uid": firebase_uid})
    if corporate:
        if corporate.get("corporateType") != "tax_firm":
            raise HTTPException(status_code=403, detail="この操作は税理士法人のみ実行できます。")
    else:
        # Check if the caller is an employee with admin role
        employee = await db["employees"].find_one({"firebase_uid": firebase_uid})
        if not employee or employee.get("role") != "admin":
            raise HTTPException(status_code=403, detail="この操作は管理者権限が必要です。")

    logger.info(f"Manual alert run triggered by {firebase_uid}")
    result = await run_all_alerts()
    return {"status": "completed", "results": result}


@router.get("/notifications", summary="通知一覧を取得する")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    """Return all notifications for this corporate (most recent first)."""
    from app.api.helpers import resolve_corporate_id
    from app.db.mongodb import get_database

    firebase_uid = current_user.get("uid")
    corporate_id, _ = await resolve_corporate_id(firebase_uid)
    db = get_database()

    cursor = db["notifications"].find({"corporate_id": corporate_id}).sort("sent_at", -1)
    docs = await cursor.to_list(length=200)
    for doc in docs:
        doc["id"] = str(doc.pop("_id"))
    return docs


@router.get("/corporate-alerts", summary="配下法人のアラート状況一覧を取得する")
async def get_corporate_alerts(
    current_user: dict = Depends(get_current_user),
):
    """
    税理士法人が配下の全法人のアラート状況を取得する。
    各法人の未処理件数・アラート種別を返す。
    アラートが多い法人が先頭に表示される。
    """
    from app.db.mongodb import get_database

    firebase_uid = current_user.get("uid")
    db = get_database()

    caller = await verify_tax_firm(firebase_uid, db)

    # 配下の全法人を取得
    clients = await db["corporates"].find({
        "corporateType": "corporate",
        "advising_tax_firm_id": firebase_uid,
    }).to_list(length=200)

    results = []
    for client in clients:
        corp_id = str(client["_id"])

        # ② asyncio はファイル先頭でインポート済み・ループ内インライン import なし
        # 各法人の未処理件数を並列取得
        (
            pending_receipts,
            pending_invoices,
            unmatched_tx,
            rejected_stale,
            approval_delay,
        ) = await asyncio.gather(
            db["receipts"].count_documents({
                "corporate_id": corp_id,
                "approval_status": "pending_approval",
            }),
            db["invoices"].count_documents({
                "corporate_id": corp_id,
                "approval_status": "pending_approval",
            }),
            db["transactions"].count_documents({
                "corporate_id": corp_id,
                "status": "unmatched",
            }),
            db["receipts"].count_documents({
                "corporate_id": corp_id,
                "approval_status": "rejected",
                "rejected_stale_alerted": True,
            }),
            db["receipts"].count_documents({
                "corporate_id": corp_id,
                "approval_status": "pending_approval",
                "approval_delay_alerted": True,
            }),
        )

        total_alerts = rejected_stale + approval_delay
        results.append({
            "corporate_id": corp_id,
            "company_name": client.get("name", ""),
            "pending_receipts": pending_receipts,
            "pending_invoices": pending_invoices,
            "unmatched_transactions": unmatched_tx,
            "rejected_stale_count": rejected_stale,
            "approval_delay_count": approval_delay,
            "total_alerts": total_alerts,
            "has_alerts": total_alerts > 0,
        })

    # アラートあり法人を先に表示
    results.sort(key=lambda x: x["total_alerts"], reverse=True)
    return {"data": results}
